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
from typing import Callable, Iterable

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
    extractor_fn: Callable[[str], dict] | None = None,
) -> dict:
    """User action on a queue entry.

    Actions:
        re_extract  — invoke the SEC 10-K extractor for `symbol`. On success,
                      mark fresh and bump last_extracted_at. On extractor error,
                      LEAVE the queue entry in needs_review so the user can retry.
        skip_30d    — set status='aging'; caller is expected to re-flag after 30d
        pin_current — set status='fresh' permanently (until next trigger fires)

    `extractor_fn` is the injection point: defaults to
    `src.data.sec_10k_extractor.process_symbol` (lazy import to avoid a circular
    dependency at module load time). Tests pass a stub.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        if action == "re_extract":
            if extractor_fn is None:
                # Lazy import: orchestrator → extractor → (downstream) would otherwise
                # create a cycle through src.data at import time.
                from src.data.sec_10k_extractor import process_symbol as extractor_fn  # type: ignore

            extraction_result = extractor_fn(symbol) or {}
            err = extraction_result.get("error")
            if err:
                # Leave the queue entry alone; user can retry.
                return {
                    "symbol": symbol,
                    "ok": False,
                    "error": err,
                    "edges_written": extraction_result.get("edges_written", 0),
                }
            new_status = "fresh"
            extracted_at = _now()
            edges_written = extraction_result.get("edges_written", 0)

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
            return {
                "symbol": symbol,
                "ok": True,
                "new_status": new_status,
                "edges_written": edges_written,
            }

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


def run_layer_4_correlation_drift(
    symbols: Iterable[str],
    *,
    returns_fetch_fn: Callable[[str, int], list[float]] | None = None,
    baseline_days: int = 252,
    recent_days: int = 90,
    log: bool = True,
) -> dict[str, int]:
    """Layer 4: flag stocks whose 90-day rolling correlation with their tagged
    peers has dropped sharply vs the prior 1-year baseline.

    `returns_fetch_fn(symbol, days) -> list[float]` is the injection point:
        - Default: live Tiingo fetch via src.data.tiingo (skips symbol on error)
        - Tests pass a stub that returns synthetic return series

    Stocks with no peers in stock_peers are skipped (nothing to compare against).
    Detection threshold lives in src.freshness.correlation_drift.DEFAULT_DRIFT_THRESHOLD.
    """
    from src.freshness.correlation_drift import detect_drift

    if returns_fetch_fn is None:
        returns_fetch_fn = _default_returns_fetch

    init_db()
    conn = get_connection()
    try:
        flagged = 0
        skipped = 0
        for sym in symbols:
            peer_rows = conn.execute(
                "SELECT to_symbol FROM stock_peers WHERE from_symbol = ?", (sym,)
            ).fetchall()
            peer_syms = [r["to_symbol"] for r in peer_rows]
            if not peer_syms:
                skipped += 1
                continue

            try:
                target_baseline = returns_fetch_fn(sym, baseline_days + recent_days)
                target_recent   = returns_fetch_fn(sym, recent_days)
                peer_baseline = [returns_fetch_fn(p, baseline_days + recent_days) for p in peer_syms]
                peer_recent   = [returns_fetch_fn(p, recent_days) for p in peer_syms]
            except Exception:
                skipped += 1
                continue

            if not target_baseline or not target_recent:
                skipped += 1
                continue

            result = detect_drift(
                sym,
                baseline_target=target_baseline,
                baseline_peers=[p for p in peer_baseline if p],
                recent_target=target_recent,
                recent_peers=[p for p in peer_recent if p],
            )
            if result.drifted:
                queue_for_review(sym, reason="peer_decoupling", conn=conn)
                flagged += 1
                if log:
                    print(
                        f"  [layer4] {sym} flagged: peer-correlation dropped "
                        f"{result.baseline_correlation:.2f}→{result.recent_correlation:.2f}"
                    )
        return {"flagged": flagged, "skipped": skipped}
    finally:
        conn.close()


def _default_returns_fetch(symbol: str, days: int) -> list[float]:
    """Live Tiingo daily-returns fetcher. Returns [] if the data layer is
    unavailable so the orchestrator skips the symbol rather than crashing."""
    try:
        from src.data.tiingo import fetch_daily_returns
        return list(fetch_daily_returns(symbol, days=days))
    except Exception:
        return []


def run_layer_5_news_drift(
    symbols: Iterable[str],
    *,
    headlines_fetch_fn: Callable[[str], list[str]] | None = None,
    industry_domains_fn: Callable[[str], set[str]] | None = None,
    log: bool = True,
) -> dict[str, int]:
    """Layer 5: flag stocks whose recent news coverage is dominated by a
    different domain than their tagged industry (e.g. SOFI tagged 'banking'
    but every recent headline is about crypto).

    Both injection points default to no-op so Layer 5 is safe to enable in
    `run_orchestrator(layers=…)` without crashing — the wrapper simply
    skips every symbol when the data layer isn't available:
        headlines_fetch_fn(symbol)    -> list[str]   (default: returns [])
        industry_domains_fn(symbol)   -> set[str]    (default: returns set())

    Tests pass real stubs to exercise the drift detection.
    """
    from src.freshness.news_drift import detect_news_drift
    from src.news.aggregate import KeywordImpactRow

    if headlines_fetch_fn is None:
        headlines_fetch_fn = lambda _sym: []
    if industry_domains_fn is None:
        industry_domains_fn = lambda _sym: set()

    init_db()
    conn = get_connection()
    try:
        # Pre-load keyword_impact + universe — Layer 5 needs both per call.
        impact_rows: list[KeywordImpactRow] = []
        for r in conn.execute(
            "SELECT keyword, industry_code, target_stock, polarity, weight, domain "
            "FROM keyword_impact"
        ).fetchall():
            impact_rows.append(KeywordImpactRow(
                keyword=r["keyword"],
                industry_code=r["industry_code"],
                target_stock=r["target_stock"],
                polarity=float(r["polarity"]),
                weight=float(r["weight"]),
                domain=r["domain"],
            ))
        keyword_set = {r.keyword.lower() for r in impact_rows}
        universe = {r["symbol"] for r in conn.execute(
            "SELECT symbol FROM stocks_universe"
        ).fetchall()}

        flagged = 0
        skipped = 0
        for sym in symbols:
            headlines = headlines_fetch_fn(sym) or []
            if not headlines:
                skipped += 1
                continue
            current_domains = industry_domains_fn(sym) or set()
            result = detect_news_drift(
                sym, headlines,
                impact_rows=impact_rows,
                keyword_set=keyword_set,
                universe=universe,
                current_industry_domains=current_domains,
            )
            if result.drifted:
                queue_for_review(sym, reason="news_tag_drift", conn=conn)
                flagged += 1
                if log:
                    print(
                        f"  [layer5] {sym} flagged: news dominated by "
                        f"'{result.dominant_domain}' ({result.dominant_share:.0%})"
                    )
        return {"flagged": flagged, "skipped": skipped}
    finally:
        conn.close()


def run_orchestrator(
    symbols: Iterable[str],
    *,
    layers: tuple[str, ...] = ("layer1", "layer2", "layer3", "layer4", "layer5"),
    hash_fetch_fn=None,
    filing_fetch_fn=None,
    returns_fetch_fn=None,
    headlines_fetch_fn=None,
    industry_domains_fn=None,
    log: bool = True,
) -> dict[str, dict]:
    """Convenience: run multiple layers in sequence.

    All five layers are in the default chain. Each layer's wrapper is
    designed to be a CLEAN NO-OP when its upstream data source is missing:

      * layer2 / layer3   skip per-symbol on fetch error
      * layer4            skips per-symbol when returns_fetch_fn returns []
                          (default `_default_returns_fetch` returns [] when
                          Tiingo isn't configured)
      * layer5            skips per-symbol when headlines_fetch_fn returns []
                          (default is the no-op `lambda _: []`)

    So enabling layers 4+5 in the default chain is safe: in environments
    where the data sources aren't wired, they cost only an empty per-symbol
    pass; nothing crashes.
    """
    out: dict[str, dict] = {}
    if "layer1" in layers:
        out["layer1"] = flag_stale_via_decay(log=log)
    if "layer2" in layers:
        out["layer2"] = run_layer_2_hash_diff(symbols, fetch_fn=hash_fetch_fn, log=log)
    if "layer3" in layers:
        out["layer3"] = run_layer_3_filing_trigger(symbols, fetch_fn=filing_fetch_fn, log=log)
    if "layer4" in layers:
        out["layer4"] = run_layer_4_correlation_drift(
            symbols, returns_fetch_fn=returns_fetch_fn, log=log,
        )
    if "layer5" in layers:
        out["layer5"] = run_layer_5_news_drift(
            symbols,
            headlines_fetch_fn=headlines_fetch_fn,
            industry_domains_fn=industry_domains_fn,
            log=log,
        )
    return out
