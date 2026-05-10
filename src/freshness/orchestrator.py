"""Phase 7B orchestrator — runs the 5-layer freshness checks.

Layer 1 (decay) is read-only at query time (effective_confidence is computed
on the fly). The orchestrator runs Layers 2-5 to populate the
`edge_freshness` queue: each detector that fires sets the row's
`status='needs_review'` with a `trigger_reason`.

Network-gated layers (hash_diff, filing_trigger) and price-data-gated layer
(correlation_drift) accept injection points for tests / batch execution.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Iterable

from src.freshness.decay import is_stale
from src.freshness.hash_diff import detect_hash_change
from src.utils.db import get_connection, init_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def queue_for_review(
    symbol: str,
    *,
    reason: str,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Mark a stock as 'needs_review' with the given reason."""
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO edge_freshness (symbol, status, trigger_reason, flagged_at)
            VALUES (?, 'needs_review', ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                status = 'needs_review',
                trigger_reason = ?,
                flagged_at = ?
            """,
            (symbol, reason, _now(), reason, _now()),
        )
        conn.commit()
    finally:
        if own_conn:
            conn.close()


def acknowledge(
    symbol: str,
    *,
    action: str,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """User action on a queue entry.

    Actions:
        re_extract — clears the queue entry (fresh) and bumps last_extracted_at
        skip_30d   — clears with status='aging' and re-flags after 30 days (caller's job)
        pin_current — clears with status='fresh' permanently (until next trigger)
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        if action == "re_extract":
            new_status = "fresh"
            extracted_at = _now()
        elif action == "skip_30d":
            new_status = "aging"
            extracted_at = None
        elif action == "pin_current":
            new_status = "fresh"
            extracted_at = None
        else:
            return {"symbol": symbol, "ok": False, "error": f"unknown action: {action}"}

        conn.execute(
            """
            UPDATE edge_freshness
            SET status = ?,
                trigger_reason = NULL,
                flagged_at = NULL,
                last_extracted_at = COALESCE(?, last_extracted_at)
            WHERE symbol = ?
            """,
            (new_status, extracted_at, symbol),
        )
        conn.commit()
        return {"symbol": symbol, "ok": True, "new_status": new_status}
    finally:
        if own_conn:
            conn.close()


def run_layer_2_hash_diff(
    symbols: Iterable[str],
    *,
    fetch_fn=None,
    log: bool = True,
) -> dict[str, int]:
    """Run Layer 2 across a list of symbols and queue any that changed."""
    init_db()
    conn = get_connection()
    try:
        flagged = 0
        skipped = 0
        for sym in symbols:
            out = detect_hash_change(sym, fetch_fn=fetch_fn, conn=conn)
            if out.get("error"):
                skipped += 1
                continue
            if out["changed"]:
                queue_for_review(sym, reason="hash_change", conn=conn)
                flagged += 1
                if log:
                    print(f"  [layer2] {sym} flagged: business summary changed")
        return {"flagged": flagged, "skipped": skipped}
    finally:
        conn.close()


def run_layer_3_filing_trigger(
    symbols: Iterable[str],
    *,
    fetch_fn=None,
    log: bool = True,
) -> dict[str, int]:
    """Run Layer 3 across a list of symbols. New 10-K/Q/8-K → flag."""
    from src.freshness.filing_trigger import detect_new_filings

    init_db()
    conn = get_connection()
    try:
        flagged = 0
        skipped = 0
        for sym in symbols:
            out = detect_new_filings(sym, fetch_fn=fetch_fn, conn=conn)
            if out.get("error"):
                skipped += 1
                continue
            if out["new_filings"]:
                forms = ",".join({f["form"] for f in out["new_filings"]})
                queue_for_review(sym, reason=f"new_filing:{forms}", conn=conn)
                flagged += 1
                if log:
                    print(f"  [layer3] {sym} flagged: new {forms}")
        return {"flagged": flagged, "skipped": skipped}
    finally:
        conn.close()


def flag_stale_via_decay(
    *,
    threshold_confidence: float = 0.5,
    log: bool = True,
) -> dict[str, int]:
    """Pure Layer-1 sweep: any symbol whose last_extracted_at is sufficiently
    old gets queued with reason='decay'. This is the lowest-risk layer —
    runs without any network or LLM calls."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol, last_extracted_at FROM edge_freshness WHERE status != 'needs_review'"
        ).fetchall()
        flagged = 0
        for r in rows:
            if is_stale(r["last_extracted_at"], threshold_confidence=threshold_confidence):
                queue_for_review(r["symbol"], reason="decay", conn=conn)
                flagged += 1
                if log:
                    print(f"  [layer1] {r['symbol']} flagged: decay")
        return {"flagged": flagged}
    finally:
        conn.close()


def run_orchestrator(
    symbols: Iterable[str],
    *,
    layers: tuple[str, ...] = ("layer1", "layer2", "layer3"),
    hash_fetch_fn=None,
    filing_fetch_fn=None,
    log: bool = True,
) -> dict[str, dict]:
    """Convenience: run multiple layers in sequence.

    Layer 4 (correlation_drift) and Layer 5 (news_drift) are not wired here
    because they require price data + news data layers that are also network-
    gated. The user-facing orchestrator can compose them when those data
    layers are available.
    """
    out: dict[str, dict] = {}
    if "layer1" in layers:
        out["layer1"] = flag_stale_via_decay(log=log)
    if "layer2" in layers:
        out["layer2"] = run_layer_2_hash_diff(symbols, fetch_fn=hash_fetch_fn, log=log)
    if "layer3" in layers:
        out["layer3"] = run_layer_3_filing_trigger(symbols, fetch_fn=filing_fetch_fn, log=log)
    return out
