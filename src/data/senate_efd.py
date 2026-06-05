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


def _fetch_and_store_one(meta: dict, *, http_get=None) -> int:
    """Fetch + parse + store ONE electronic PTR. Returns transactions stored.

    Paper filings are not fetched -- marked 'paper_unparsed' and skipped.
    `http_get` is dependency-injected for tests; the default establishes a
    session per call.
    """
    init_db()
    uuid = meta["filing_uuid"]
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO senate_efd_index "
            "  (filing_uuid, doc_kind, filing_type, politician_name, state, "
            "   filing_date, last_attempted) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(filing_uuid) DO UPDATE SET last_attempted = ?",
            (uuid, meta.get("doc_kind"), meta.get("filing_type", "P"),
             meta.get("politician_name"), meta.get("state"),
             meta.get("filing_date"), now_iso, now_iso),
        )
        conn.commit()

        if meta.get("doc_kind") == "paper":
            conn.execute(
                "UPDATE senate_efd_index SET status='paper_unparsed', fetched_at=? "
                "WHERE filing_uuid=?", (now_iso, uuid))
            conn.commit()
            return 0

        get = http_get
        client = None
        if get is None:
            client = _establish_session()
            if client is None:
                conn.execute(
                    "UPDATE senate_efd_index SET status='http_error', error=? "
                    "WHERE filing_uuid=?", ("session failed", uuid))
                conn.commit()
                return 0
            get = lambda url: client.get(url)

        url = _VIEW_URL.format(uuid=uuid)
        try:
            r = get(url)
            r.raise_for_status()
        except Exception as exc:
            conn.execute(
                "UPDATE senate_efd_index SET status='http_error', error=? "
                "WHERE filing_uuid=?", (str(exc)[:200], uuid))
            conn.commit()
            log_api_call("senate_efd", url, "error", error=str(exc))
            return 0
        finally:
            if client is not None:
                client.close()

        txns = parse_ptr_html(r.text)
        if not txns:
            conn.execute(
                "UPDATE senate_efd_index SET status='empty', fetched_at=? "
                "WHERE filing_uuid=?", (now_iso, uuid))
            conn.commit()
            return 0

        conn.execute("DELETE FROM senate_efd_trades WHERE filing_uuid=?", (uuid,))
        for i, t in enumerate(txns):
            txn_date = _norm_date(t["transaction_date_raw"])
            conn.execute(
                """
                INSERT INTO senate_efd_trades
                  (filing_uuid, txn_index, politician_name, state, filing_date,
                   ticker, asset_type, transaction_type, transaction_date,
                   notification_date, amount_low, amount_high, raw_text, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (uuid, i, meta.get("politician_name"), meta.get("state"),
                 meta.get("filing_date"), t["ticker"], t["asset_type"],
                 _norm_txn(t["transaction_code"]), txn_date,
                 txn_date,  # Senate table has no separate notification date
                 t["amount_low"], t["amount_high"], t["raw_text"], now_iso),
            )
        conn.execute(
            "UPDATE senate_efd_index SET status='parsed', fetched_at=? "
            "WHERE filing_uuid=?", (now_iso, uuid))
        conn.commit()
        log_api_call("senate_efd", url, "ok", error=f"{len(txns)} txns")
        return len(txns)
    finally:
        conn.close()


def refresh_recent(*, days: int = 30, max_docs: int = 50,
                   search_fn=None, http_get=None) -> dict:
    """Refresh recent Senate PTRs in a rolling `days` window.

    Lists filings, skips any already in a terminal state ('parsed' or
    'paper_unparsed'), and processes up to `max_docs` new ones. Both fetchers
    are dependency-injected for tests; defaults establish one shared session.
    Returns {found, attempted, parsed, errored, empty, paper}.
    """
    init_db()

    client = None
    _search = search_fn
    _get = http_get
    if _search is None or _get is None:
        client = _establish_session()
        if client is None:
            return {"found": 0, "attempted": 0, "parsed": 0,
                    "errored": 0, "empty": 0, "paper": 0}
        if _search is None:
            _search = lambda s, l, sd, ed: _search_page(client, s, l, sd, ed)
        if _get is None:
            _get = lambda url: client.get(url)

    try:
        index = fetch_index(days=days, max_docs=max_docs, search_fn=_search)
        if not index:
            return {"found": 0, "attempted": 0, "parsed": 0,
                    "errored": 0, "empty": 0, "paper": 0}

        conn = get_connection()
        terminal = {r[0] for r in conn.execute(
            "SELECT filing_uuid FROM senate_efd_index "
            "WHERE status IN ('parsed', 'paper_unparsed')"
        )}
        conn.close()

        todo = [m for m in index if m["filing_uuid"] not in terminal][:max_docs]
        counts = {"found": len(index), "attempted": len(todo),
                  "parsed": 0, "errored": 0, "empty": 0, "paper": 0}

        for meta in todo:
            if meta["doc_kind"] == "paper":
                _fetch_and_store_one(meta, http_get=_get)
                counts["paper"] += 1
                continue
            n = _fetch_and_store_one(meta, http_get=_get)
            if n > 0:
                counts["parsed"] += 1
            else:
                conn = get_connection()
                row = conn.execute(
                    "SELECT status FROM senate_efd_index WHERE filing_uuid=?",
                    (meta["filing_uuid"],)).fetchone()
                conn.close()
                if row and row["status"] == "empty":
                    counts["empty"] += 1
                else:
                    counts["errored"] += 1
        return counts
    finally:
        if client is not None:
            client.close()


def get_top_traded_stocks(days: int = 90, *, limit: int = 20) -> list[dict]:
    """Top tickers by transaction count over the last `days`."""
    init_db()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).date().isoformat()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT ticker, COUNT(*) AS trade_count
            FROM senate_efd_trades
            WHERE ticker != '' AND transaction_date >= ?
            GROUP BY ticker ORDER BY trade_count DESC LIMIT ?
            """,
            (cutoff, limit),
        ).fetchall()
    finally:
        conn.close()
    return [{"symbol": r["ticker"], "trade_count": r["trade_count"]} for r in rows]


def get_trades_by_symbol(symbol: str, days: int = 180) -> list[dict]:
    """All Senate transactions for one ticker over the lookback window."""
    if not symbol:
        return []
    init_db()
    sym = symbol.upper().strip()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).date().isoformat()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT filing_uuid, politician_name, state, filing_date, ticker, asset_type,
                   transaction_type, transaction_date, notification_date,
                   amount_low, amount_high, raw_text
            FROM senate_efd_trades
            WHERE ticker = ? AND transaction_date >= ?
            ORDER BY transaction_date DESC
            """,
            (sym, cutoff),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_trades_by_politician(name: str, days: int = 180) -> list[dict]:
    """All Senate transactions for one politician over the lookback window."""
    if not name:
        return []
    init_db()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).date().isoformat()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT filing_uuid, politician_name, state, filing_date, ticker, asset_type,
                   transaction_type, transaction_date, notification_date,
                   amount_low, amount_high, raw_text
            FROM senate_efd_trades
            WHERE politician_name LIKE ? AND transaction_date >= ?
            ORDER BY transaction_date DESC
            """,
            (f"%{name.strip()}%", cutoff),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]
