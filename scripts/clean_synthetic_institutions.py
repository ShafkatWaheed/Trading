"""Delete synthetic-CIK institutions and their orphan holdings.

The original seeds/institutions.csv shipped with 49 placeholder CIKs in the
10000xxx range (made-up identifiers for famous funds like Citadel,
Renaissance, Fidelity, etc.). They were intended as a "names list" but
were treated as real CIKs by the 13F loader, which then failed against
SEC EDGAR for all 49.

Per CLAUDE.md's data-integrity rule ("never use fake / synthetic data"),
this script removes them cleanly. After running, only institutions with
real SEC CIKs remain. To re-add the famous funds with their REAL CIKs,
run scripts/discover_real_ciks.py separately (it queries SEC's filer
search and never invents values).

Idempotent: re-running is a no-op after the first cleanup.

Usage:
    python -m scripts.clean_synthetic_institutions          # dry run
    python -m scripts.clean_synthetic_institutions --apply  # actually delete
"""
from __future__ import annotations

import argparse
import sys

from src.utils.db import get_connection, init_db


def _synthetic_ciks(conn) -> list[str]:
    """Synthetic CIKs are 8+ digits; real SEC CIKs are at most 7 digits."""
    return [r["cik"] for r in conn.execute(
        "SELECT cik FROM institutions WHERE LENGTH(cik) >= 8"
    )]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true",
                   help="Actually delete. Without this flag, only previews.")
    args = p.parse_args()

    init_db()
    conn = get_connection()
    try:
        synthetic = _synthetic_ciks(conn)
        if not synthetic:
            print("Nothing to do — no synthetic CIKs found. Already clean.")
            return 0

        placeholders = ",".join("?" * len(synthetic))
        orphan_count = conn.execute(
            f"SELECT COUNT(*) FROM institution_holdings WHERE cik IN ({placeholders})",
            synthetic,
        ).fetchone()[0]

        print(f"Synthetic institutions to delete: {len(synthetic)}")
        sample = conn.execute(
            f"SELECT cik, name FROM institutions WHERE cik IN ({placeholders}) "
            "ORDER BY name LIMIT 10",
            synthetic,
        ).fetchall()
        for r in sample:
            print(f"  cik={r['cik']:>10}  {r['name']}")
        if len(synthetic) > 10:
            print(f"  ... ({len(synthetic) - 10} more)")
        print(f"\nOrphan institution_holdings rows to delete: {orphan_count}")

        if not args.apply:
            print("\nDry run — pass --apply to actually delete.")
            return 0

        # Delete holdings first (FK-style consistency)
        conn.execute(
            f"DELETE FROM institution_holdings WHERE cik IN ({placeholders})",
            synthetic,
        )
        conn.execute(
            f"DELETE FROM institutions WHERE cik IN ({placeholders})",
            synthetic,
        )
        conn.commit()

        print("\nDeleted.")
        print(f"  institutions remaining:        "
              f"{conn.execute('SELECT COUNT(*) FROM institutions').fetchone()[0]}")
        print(f"  institution_holdings remaining: "
              f"{conn.execute('SELECT COUNT(*) FROM institution_holdings').fetchone()[0]}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
