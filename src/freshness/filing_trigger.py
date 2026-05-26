"""Layer 3: SEC EDGAR filing trigger.

For each symbol, check whether a new filing of one of the watched form types
(10-K, 10-Q, 8-K, DEF 14A) has been submitted since the last check. A new
filing is a strong signal that supplier/customer/risk-factor information may
have changed and the stock's edges need re-extraction.

Network-gated. Tests mock the filings fetch.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable

import httpx

from src.utils.db import get_connection, init_db


# Narrow default — only material filings that meaningfully change graph edges.
# 10-K: annual, definitive supplier/customer disclosures (Item 1, Item 7).
# 8-K: filtered by item code below (see MATERIAL_8K_ITEMS).
# 10-Q and DEF 14A are intentionally excluded — they flood the queue
# without affecting the graph (proxy comp info, quarterly noise).
WATCHED_FORM_TYPES: frozenset[str] = frozenset({"10-K", "8-K"})

# 8-K item codes that materially affect graph edges:
#   1.01 — Entry into a Material Definitive Agreement (new contracts → new edges)
#   2.01 — Completion of Acquisition or Disposition of Assets (M&A → new/dropped edges)
#   5.02 — Departure / Election of Directors or Principal Officers (leadership)
# All other items (7.01 Reg FD, 8.01 Other Events, 9.01 Exhibits, etc.) are skipped.
MATERIAL_8K_ITEMS: frozenset[str] = frozenset({"1.01", "2.01", "5.02"})

SEC_HEADERS = {
    "User-Agent": "Trading Prototype research@example.com",
    "Accept-Encoding": "gzip, deflate",
}


def _items_string(filing: dict) -> str:
    """Normalize a filing's items field to a comma-separated string.

    SEC submissions API returns `items` as a string ("1.01,2.03") or empty;
    test fixtures may pass list or missing. Returns "" if absent."""
    raw = filing.get("items")
    if raw is None:
        return ""
    if isinstance(raw, list):
        return ",".join(str(x) for x in raw)
    return str(raw)


def _is_material_8k(filing: dict, material_items: frozenset[str]) -> bool:
    """True if any of the filing's items overlaps the material-items set."""
    items_str = _items_string(filing)
    if not items_str:
        return False
    filed_items = {it.strip() for it in items_str.split(",") if it.strip()}
    return bool(filed_items & material_items)


def _default_latest_filings(symbol: str) -> list[dict]:
    """Live SEC fetcher: returns recent filings for a symbol via EDGAR submissions API.

    Returns a list of dicts with keys: form, filed_at (str ISO date), items
    (comma-separated string of 8-K item codes; empty for non-8-Ks). Empty list
    on error or unknown CIK.
    """
    from src.data.sec_edgar import SECEdgarProvider

    provider = SECEdgarProvider()
    try:
        cik = provider._get_cik(symbol)
    except Exception:
        return []
    if not cik:
        return []

    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    try:
        resp = httpx.get(url, headers=SEC_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    items_arr = recent.get("items", [])
    out: list[dict] = []
    for i, (f, d) in enumerate(zip(forms, filing_dates)):
        items = items_arr[i] if i < len(items_arr) else ""
        out.append({"form": f, "filed_at": d, "items": items})
    return out


def detect_new_filings(
    symbol: str,
    *,
    fetch_fn: Callable[[str], list[dict]] | None = None,
    watched: frozenset[str] = WATCHED_FORM_TYPES,
    material_8k_items: frozenset[str] = MATERIAL_8K_ITEMS,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Returns dict with: symbol, new_filings (list of {form, filed_at, items}), error.

    A filing is "new" if its filed_at is greater than the
    `edge_freshness.last_filing_check` timestamp for that symbol.

    8-K filings additionally pass through the `material_8k_items` filter:
    only flagged if at least one of their item codes is in the material set.
    Non-8-K filings in `watched` are always included.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    fetch_fn = fetch_fn or _default_latest_filings

    try:
        filings = fetch_fn(symbol)
        if not filings:
            return {"symbol": symbol, "new_filings": [], "error": "no_filings"}

        row = conn.execute(
            "SELECT last_filing_check FROM edge_freshness WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        last_check = row["last_filing_check"] if row else None

        new_filings = []
        for f in filings:
            form = f.get("form")
            if form not in watched:
                continue
            filed_at = f.get("filed_at")
            if not filed_at:
                continue
            if last_check is not None and filed_at <= last_check:
                continue
            # 8-K item-code filter: only material items pass.
            if form == "8-K" and not _is_material_8k(f, material_8k_items):
                continue
            new_filings.append({
                "form": form,
                "filed_at": filed_at,
                "items": _items_string(f),
            })

        # Update the cursor regardless of whether we found new filings — next
        # run only reports filings since this check.
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO edge_freshness (symbol, last_filing_check)
            VALUES (?, ?)
            ON CONFLICT(symbol) DO UPDATE SET last_filing_check = excluded.last_filing_check
            """,
            (symbol, now),
        )
        conn.commit()

        return {
            "symbol": symbol,
            "new_filings": new_filings,
            "previous_check": last_check,
            "error": None,
        }
    finally:
        if own_conn:
            conn.close()
