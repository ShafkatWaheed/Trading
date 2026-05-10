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


WATCHED_FORM_TYPES: frozenset[str] = frozenset({"10-K", "10-Q", "8-K", "DEF 14A"})

SEC_HEADERS = {
    "User-Agent": "Trading Prototype research@example.com",
    "Accept-Encoding": "gzip, deflate",
}


def _default_latest_filings(symbol: str) -> list[dict]:
    """Live SEC fetcher: returns recent filings for a symbol via EDGAR submissions API.

    Returns a list of dicts with keys: form, filed_at (str ISO date).
    Empty list on error or unknown CIK.
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
    return [
        {"form": f, "filed_at": d}
        for f, d in zip(forms, filing_dates)
    ]


def detect_new_filings(
    symbol: str,
    *,
    fetch_fn: Callable[[str], list[dict]] | None = None,
    watched: frozenset[str] = WATCHED_FORM_TYPES,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Returns dict with: symbol, new_filings (list of {form, filed_at}), error.

    A filing is "new" if its filed_at is greater than the
    `edge_freshness.last_filing_check` timestamp for that symbol.
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
            if f.get("form") not in watched:
                continue
            filed_at = f.get("filed_at")
            if not filed_at:
                continue
            if last_check is None or filed_at > last_check:
                new_filings.append({"form": f["form"], "filed_at": filed_at})

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
