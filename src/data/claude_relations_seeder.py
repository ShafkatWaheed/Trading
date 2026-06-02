"""Claude-driven substitute + complement edge seeder.

Fills the "Loses share to" (substitute) and "Moves with" (complement) lanes
on the Deep Dive Neighborhood card. For each target stock, asks Claude for
3-5 substitutes + 3-5 complements with reasoning. Validates against the
universe, writes bidirectional edges with `evidence` prefixed `claude_batch`.

Each kind has a distinct economic meaning:
  • substitute  — zero-sum displacement (polarity = -1)
                   if a customer buys X, they don't buy Y
                   (TSLA sub F on EVs; NFLX sub DIS on streaming)
  • complement  — paired demand (polarity = +1)
                   X selling more drives demand for Y
                   (NVDA comp TSM via fab demand; F comp GOOG via Android Auto)

Run via:
    python -m src.data.claude_relations_seeder --tier A --batch 6 --limit 100

Idempotent: ON CONFLICT keeps the highest strength, never downgrades hand seeds.
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

_EVIDENCE_PREFIX = "claude_batch:sub_comp"
_DEFAULT_BATCH = 6
_DEFAULT_WORKERS = 3


# ── target selection ────────────────────────────────────────────────


def _target_symbols(conn: sqlite3.Connection, *, tier: str, limit: int) -> list[dict]:
    """Tier-A/B stocks that currently have FEWER than 2 substitute+complement
    edges combined — i.e. they need filling. Ordered by market_cap desc."""
    tiers = tier.split(",")
    rows = conn.execute(
        f"""
        SELECT u.symbol, u.name, i.sector
        FROM stocks_universe u
        LEFT JOIN stock_industry si
            ON si.symbol = u.symbol AND si.is_primary = 1
        LEFT JOIN industries i ON i.code = si.industry_code
        WHERE u.tier IN ({','.join('?' * len(tiers))})
          AND (
              SELECT COUNT(*) FROM stock_relations
              WHERE (from_symbol = u.symbol OR to_symbol = u.symbol)
                AND relation_type IN ('substitute', 'complement')
          ) < 2
        ORDER BY u.market_cap DESC NULLS LAST
        LIMIT ?
        """,
        (*tiers, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _universe(conn: sqlite3.Connection) -> set[str]:
    return {r["symbol"] for r in conn.execute("SELECT symbol FROM stocks_universe")}


# ── Claude call ─────────────────────────────────────────────────────


def _build_prompt(batch: list[dict]) -> str:
    listing = "\n".join(
        f"  - {s['symbol']}  ({(s.get('name') or '?')[:36]}, {s.get('sector') or '—'})"
        for s in batch
    )
    return f"""You are a stock-relationship analyst. For each ticker below, list:

  • SUBSTITUTES — 3-5 publicly-traded companies whose products/services
    DIRECTLY DISPLACE this stock's business. Zero-sum competition: if a
    customer buys their thing, they don't buy this one.
    Example: TSLA substitutes F (EVs displacing ICE light vehicles).

  • COMPLEMENTS — 3-5 publicly-traded companies whose products/services
    HAVE PAIRED DEMAND with this stock. When this company's sales grow,
    the complement's sales tend to grow too.
    Example: NVDA complements TSM (GPU growth drives TSM fab demand);
             F complements GOOG (Ford cars use Android Automotive).

Strictness rules:
  • Be conservative. Better to give 3 high-confidence pairs than 5 weak ones.
  • DO NOT list pure peers/competitors with no real displacement — that
    relationship is captured separately in the peer graph.
  • DO NOT list pure suppliers or customers — captured separately.
  • Prefer large US-listed companies. Skip foreign listings without ADRs,
    SPACs, OTC names, and small floats.

For each pair, assign:
  • strength ∈ [0.3, 0.85] — higher = tighter displacement / pairing.
    Use 0.75+ only for very clear examples (TSLA-F EVs, MA-V networks).
  • evidence — one short phrase explaining the relationship.

TICKERS:
{listing}

Return JSON with this exact shape:
{{
  "TSLA": {{
    "substitutes": [
      {{"symbol": "F", "strength": 0.65, "evidence": "EVs displacing ICE light vehicles"}},
      ...
    ],
    "complements": [
      {{"symbol": "ALB", "strength": 0.55, "evidence": "EV growth drives lithium demand"}},
      ...
    ]
  }},
  ...
}}

