"""Seed `institutions` with well-known active hedge funds + active managers,
then run the 13F historical backfill so they show up in the smart-money tape.

Idempotent — uses ON CONFLICT to skip rows already present. Safe to re-run.

Usage:
    python -m scripts.seed_active_funds                # insert + verify CIKs only
    python -m scripts.seed_active_funds --backfill     # also run historical backfill
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time

import httpx

from src.utils.db import get_connection
from src.data.sec_13f_loader import SEC_HEADERS, _list_13f_filings, process_institution_history


# Curated list of active managers / hedge funds that file 13F-HR.
# Format: (cik, display_name, type)
# type ∈ {hedge_fund, active_mgr, sovereign, pension}
ACTIVE_FUNDS: list[tuple[str, str, str]] = [
    # Hedge funds
    ("1040273", "Third Point LLC",                          "hedge_fund"),
    ("1418814", "ValueAct Capital Management",              "hedge_fund"),
    ("1079114", "Greenlight Capital Inc",                   "hedge_fund"),
    ("1029160", "Soros Fund Management LLC",                "hedge_fund"),
    ("1656456", "Appaloosa LP",                             "hedge_fund"),
    ("1271879", "Glenview Capital Management",              "hedge_fund"),
    ("1273087", "Millennium Management LLC",                "hedge_fund"),
    ("1603466", "Point72 Asset Management LP",              "hedge_fund"),
    ("1009207", "D. E. Shaw & Co. Inc",                     "hedge_fund"),
    ("1167557", "AQR Capital Management LLC",               "hedge_fund"),
    ("1495796", "Brevan Howard Capital Management LP",      "hedge_fund"),
    ("1404982", "Marshall Wace LLP",                        "hedge_fund"),
    ("1387554", "Hound Partners LLC",                       "hedge_fund"),
    # Active managers
    ("1112520", "Akre Capital Management LLC",              "active_mgr"),
    ("1697748", "Ark Investment Management LLC",            "active_mgr"),
]


def _verify_cik_files_13f(cik: str) -> tuple[bool, int]:
    """Hit SEC EDGAR submissions JSON to confirm this CIK actually files 13F-HR.
    Returns (is_filer, latest_filing_count). Skips inserts for non-filers.
    """
    try:
        filings = _list_13f_filings(cik)
        return (len(filings) > 0, len(filings))
    except Exception:
        return (False, 0)


def insert_funds(conn: sqlite3.Connection, *, verify: bool = True) -> list[str]:
    """INSERT OR IGNORE the funds. Returns the list of CIKs successfully added
    (or already present). Skips CIKs that don't appear to file 13F-HR (likely
    wrong CIK number).
    """
    inserted: list[str] = []
    cur = conn.cursor()
    for cik, name, ftype in ACTIVE_FUNDS:
        # Verify the CIK looks legit before inserting — saves us from
        # poisoning institutions with junk that then errors during backfill.
        if verify:
            ok, n_filings = _verify_cik_files_13f(cik)
            time.sleep(0.15)  # be polite to SEC EDGAR
            if not ok:
                print(f"  SKIP cik={cik:>10s} {name:42s} — no 13F-HR filings found on EDGAR")
                continue
            print(f"  ✓    cik={cik:>10s} {name:42s} — {n_filings} 13F-HRs on EDGAR")
        # ON CONFLICT IGNORE — never overwrite existing rows
        cur.execute(
            """
            INSERT OR IGNORE INTO institutions (cik, name, type, total_aum, last_updated)
            VALUES (?, ?, ?, NULL, datetime('now'))
            """,
            (cik, name, ftype),
        )
        if cur.rowcount > 0:
            print(f"       inserted")
        else:
            print(f"       already in DB (skipped)")
        inserted.append(cik)
    conn.commit()
    return inserted


def run_backfill_for(ciks: list[str], quarters: int = 4) -> dict:
    """Run process_institution_history for each newly-added CIK."""
    succeeded = 0
    failed = 0
    snapshots = 0
    rows = 0
    for cik in ciks:
        print(f"  [backfill] cik={cik}…", flush=True)
        out = process_institution_history(cik, quarters=quarters)
        if out.get("error") and not out.get("snapshots_written"):
            failed += 1
            print(f"    -> failed: {out.get('error')}", flush=True)
        else:
            succeeded += 1
            snapshots += out["snapshots_written"]
            rows += out["rows_written"]
            print(f"    -> {out['snapshots_written']} snapshots, {out['rows_written']} rows", flush=True)
    return {
        "processed": len(ciks),
        "succeeded": succeeded,
        "failed": failed,
        "snapshots_written": snapshots,
        "rows_written": rows,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backfill", action="store_true",
                   help="Also run 13F historical backfill for newly-inserted CIKs")
    p.add_argument("--no-verify", action="store_true",
                   help="Skip the CIK existence check (insert all unconditionally)")
    p.add_argument("--quarters", type=int, default=4,
                   help="How many historical quarters to backfill per CIK")
    args = p.parse_args()

    conn = get_connection()
    try:
        print(f"Inserting {len(ACTIVE_FUNDS)} active funds (idempotent — existing rows skipped):")
        ciks = insert_funds(conn, verify=not args.no_verify)
        print(f"\n{len(ciks)} CIKs ready in the institutions table.\n")
    finally:
        conn.close()

    if args.backfill and ciks:
        print(f"Running 13F historical backfill ({args.quarters} quarters per CIK)…")
        result = run_backfill_for(ciks, quarters=args.quarters)
        print()
        for k, v in result.items():
            print(f"  {k:20s}: {v}")
        return 0 if result["failed"] == 0 else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
