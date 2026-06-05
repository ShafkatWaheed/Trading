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
_AMOUNT_RE = re.compile(r"\$([\d,]+)\s*[-–]\s*\$([\d,]+)")
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9./\-]{0,9}$")


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


def _cell_text(td) -> str:
    return td.get_text(" ", strip=True)


def parse_ptr_html(html: str) -> list[dict]:
    """Parse one electronic PTR view's transactions table into raw dicts.

    Column order: #, Transaction Date, Owner, Ticker, Asset Name, Asset Type,
    Type, Amount, Comment. Rows without a real ticker (e.g. '--', bonds) are
    dropped -- we never guess a symbol. Returns [] when no table / on any
    parse error.
    """
    out: list[dict] = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if table is None:
            return []
        body = table.find("tbody") or table
        for tr in body.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 8:
                continue
            ticker = _cell_text(tds[3]).upper().strip()
            if not _TICKER_RE.match(ticker):
                continue  # '--', CUSIPs, blanks -> dropped
            txn_date = _cell_text(tds[1])
            asset_type = _cell_text(tds[5])
            txn_type = _cell_text(tds[6])
            lo, hi = _parse_amount_range(_cell_text(tds[7]))
            out.append({
                "ticker": ticker,
                "asset_type": asset_type,
                "transaction_code": txn_type,
                "transaction_date_raw": txn_date,
                "amount_low": lo,
                "amount_high": hi,
                "raw_text": tr.get_text(" ", strip=True)[:500],
            })
    except Exception:
        return []
    return out


def _extract_csrf(html: str) -> str | None:
    """Pull csrfmiddlewaretoken from the search home page HTML."""
    m = re.search(
        r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', html
    )
    return m.group(1) if m else None


def _establish_session() -> httpx.Client | None:
    """GET home -> read CSRF -> POST agreement. Returns a cookie-bearing
    client, or None on failure (logged)."""
    client = httpx.Client(headers=_HEADERS, timeout=60.0, follow_redirects=True)
    try:
        r = client.get(_HOME_URL)
        r.raise_for_status()
        token = _extract_csrf(r.text) or client.cookies.get("csrftoken")
        if not token:
            raise RuntimeError("no CSRF token on search home")
        r2 = client.post(
            _HOME_URL,
            data={"prohibition_agreement": "1", "csrfmiddlewaretoken": token},
            headers={"Referer": _HOME_URL, "X-CSRFToken": token},
        )
        r2.raise_for_status()
        return client
    except Exception as exc:
        log_api_call("senate_efd", _HOME_URL, "error", error=str(exc))
        client.close()
        return None


def _search_page(client: httpx.Client, start: int, length: int,
                 start_date: str, end_date: str) -> dict:
    """POST the DataTables report/data endpoint for one page."""
    token = client.cookies.get("csrftoken") or ""
    payload = {
        "start": str(start),
        "length": str(length),
        "report_types": f"[{_REPORT_TYPE_PTR}]",
        "submitted_start_date": f"{start_date} 00:00:00",
        "submitted_end_date": f"{end_date} 23:59:59",
        "csrfmiddlewaretoken": token,
    }
    r = client.post(_DATA_URL, data=payload,
                    headers={"Referer": _HOME_URL, "X-CSRFToken": token})
    r.raise_for_status()
    return r.json()


def fetch_index(*, days: int = 30, max_docs: int = 50, search_fn=None) -> list[dict]:
    """List recent PTR filings in a rolling `days` window.

    `search_fn(start, length, start_date_iso, end_date_iso) -> dict` is
    dependency-injected for tests; the default establishes a session and hits
    the live DataTables endpoint. Returns [] on any error (logged).
    Each record: {filing_uuid, doc_kind, filing_type, politician_name,
    state, filing_date}.
    """
    init_db()
    now = datetime.now(tz=timezone.utc).date()
    start_date = (now - timedelta(days=days)).isoformat()
    end_date = now.isoformat()

    client = None
    if search_fn is None:
        client = _establish_session()
        if client is None:
            return []
        search_fn = lambda s, l, sd, ed: _search_page(client, s, l, sd, ed)

    out: list[dict] = []
    try:
        page_len = 100
        start = 0
        while len(out) < max_docs:
            data = search_fn(start, page_len, start_date, end_date)
            rows = data.get("data") or []
            if not rows:
                break
            for row in rows:
                if len(out) >= max_docs:
                    break
                rec = _row_to_index_record(row)
                if rec:
                    out.append(rec)
            start += page_len
            if start >= int(data.get("recordsTotal") or 0):
                break
        log_api_call("senate_efd", _DATA_URL, "ok", error=f"{len(out)} filings")
    except Exception as exc:
        log_api_call("senate_efd", _DATA_URL, "error", error=str(exc))
        return []
    finally:
        if client is not None:
            client.close()
    return out[:max_docs]


def _row_to_index_record(row: list) -> dict | None:
    """DataTables row -> index record. None if no recognizable filing link."""
    if not row or len(row) < 5:
        return None
    first, last = (row[0] or "").strip(), (row[1] or "").strip()
    link_html = row[3] or ""
    m = _LINK_RE.search(link_html)
    if not m:
        return None
    kind = "paper" if m.group(1) == "paper" else "electronic"
    return {
        "filing_uuid": m.group(2),
        "doc_kind": kind,
        "filing_type": "P",
        "politician_name": " ".join(filter(None, [first, last])).strip(),
        "state": "",  # not in the search row; filled by roster join later
        "filing_date": _norm_date(row[4] or ""),
    }
