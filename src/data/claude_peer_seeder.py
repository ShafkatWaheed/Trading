"""Claude-driven peer seeder for stocks the hand-curated seed missed.

For each uncovered Tier A/B stock, asks Claude for 5-7 competitive peers,
validates them against the universe, and inserts as `source='claude_batch'`.
Idempotent — only operates on stocks that currently have zero peer edges.

Run via:
    python -m src.data.claude_peer_seeder --tier A --batch 8 --limit 200

The job is checkpointed: each stock's results are persisted immediately, so
interrupting the run leaves a partial-but-clean state. Re-running picks up
where it left off.
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor

from src.utils.claude_cli import ask_claude_json
from src.utils.db import get_connection, init_db

logger = logging.getLogger(__name__)

_SOURCE = "claude_batch"
_CONFIDENCE = "medium"
_DEFAULT_BATCH = 8
_DEFAULT_WORKERS = 3      # parallel claude subprocesses (bounded to stay polite)


# ── universe queries ───────────────────────────────────────────────


def _uncovered_symbols(conn: sqlite3.Connection, *, tier: str, limit: int) -> list[dict]:
    """Tier-A/B stocks with ZERO peer edges. Ordered by market cap desc so the
    most-important uncovered names get seeded first."""
    rows = conn.execute(
        f"""
        SELECT u.symbol, u.name, u.market_cap, u.tier, i.sector
        FROM stocks_universe u
        LEFT JOIN stock_industry si
            ON si.symbol = u.symbol AND si.is_primary = 1
        LEFT JOIN industries i ON i.code = si.industry_code
        WHERE u.tier IN ({','.join('?' * len(tier.split(',')))})
          AND NOT EXISTS (
            SELECT 1 FROM stock_peers
            WHERE from_symbol = u.symbol OR to_symbol = u.symbol
          )
        ORDER BY u.market_cap DESC NULLS LAST
        LIMIT ?
        """,
        (*tier.split(","), limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _universe_lookup(conn: sqlite3.Connection) -> set[str]:
    return {r["symbol"] for r in conn.execute("SELECT symbol FROM stocks_universe")}


# ── Claude call ────────────────────────────────────────────────────


def _build_prompt(batch: list[dict]) -> str:
    listing = "\n".join(
        f"  - {s['symbol']}  ({s['name'] or '?'}, {s.get('sector') or '—'})"
        for s in batch
    )
    return f"""You are a stock peer analyst. For each ticker below, list its top 5-7
publicly-traded peers — companies that compete in the same product market,
serve similar customers, or are commonly cited together by analysts.

Prefer peers that are large enough to be trading on major US exchanges.
Avoid ETFs, holding companies, foreign listings without ADRs, SPACs, OTC
names, and freshly-IPO'd companies with limited float.

For each peer, assign:
  • similarity ∈ [0.3, 0.95] — higher = tighter competition / closer business
    overlap. 0.85+ for near-duopolies; 0.4-0.6 for adjacent-sector peers.
  • overlap_dimensions — short comma-separated tags like "cloud, ai" or
    "specialty pharma, rare disease".
  • evidence — one short sentence explaining the relationship.

TICKERS:
{listing}

Return a JSON object with exactly this shape:
{{
  "AAPL": {{
    "peers": [
      {{"symbol": "MSFT", "similarity": 0.7, "overlap_dimensions": "cloud, ai", "evidence": "..."}},
      ...
    ]
  }},
  ...
}}

