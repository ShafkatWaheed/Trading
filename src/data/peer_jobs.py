"""Resumable per-industry peer-ranking jobs powered by Claude (CLI subprocess).

The Tier A spine ships hand-curated peer edges via `peer_seed_loader.py`.
Tier B / C / D get peers via Claude — for each industry, Claude gets the
list of stocks tagged with that industry and ranks each one's top peers
within the same list. The result lands in `stock_peers` with
`source='claude_batch'` and tier-derived confidence labels.

Why per-industry batching?
    * Within-industry peers are 80% of the useful peer signal at this scale.
    * Cross-industry peers for Tier A are hand-curated separately.
    * Constraining each call to one industry keeps the prompt short
      (under 30 stocks) and the response easy to validate.

Why resumable?
    * The Claude CLI runs against the user's subscription, not an API key.
      Long bulk runs may hit subscription budget windows. The `peer_jobs`
      table is the persistent ledger — `status='pending'` rows can be
      picked up by a later session without redoing finished work.

CLI:
    python -m src.data.peer_jobs --tier B,C,D
    python -m src.data.peer_jobs --industry Semiconductors
    python -m src.data.peer_jobs --status pending --limit 10
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from src.utils.claude_cli import ask_claude_json
from src.utils.db import get_connection, init_db


# ── confidence by tier ──────────────────────────────────────────


# Maps a stock's tier to the confidence label we tag its Claude-derived edges.
# Tier A is hand-curated, never auto-ranked.
TIER_CONFIDENCE: dict[str, str] = {
    "B": "medium",
    "C": "low",
    "D": "low",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── prompt construction ─────────────────────────────────────────


PEER_RANKING_PROMPT = """\
You are ranking peer / competitor relationships among publicly-traded stocks.
Given the list below of companies in the same industry, for EACH company
output its 5 closest peers from this same list (only — no external companies).

Return ONLY valid JSON of the form:

[
  {{
    "symbol": "AAA",
    "peers": [
      {{"sym": "BBB", "reason": "<≤20-word rationale>"}},
      ...
    ]
  }},
  ...
]

Rules:
- ONLY pick peers from the input list.
- A company should NOT list itself as a peer.
- Reason must be a concise comparison of business overlap.
- Skip a company entirely if it has fewer than 2 plausible peers in the list.

Industry: {industry}

Companies (symbol — name):
{listing}
"""


def _build_prompt(industry: str, stocks: list[tuple[str, str]]) -> str:
    """`stocks` is a list of (symbol, name) tuples."""
    listing = "\n".join(f"  {sym} — {name}" for sym, name in stocks)
    return PEER_RANKING_PROMPT.format(industry=industry, listing=listing)


# ── per-industry processing ─────────────────────────────────────


@dataclass
class PeerJobResult:
    industry: str
    tier: str
    symbols_in_industry: int
    edges_written: int
    error: str | None = None


def _stocks_in_industry_at_tier(
    conn: sqlite3.Connection,
    industry_code: str,
    tier: str,
) -> list[tuple[str, str]]:
    """Return [(symbol, name), ...] for stocks tagged with this industry at this tier."""
    rows = conn.execute(
        """
        SELECT u.symbol, COALESCE(u.name, u.symbol) AS name
        FROM stock_industry si
        JOIN stocks_universe u ON u.symbol = si.symbol
        WHERE si.industry_code = ?
          AND u.tier = ?
        ORDER BY u.market_cap DESC NULLS LAST, u.symbol
        """,
        (industry_code, tier),
    ).fetchall()
    return [(r["symbol"], r["name"]) for r in rows]


def _ensure_job_row(
    conn: sqlite3.Connection, industry: str, tier: str
) -> None:
    conn.execute(
        """
        INSERT INTO peer_jobs (industry_code, tier, status)
        VALUES (?, ?, 'pending')
        ON CONFLICT(industry_code, tier) DO NOTHING
        """,
        (industry, tier),
    )


def _mark(
    conn: sqlite3.Connection,
    industry: str,
    tier: str,
    *,
    status: str,
    symbols_processed: int = 0,
    edges_written: int = 0,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE peer_jobs SET
            status = ?,
            last_attempt = ?,
            symbols_processed = ?,
            edges_written = ?,
            error = ?
        WHERE industry_code = ? AND tier = ?
        """,
        (status, _now(), symbols_processed, edges_written, error, industry, tier),
    )


