"""Schema migration: add composite_confidence to stock_relations.

Stores a single 0..1 confidence value derived from how many independent
evidence channels support each edge (hand seed, 10-K disclosure with
quantified %, named-but-not-quantified 10-K, etc.). Recomputed by the
`composite_confidence` refresh job; stored so consumers don't have to
recompute on every read.

Idempotent.

Usage:
    python scripts/migrate_composite_confidence.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.db import get_connection, init_db


def main() -> int:
    init_db()
    conn = get_connection()
    try:
        existing = {
            r[1] for r in conn.execute("PRAGMA table_info(stock_relations)").fetchall()
        }
        if "composite_confidence" in existing:
            print("No-op: composite_confidence already present.")
            return 0
        conn.execute(
            "ALTER TABLE stock_relations ADD COLUMN composite_confidence REAL"
        )
        conn.commit()
        print("Added column: composite_confidence")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
