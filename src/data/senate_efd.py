"""Senate eFD (Electronic Financial Disclosure) PTR ingest pipeline.

Sibling to `src.data.house_clerk`. Source: https://efdsearch.senate.gov/

Unlike the House Clerk's static yearly ZIP, the Senate portal is a stateful
search: GET the home page for a CSRF token, POST to accept the usage
agreement (sets a session cookie), then POST the DataTables `report/data`
endpoint to list Periodic Transaction Reports (report_type=11). Each filing
is either electronic (an HTML transaction table we parse) or paper (a scanned
PDF we skip + log -- no OCR).

Per CLAUDE.md: data layer. May call external APIs, read/write trading.db.
Returns empty lists on error -- no fake fallbacks. Point-in-time safe: we use
the filing/transaction dates as the "available at" timestamps.

Party is NOT in the feed and is left to a separate roster-enrichment join;
this module stores politician_name + state only. Chamber is always Senate.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup

from src.utils.db import get_connection, init_db, log_api_call

_BASE = "https://efdsearch.senate.gov"
_HOME_URL = f"{_BASE}/search/home/"
_DATA_URL = f"{_BASE}/search/report/data/"
_VIEW_URL = f"{_BASE}/search/view/ptr/{{uuid}}/"

# report_type 11 = Periodic Transaction Report
_REPORT_TYPE_PTR = "11"

_HEADERS = {
    "User-Agent": "TradingAnalysis/1.0 (research; admin@tradinganalysis.local)"
}

_LINK_RE = re.compile(r"/search/view/(ptr|paper)/([0-9a-fA-F\-]+)/?")
_AMOUNT_RE = re.compile(r"\$([\d,]+)\s*-\s*\$([\d,]+)")
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _norm_date(mdY: str) -> str:
    """'03/16/2026' -> '2026-03-16'. Returns input unchanged on failure."""
    try:
        return datetime.strptime(mdY.strip(), "%m/%d/%Y").date().isoformat()
    except Exception:
        return mdY


def _norm_txn(label: str) -> str:
    """Senate transaction label -> buy | sell | exchange | unknown."""
    s = (label or "").strip().lower()
    if s.startswith("purchase"):
        return "buy"
    if s.startswith("sale"):
        return "sell"
    if s.startswith("exchange"):
        return "exchange"
    return "unknown"


def _parse_amount_range(s: str) -> tuple[int, int]:
    """'$1,001 - $15,000' -> (1001, 15000). (0, 0) when no range found."""
    m = _AMOUNT_RE.search(s or "")
    if not m:
        return (0, 0)
    lo = int(m.group(1).replace(",", ""))
    hi = int(m.group(2).replace(",", ""))
    return (lo, hi)