def _write_claude_edges(
    conn: sqlite3.Connection,
    parsed: list[dict],
    *,
    valid_symbols: set[str],
    tier: str,
) -> int:
    """Write `stock_peers` rows from a parsed Claude response.

    Validates: (1) symbols in `valid_symbols`, (2) self-loops dropped,
    (3) caps at 5 peers per source.
    Returns count of (from, to) rows written.
    """
    confidence = TIER_CONFIDENCE.get(tier, "low")
    written = 0
    if not isinstance(parsed, list):
        return 0
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        from_sym = (entry.get("symbol") or "").upper()
        if from_sym not in valid_symbols:
            continue
        peer_list = entry.get("peers") or []
        if not isinstance(peer_list, list):
            continue
        for p in peer_list[:5]:
            if not isinstance(p, dict):
                continue
            to_sym = (p.get("sym") or "").upper()
            if not to_sym or to_sym == from_sym or to_sym not in valid_symbols:
                continue
            reason = (p.get("reason") or "")[:240]
            conn.execute(
                """
                INSERT INTO stock_peers
                    (from_symbol, to_symbol, similarity, overlap_dimensions,
                     source, confidence, evidence)
                VALUES (?, ?, ?, NULL, 'claude_batch', ?, ?)
                ON CONFLICT(from_symbol, to_symbol) DO UPDATE SET
                    similarity = MAX(stock_peers.similarity, excluded.similarity),
                    source = CASE
                        WHEN stock_peers.source = 'hand' THEN stock_peers.source
                        ELSE excluded.source END,
                    confidence = CASE
                        WHEN stock_peers.source = 'hand' THEN stock_peers.confidence
                        ELSE excluded.confidence END,
                    evidence = COALESCE(stock_peers.evidence, excluded.evidence)
                """,
                # Default similarity for Claude-ranked peers: 0.6 (medium) - lower
                # than hand-curated highs (0.85+) but high enough to surface in
                # peer queries. Future: ask Claude for a similarity score too.
                (from_sym, to_sym, 0.6, confidence, reason),
            )
            written += 1
    return written


