"""Look up real SEC CIKs for institutional investors via EDGAR full-text search.

Use to find verified CIKs for institutions you want to add to seeds/institutions.csv,
WITHOUT inventing placeholder values. The script queries SEC EDGAR's full-text
search and returns the most-frequent filer CIK for 13F-HR filings matching
each name. Ambiguous results (multiple distinct CIKs match equally) are
reported but not auto-resolved — you decide whether to add them.

This script NEVER invents CIKs. Names with no match or ambiguous matches
are left for manual review.

Usage:
    # Look up CIKs for the standard list of major US institutional investors
    python -m scripts.discover_real_ciks

    # Look up CIKs for custom names
    python -m scripts.discover_real_ciks --name "Fidelity" --name "Renaissance"

    # After review, write resolved names to seeds/institutions_proposed.csv
    python -m scripts.discover_real_ciks --write seeds/institutions_proposed.csv
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter

import httpx

# Polite SEC headers — EDGAR requires User-Agent with contact info per their TOS.
SEC_HEADERS = {
    "User-Agent": "Trading Analysis App research@localhost",
    "Accept": "application/json",
}

# Default list of institutional names commonly tracked for portfolio research.
# These are NAMES not CIKs — each gets verified against SEC before any seeding.
_DEFAULT_NAMES = [
    "Fidelity Management & Research",
    "Renaissance Technologies",
    "Citadel Advisors",
    "Bridgewater Associates",
    "ARK Investment Management",
    "DE Shaw",
    "Coatue Management",
    "Two Sigma Investments",
    "Elliott Investment Management",
    "Millennium Management",
    "Lone Pine Capital",
    "Tiger Global Management",
    "Capital Research Global Investors",
    "T Rowe Price",
    "Wellington Management",
    "Pershing Square Capital Management",
    "Greenlight Capital",
    "Third Point",
    "Baupost Group",
    "Maverick Capital",
]


def _edgar_search(name: str, *, retries: int = 2) -> list[dict]:
    """Search SEC EDGAR's full-text index for 13F-HR filings matching `name`."""
    url = "https://efts.sec.gov/LATEST/search-index"
    params = {
        "q": f'"{name}"',
        "forms": "13F-HR",
        # Newer first
        "dateRange": "custom",
        "startdt": "2023-01-01",
        "enddt": "2026-12-31",
    }
    for attempt in range(retries + 1):
        try:
            r = httpx.get(url, params=params, headers=SEC_HEADERS, timeout=30)
            r.raise_for_status()
            return (r.json().get("hits", {}).get("hits") or [])
        except Exception:
            if attempt == retries:
                return []
            time.sleep(1.0 * (attempt + 1))
    return []


def _resolve_one(name: str) -> dict:
    """Return {name, cik, filer_name, hit_count, confidence}.

    confidence:
      'high'   — one CIK dominates (≥75% of hits) and ≥3 hits
      'medium' — one CIK dominates (≥60%) and ≥2 hits
      'low'    — ambiguous or only 1 hit
      'none'   — no hits
    """
    hits = _edgar_search(name)
    if not hits:
        return {"name": name, "cik": None, "filer_name": None,
                "hit_count": 0, "confidence": "none"}

    # Each hit has an `_id` like "0001234567-25-000123:..." but the CIK we
    # want is in `_source.display_names` (filer-level) and `ciks` (list).
    cik_counter: Counter[str] = Counter()
    filer_names: dict[str, str] = {}
    for h in hits:
        src = h.get("_source", {}) or {}
        ciks = src.get("ciks") or []
        display = (src.get("display_names") or [None])[0]
        for cik in ciks:
            cik_str = str(cik).lstrip("0") or "0"
            cik_counter[cik_str] += 1
            if display and cik_str not in filer_names:
                filer_names[cik_str] = display

    if not cik_counter:
        return {"name": name, "cik": None, "filer_name": None,
                "hit_count": 0, "confidence": "low"}

    top_cik, top_n = cik_counter.most_common(1)[0]
    total = sum(cik_counter.values())
    share = top_n / total

    if total >= 3 and share >= 0.75:
        conf = "high"
    elif total >= 2 and share >= 0.60:
        conf = "medium"
    else:
        conf = "low"

    return {
        "name": name,
        "cik": top_cik,
        "filer_name": filer_names.get(top_cik),
        "hit_count": total,
        "top_share": round(share, 2),
        "confidence": conf,
        "alternatives": [
            {"cik": c, "n": n, "name": filer_names.get(c)}
            for c, n in cik_counter.most_common(4)[1:]
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--name", action="append", help="Institution name (repeatable)")
    p.add_argument("--write", help="CSV file to write resolved entries (only high/medium)")
    args = p.parse_args()

    names = args.name or _DEFAULT_NAMES
    print(f"Looking up {len(names)} institutions via SEC EDGAR full-text search...")
    print(f"Each query is rate-limited (~1s) — total time: ~{len(names)}s\n")

    results: list[dict] = []
    for nm in names:
        out = _resolve_one(nm)
        results.append(out)
        flag = {"high": "✓", "medium": "?", "low": "?", "none": "✗"}[out["confidence"]]
        cik_disp = out["cik"] or "—"
        print(f"  {flag}  {nm:42s} → CIK {cik_disp:>10}  "
              f"({out['confidence']:6s} · {out['hit_count']} 13Fs)")
        if out.get("filer_name"):
            print(f"        filer name: {out['filer_name']}")
        # Be polite to SEC
        time.sleep(0.5)

    if args.write:
        # Write only high/medium-confidence entries
        keep = [r for r in results if r["confidence"] in ("high", "medium")]
        with open(args.write, "w") as f:
            f.write("cik,name,type,total_aum,notes\n")
            for r in keep:
                # Conservative type tag; AUM left blank (must be filled separately
                # — we don't invent it). notes records the source.
                f.write(f"{r['cik']},{r['filer_name'] or r['name']},active_mgr,,"
                        f"discovered via SEC EDGAR ({r['confidence']} confidence)\n")
        print(f"\nWrote {len(keep)} high/medium-confidence entries to {args.write}")
        print(f"  ({len(results) - len(keep)} low/none-confidence entries excluded — review manually)")

    print()
    print(f"Summary: high={sum(1 for r in results if r['confidence']=='high')}  "
          f"medium={sum(1 for r in results if r['confidence']=='medium')}  "
          f"low={sum(1 for r in results if r['confidence']=='low')}  "
          f"none={sum(1 for r in results if r['confidence']=='none')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
