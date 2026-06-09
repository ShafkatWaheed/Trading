"""One-off: backfill `stocks_universe.name` for nameless rows.

Tier B/C symbols were inserted by the ETF `index_loader` without names (the
holdings CSVs only carry tickers). This fills them from the canonical Nasdaq
Trader symbol directory (nasdaqlisted.txt + otherlisted.txt — free, no key),
lightly cleaned to the curated tier-A style. Only empty names are touched;
existing names are never overwritten.

Committed for auditability (CLAUDE.md: real-DB mutations live in scripts/).

Run: .venv/bin/python -m scripts.backfill_universe_names
"""
from __future__ import annotations

import logging

from src.data.nasdaq_listings_loader import (
    backfill_universe_names,
    build_name_map,
)
from src.utils.db import get_connection


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    name_map = build_name_map(force=True)
    print(f"Nasdaq directory: {len(name_map)} symbol→name entries")

    res = backfill_universe_names(name_map)
    print(
        f"backfill: filled {res['filled']} of {res['total_missing']} nameless rows; "
        f"{res['remaining']} still missing"
    )

    if res["remaining"]:
        conn = get_connection()
        try:
            sample = conn.execute(
                "SELECT symbol, tier FROM stocks_universe "
                "WHERE name IS NULL OR TRIM(name) = '' ORDER BY symbol LIMIT 20"
            ).fetchall()
        finally:
            conn.close()
        print(
            "still missing (sample, likely non-US / delisted): "
            + ", ".join(f"{r['symbol']}({r['tier']})" for r in sample)
        )


if __name__ == "__main__":
    main()
