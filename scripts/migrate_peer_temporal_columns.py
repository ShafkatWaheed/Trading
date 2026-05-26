"""Schema migration: add effective_from + effective_to to stock_peers.

Mirrors scripts/migrate_temporal_columns.py for the peer-edge table.
Idempotent. Required so peer-graph traversals can also honor the
no-lookahead rule via `as_of=`.

Usage:
    python scripts/migrate_peer_temporal_columns.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.db import get_connection, init_db


NEW_COLUMNS: list[tuple[str, str]] = [
    ("effective_from", "TEXT"),
    ("effective_to",   "TEXT"),
]


def main() -> int:
    init_db()
    conn = get_connection()
    try:
        existing = {
            r[1] for r in conn.execute("PRAGMA table_info(stock_peers)").fetchall()
        }
        added: list[str] = []
        for col, typ in NEW_COLUMNS:
            if col in existing:
                continue
            conn.execute(f"ALTER TABLE stock_peers ADD COLUMN {col} {typ}")
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
