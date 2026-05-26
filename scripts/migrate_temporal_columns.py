"""Schema migration: add effective_from + effective_to to stock_relations.

Idempotent. Required by CLAUDE.md's no-lookahead rule once edges drive
backtests: a relation only counts for date `t` if effective_from <= t and
(effective_to IS NULL OR effective_to > t).

Conventions:
    effective_from = NULL  ⇒  "always valid going back"
    effective_to   = NULL  ⇒  "still in effect"
    Both NULL              ⇒  no temporal constraint (current default for
                              all existing hand-seeded rows)

Usage:
    python scripts/migrate_temporal_columns.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.db import get_connection, init_db


NEW_COLUMNS: list[tuple[str, str]] = [
    ("effective_from", "TEXT"),    # ISO 8601 date — when the relation started
    ("effective_to",   "TEXT"),    # ISO 8601 date — when it ended (NULL = still in effect)
]


def main() -> int:
    init_db()
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