The keys MUST be the input tickers verbatim. Skip any ticker you genuinely
don't recognize by omitting it from the response.
"""


def _judge_batch(batch: list[dict]) -> dict:
    """Ask Claude for peer suggestions for a batch of stocks. Returns the
    parsed dict or {} on failure."""
    prompt = _build_prompt(batch)
    try:
        result = ask_claude_json(prompt, model="haiku", timeout=90, retries=1)
    except Exception as e:
        logger.warning("claude peer suggest failed for batch: %r", e)
        return {}
    return result if isinstance(result, dict) else {}


# ── persistence ────────────────────────────────────────────────────


def _persist_peers(
    conn: sqlite3.Connection,
    *,
    from_sym: str,
    peers: list[dict],
    universe: set[str],
    bidirectional: bool = True,
) -> int:
    """Insert peer edges. Returns count of rows written.

    Validates each suggested peer against the universe. Bidirectional means
    we also write the reverse edge so queries from either side find the
    relationship.
    """
    written = 0
    seen_to: set[str] = set()
    for raw in (peers or []):
        if not isinstance(raw, dict):
            continue
        to_sym = (raw.get("symbol") or "").upper().strip()
        if not to_sym or to_sym == from_sym or to_sym not in universe or to_sym in seen_to:
            continue
        seen_to.add(to_sym)
        try:
            sim = float(raw.get("similarity") or 0)
        except (TypeError, ValueError):
            sim = 0.0
        sim = max(0.3, min(0.95, sim))
        overlap = (raw.get("overlap_dimensions") or "").strip() or None
        evidence = (raw.get("evidence") or "").strip() or None

        for (a, b) in (((from_sym, to_sym),) if not bidirectional
                       else ((from_sym, to_sym), (to_sym, from_sym))):
            conn.execute(
                """
                INSERT INTO stock_peers
                    (from_symbol, to_symbol, similarity, overlap_dimensions,
                     source, confidence, evidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(from_symbol, to_symbol) DO UPDATE SET
                    similarity = excluded.similarity,
                    overlap_dimensions = excluded.overlap_dimensions,
                    source = excluded.source,
                    confidence = excluded.confidence,
                    evidence = excluded.evidence
                WHERE stock_peers.source = ?   -- never override 'hand' rows
                """,
                (a, b, sim, overlap, _SOURCE, _CONFIDENCE, evidence, _SOURCE),
            )
            written += 1
    return written


# ── orchestration ──────────────────────────────────────────────────


def _process_batch(batch: list[dict], universe: set[str]) -> dict:
    """Judge one batch + persist. Returns counts."""
    result = _judge_batch(batch)
    if not result:
        return {"batch_size": len(batch), "claude_responded_for": 0, "rows_written": 0}

    # Each thread gets its own connection (SQLite is per-thread)
    conn = get_connection()
    try:
        responded = 0
        written_total = 0
        for stock in batch:
            sym = stock["symbol"]
            block = result.get(sym) or result.get(sym.upper())
            if not isinstance(block, dict):
                continue
            peers = block.get("peers") or []
            n = _persist_peers(conn, from_sym=sym, peers=peers, universe=universe)
            if n > 0:
                responded += 1
                written_total += n
        conn.commit()
        return {"batch_size": len(batch), "claude_responded_for": responded, "rows_written": written_total}
    finally:
        conn.close()


def run(*, tier: str = "A", batch_size: int = _DEFAULT_BATCH,
        limit: int = 200, workers: int = _DEFAULT_WORKERS) -> dict:
    """Seed peers for uncovered stocks via Claude.

    `tier`: 'A' | 'B' | 'A,B' — which tier to target.
    `batch_size`: stocks per Claude call.
    `limit`: hard cap on stocks to process this run (defends against runaway).
    `workers`: parallel Claude subprocess count.
    """
    init_db()
    conn = get_connection()
    try:
        targets = _uncovered_symbols(conn, tier=tier, limit=limit)
        universe = _universe_lookup(conn)
    finally:
        conn.close()

    if not targets:
        return {"targets": 0, "batches": 0, "stocks_seeded": 0, "rows_written": 0}

    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]
    logger.info("seeding %d uncovered tier-%s stocks across %d batches",
                len(targets), tier, len(batches))

    seeded = 0
    rows = 0
    with ThreadPoolExecutor(max_workers=min(workers, len(batches))) as pool:
        for i, out in enumerate(pool.map(lambda b: _process_batch(b, universe), batches), 1):
            seeded += out["claude_responded_for"]
            rows += out["rows_written"]
            logger.info("batch %d/%d: %d/%d responded, %d rows",
                        i, len(batches), out["claude_responded_for"], out["batch_size"], out["rows_written"])
            print(f"  batch {i}/{len(batches)}: {out['claude_responded_for']}/{out['batch_size']} "
                  f"responded, {out['rows_written']} rows written")

    return {
        "targets": len(targets),
        "batches": len(batches),
        "stocks_seeded": seeded,
        "rows_written": rows,
    }


def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tier", default="A", help="Tier(s) to target — e.g. 'A' or 'A,B'")
    p.add_argument("--batch", type=int, default=_DEFAULT_BATCH, help="Stocks per Claude call")
    p.add_argument("--limit", type=int, default=200, help="Max stocks to process this run")
    p.add_argument("--workers", type=int, default=_DEFAULT_WORKERS, help="Parallel Claude subprocesses")
    args = p.parse_args()

    out = run(tier=args.tier, batch_size=args.batch, limit=args.limit, workers=args.workers)
    print()
    print("=" * 60)
    for k, v in out.items():
        print(f"  {k:18s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