Keys MUST be the input tickers verbatim. Skip tickers you don't recognize.
"""


def _judge_batch(batch: list[dict]) -> dict:
    try:
        result = ask_claude_json(_build_prompt(batch), model="haiku", timeout=90, retries=1)
    except Exception as e:
        logger.warning("claude relations suggest failed: %r", e)
        return {}
    return result if isinstance(result, dict) else {}


# ── persistence ─────────────────────────────────────────────────────


def _persist(
    conn: sqlite3.Connection,
    *,
    from_sym: str,
    pairs: list[dict],
    relation_type: str,    # 'substitute' | 'complement'
    polarity: float,
    universe: set[str],
) -> int:
    """Insert relations. Returns rows written.

    Sym + relation_type are symmetric — write BOTH directions so neighbor
    queries from either side return the edge. Skip self-loops and non-universe.
    """
    written = 0
    seen: set[str] = set()
    for raw in (pairs or []):
        if not isinstance(raw, dict):
            continue
        to_sym = (raw.get("symbol") or "").upper().strip()
        if not to_sym or to_sym == from_sym or to_sym not in universe or to_sym in seen:
            continue
        seen.add(to_sym)
        try:
            strength = float(raw.get("strength") or 0)
        except (TypeError, ValueError):
            strength = 0.0
        strength = max(0.30, min(0.85, strength))
        evidence_text = (raw.get("evidence") or "").strip()
        evidence = f"{_EVIDENCE_PREFIX} | {evidence_text}" if evidence_text else _EVIDENCE_PREFIX

        # Bidirectional insert — both substitute and complement are symmetric
        for (a, b) in ((from_sym, to_sym), (to_sym, from_sym)):
            conn.execute(
                """
                INSERT INTO stock_relations
                    (from_symbol, to_symbol, relation_type, strength, polarity, evidence)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(from_symbol, to_symbol, relation_type) DO UPDATE SET
                    strength = MAX(stock_relations.strength, excluded.strength),
                    evidence = excluded.evidence
                WHERE stock_relations.evidence LIKE 'claude_batch%'
                """,
                (a, b, relation_type, strength, polarity, evidence),
            )
            written += 1
    return written


def _process_batch(batch: list[dict], universe: set[str]) -> dict:
    result = _judge_batch(batch)
    if not result:
        return {"batch_size": len(batch), "responded_for": 0, "rows_written": 0}

    conn = get_connection()
    try:
        responded = 0
        written = 0
        for stock in batch:
            sym = stock["symbol"]
            block = result.get(sym) or result.get(sym.upper())
            if not isinstance(block, dict):
                continue
            subs = _persist(conn, from_sym=sym, pairs=block.get("substitutes") or [],
                            relation_type="substitute", polarity=-1.0, universe=universe)
            comps = _persist(conn, from_sym=sym, pairs=block.get("complements") or [],
                              relation_type="complement", polarity=1.0, universe=universe)
            n = subs + comps
            if n > 0:
                responded += 1
                written += n
        conn.commit()
        return {"batch_size": len(batch), "responded_for": responded, "rows_written": written}
    finally:
        conn.close()


# ── orchestration ───────────────────────────────────────────────────


def run(*, tier: str = "A", batch_size: int = _DEFAULT_BATCH,
        limit: int = 100, workers: int = _DEFAULT_WORKERS) -> dict:
    init_db()
    conn = get_connection()
    try:
        targets = _target_symbols(conn, tier=tier, limit=limit)
        universe = _universe(conn)
    finally:
        conn.close()

    if not targets:
        return {"targets": 0, "batches": 0, "stocks_seeded": 0, "rows_written": 0}

    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]
    logger.info("seeding sub/comp for %d tier-%s stocks across %d batches",
                len(targets), tier, len(batches))

    seeded = 0
    rows = 0
    with ThreadPoolExecutor(max_workers=min(workers, len(batches))) as pool:
        for i, out in enumerate(pool.map(lambda b: _process_batch(b, universe), batches), 1):
            seeded += out["responded_for"]
            rows += out["rows_written"]
            logger.info("batch %d/%d: %d/%d responded, %d rows",
                        i, len(batches), out["responded_for"], out["batch_size"], out["rows_written"])
            print(f"  batch {i}/{len(batches)}: {out['responded_for']}/{out['batch_size']} "
                  f"responded, {out['rows_written']} rows")
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
    p.add_argument("--batch", type=int, default=_DEFAULT_BATCH)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--workers", type=int, default=_DEFAULT_WORKERS)
    args = p.parse_args()

    out = run(tier=args.tier, batch_size=args.batch, limit=args.limit, workers=args.workers)
    print()
    print("=" * 60)
    for k, v in out.items():
        print(f"  {k:18s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