def process_industry(
    industry_code: str,
    tier: str,
    *,
    model: str = "haiku",
    conn: sqlite3.Connection | None = None,
) -> PeerJobResult:
    """Process one (industry, tier) batch end-to-end.

    Marks the job row 'in_progress' before the LLM call, then 'done' or
    'failed' after. Safe to interrupt — the next run picks up pending jobs.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    _ensure_job_row(conn, industry_code, tier)
    conn.commit()

    try:
        stocks = _stocks_in_industry_at_tier(conn, industry_code, tier)
        if len(stocks) < 2:
            _mark(conn, industry_code, tier, status="done",
                  symbols_processed=len(stocks), edges_written=0,
                  error="fewer than 2 stocks; nothing to rank")
            conn.commit()
            return PeerJobResult(industry_code, tier, len(stocks), 0,
                                 error="fewer than 2 stocks")

        _mark(conn, industry_code, tier, status="in_progress")
        conn.commit()

        prompt = _build_prompt(industry_code, stocks)
        result = ask_claude_json(prompt, model=model, retries=2)
        if result is None:
            _mark(conn, industry_code, tier, status="failed",
                  symbols_processed=len(stocks), edges_written=0,
                  error="claude returned no parseable JSON")
            conn.commit()
            return PeerJobResult(industry_code, tier, len(stocks), 0,
                                 error="claude failed")

        valid_symbols = {sym for sym, _ in stocks}
        edges = _write_claude_edges(
            conn, result, valid_symbols=valid_symbols, tier=tier
        )

        _mark(conn, industry_code, tier, status="done",
              symbols_processed=len(stocks), edges_written=edges)
        conn.commit()
        return PeerJobResult(industry_code, tier, len(stocks), edges)
    finally:
        if own_conn:
            conn.close()


# ── batch runner ────────────────────────────────────────────────


def discover_industries_to_rank(
    conn: sqlite3.Connection,
    *,
    tiers: list[str],
) -> list[tuple[str, str]]:
    """Return [(industry, tier), ...] pairs that have ≥2 stocks at that tier
    and are NOT yet recorded as 'done' in peer_jobs."""
    placeholders = ",".join("?" * len(tiers))
    rows = conn.execute(
        f"""
        SELECT si.industry_code AS industry, u.tier AS tier, COUNT(*) AS n
        FROM stock_industry si
        JOIN stocks_universe u ON u.symbol = si.symbol
        WHERE u.tier IN ({placeholders})
        GROUP BY si.industry_code, u.tier
        HAVING n >= 2
        """,
        tiers,
    ).fetchall()
    out = []
    for r in rows:
        # Skip industries already 'done' at this tier
        existing = conn.execute(
            "SELECT status FROM peer_jobs WHERE industry_code = ? AND tier = ?",
            (r["industry"], r["tier"]),
        ).fetchone()
        if existing and existing["status"] == "done":
            continue
        out.append((r["industry"], r["tier"]))
    return out


def detect_drift_and_reset(conn: sqlite3.Connection) -> int:
    """Reset 'done' peer_jobs rows whose claimed edges have disappeared.

    Industries are marked 'done' with an `edges_written` count, but those
    edges live in `stock_peers` and can be deleted by other operations
    (e.g. an over-scoped test cleanup wiped 5,285 edges historically).
    When the ledger says >0 edges but the actual count is 0, the ledger
    has drifted from reality — reset to 'pending' so the next run rebuilds
    those edges.

    Returns the number of rows reset.
    """
    rows = conn.execute(
        """
        SELECT industry_code, tier, edges_written
        FROM peer_jobs
        WHERE status = 'done' AND edges_written > 0
        """
    ).fetchall()

    reset = 0
    for r in rows:
        # Count actual claude_batch edges where the `from_symbol` is tagged
        # with this industry and at this tier — these are the edges this job
        # would have written.
        actual = conn.execute(
            """
            SELECT COUNT(*) FROM stock_peers sp
            JOIN stock_industry si ON si.symbol = sp.from_symbol
            JOIN stocks_universe u ON u.symbol = sp.from_symbol
            WHERE sp.source = 'claude_batch'
              AND si.industry_code = ?
              AND u.tier = ?
            """,
            (r["industry_code"], r["tier"]),
        ).fetchone()[0]
        if actual == 0:
            conn.execute(
                "UPDATE peer_jobs SET status='pending', last_attempt=? "
                "WHERE industry_code=? AND tier=?",
                (_now(), r["industry_code"], r["tier"]),
            )
            reset += 1
    if reset:
        conn.commit()
    return reset


def run_pending_jobs(
    *,
    tiers: list[str] | None = None,
    industry: str | None = None,
    limit: int | None = None,
    model: str = "haiku",
    log: bool = True,
) -> dict[str, int]:
    """Process pending peer-ranking jobs.

    Args:
        tiers: list of tiers to process (default ['B', 'C', 'D'] — never 'A')
        industry: optional single industry to focus on
        limit: max jobs to process this run

    Returns counts: {processed, succeeded, failed, edges_written, drift_reset}.
    """
    init_db()
    if tiers is None:
        tiers = ["B", "C", "D"]
    # Tier A is hand-curated; never auto-rank.
    tiers = [t for t in tiers if t != "A"]

    conn = get_connection()
    try:
        # Heal ledger drift before discovering pending work — keeps the
        # Refresh button able to rescue stocks whose edges got wiped.
        drift_reset = detect_drift_and_reset(conn)
        if log and drift_reset:
            print(f"  [peer_jobs] drift detected — reset {drift_reset} stale 'done' rows to pending")

        if industry:
            jobs = [(industry, t) for t in tiers]
        else:
            jobs = discover_industries_to_rank(conn, tiers=tiers)

        if limit is not None:
            jobs = jobs[:limit]
    finally:
        conn.close()

    processed = 0
    succeeded = 0
    failed = 0
    edges_total = 0

    for industry_code, tier in jobs:
        if log:
            print(f"  [peer_jobs] processing ({industry_code}, {tier})…")
        result = process_industry(industry_code, tier, model=model)
        processed += 1
        if result.error:
            failed += 1
            if log:
                print(f"    ✗ {result.error}")
        else:
            succeeded += 1
            edges_total += result.edges_written
            if log:
                print(f"    ✓ {result.edges_written} edges from {result.symbols_in_industry} stocks")

    return {
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "edges_written": edges_total,
        "drift_reset": drift_reset,
    }


# ── CLI ─────────────────────────────────────────────────────────


def _main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tier", default="B,C,D", help="Comma-separated tiers (default: B,C,D)")
    p.add_argument("--industry", help="Single industry name to process")
    p.add_argument("--model", default="haiku", help="claude --model arg (default: haiku)")
    p.add_argument("--limit", type=int, default=None, help="Cap jobs this run")
    args = p.parse_args()

    tiers = [t.strip().upper() for t in args.tier.split(",") if t.strip()]
    out = run_pending_jobs(
        tiers=tiers,
        industry=args.industry,
        limit=args.limit,
        model=args.model,
    )
    print()
    for k, v in out.items():
        print(f"  {k:20s}: {v}")
    return 0 if out["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(_main())
