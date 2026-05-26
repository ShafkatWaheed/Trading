"""Schema migration: add concentration_pct + source_filing_date + last_verified_at to stock_relations.

Idempotent — safe to run repeatedly. SQLite doesn't support ADD COLUMN IF NOT
EXISTS, so we introspect the table first and skip columns that already exist.

Usage:
    python scripts/migrate_concentration_pct.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `src.*` importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.db import get_connection, init_db


NEW_COLUMNS: list[tuple[str, str]] = [
    # (column, SQL type) — all nullable; existing 10k_mined rows get NULL until re-mined.
    ("concentration_pct",   "REAL"),     # disclosed customer concentration % (10..100)
    ("source_filing_date",  "TEXT"),     # filing date the % was extracted from (ISO 8601)
    ("last_verified_at",    "TEXT"),     # when this row was last refreshed (ISO 8601)
]


def main() -> int:
    init_db()  # ensure base schema exists
    conn = get_connection()
    try:
        existing = {
            r[1] for r in conn.execute("PRAGMA table_info(stock_relations)").fetchall()
        }
        added: list[str] = []
        for col, typ in NEW_COLUMNS:
            if col in existing:
                continue
            conn.execute(f"ALTER TABLE stock_relations ADD COLUMN {col} {typ}")
            added.append(col)
        conn.commit()
        if added:
            print(f"Added columns: {added}")
        else:
            print("No-op: all target columns already present.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
