"""Universe loader — populates stocks_universe + stock_industry from seeds and (later) network sources.

Phase 1 (this file as of week 1 day 1): backfills the hand-curated Tier A
stocks from `tier_a_seed.py` into `stocks_universe` and `stock_industry`.

Phase 2 (week 1 day 2-3, separate functions): pulls Russell/S&P/TSX index
memberships from ETF holdings + TSX/NASDAQ exchange exports to fill in Tier
B/C/D. Those are added as separate functions when the network-side code
lands.

This module is the single chokepoint for "where does the universe come from."
Anything that touches stocks_universe or stock_industry should go through here.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable

from src.data.tier_a_seed import TIER_A
from src.utils.db import get_connection, init_db


def load_tier_a(conn: sqlite3.Connection | None = None) -> dict[str, int]:
    """Insert/upsert the hand-curated Tier A stocks.

    Idempotent — running this twice keeps the existing rows up to date with
    the latest seed (UPSERT on conflict).

    Returns a counts dict: {"stocks_inserted": N, "stocks_updated": M, "industries_linked": K}.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    try:
        # Snapshot existing tier-A rows so we can report inserts vs updates.
        existing_a = {
            r["symbol"]
            for r in conn.execute("SELECT symbol FROM stocks_universe WHERE tier='A'").fetchall()
        }

        for symbol, name, sector, industry, exchange, country in TIER_A:
            # 1) industry row (idempotent)
            conn.execute(
                """
                INSERT INTO industries (code, sector)
                VALUES (?, ?)
                ON CONFLICT(code) DO UPDATE SET sector = excluded.sector
                """,
                (industry, sector),
            )

            # 2) stocks_universe row
            conn.execute(
                """
                INSERT INTO stocks_universe
                    (symbol, name, tier, exchange, country, in_sp500, source)
                VALUES (?, ?, 'A', ?, ?, 1, 'tier_a_seed')
                ON CONFLICT(symbol) DO UPDATE SET
                    name = excluded.name,
                    tier = 'A',
                    exchange = excluded.exchange,
                    country = excluded.country,
                    source = 'tier_a_seed'
                """,
                (symbol, name, exchange, country),
            )

            # 3) primary industry mapping
            conn.execute(
                """
                INSERT INTO stock_industry
                    (symbol, industry_code, weight, is_primary, source)
                VALUES (?, ?, 1.0, 1, 'tier_a_seed')
                ON CONFLICT(symbol, industry_code) DO UPDATE SET
                    weight = 1.0,
                    is_primary = 1,
                    source = 'tier_a_seed'
                """,
                (symbol, industry),
            )

        conn.commit()

        new_a = {
            r["symbol"]
            for r in conn.execute("SELECT symbol FROM stocks_universe WHERE tier='A'").fetchall()
        }
        inserted = len(new_a - existing_a)
        updated = len(existing_a & new_a)
        industry_links = conn.execute(
            "SELECT COUNT(*) FROM stock_industry WHERE source='tier_a_seed'"
        ).fetchone()[0]

        return {
            "stocks_inserted": inserted,
            "stocks_updated": updated,
            "industries_linked": industry_links,
        }
    finally:
        if own_conn:
            conn.close()


def get_universe(tier: Iterable[str] | None = None) -> list[dict]:
    """Read the full universe (or a tier slice) from stocks_universe.

    Args:
        tier: optional iterable of tiers to filter by (e.g. ['A','B']).
              None returns everything.
    """
    init_db()
    conn = get_connection()
    try:
        if tier is None:
            rows = conn.execute(
                "SELECT * FROM stocks_universe ORDER BY tier, symbol"
            ).fetchall()
        else:
            tiers = list(tier)
            placeholders = ",".join("?" * len(tiers))
            rows = conn.execute(
                f"SELECT * FROM stocks_universe WHERE tier IN ({placeholders}) ORDER BY tier, symbol",
                tiers,
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def universe_counts() -> dict[str, int]:
    """Return per-tier and total counts. Useful for dashboards / smoke checks."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT tier, COUNT(*) FROM stocks_universe GROUP BY tier"
        ).fetchall()
        out: dict[str, int] = {row[0]: row[1] for row in rows}
        out["total"] = sum(out.values()) if out else 0
        return out
    finally:
        conn.close()
