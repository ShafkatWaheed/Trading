# Senate eFD Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Senate-side congressional-trade ingester that mirrors the House Clerk pipeline, so `CongressDataProvider` returns House **and** Senate trades through its existing unchanged public API.

**Architecture:** New sibling module `src/data/senate_efd.py` mirroring `src/data/house_clerk.py`, backed by two new cache tables (`senate_efd_trades`, `senate_efd_index`). The `src/data/congress.py` adapter unions House + Senate rows. A second nightly scheduler job refreshes the Senate side. Paper (scanned) filings are skipped + logged; party stays `"Unknown"` (a roster-enrichment join is a separate follow-up). The working House pipeline is untouched.

**Tech Stack:** Python, `httpx` (session/cookie flow), `beautifulsoup4` (HTML table parse), SQLite via `src.utils.db`, `pytest` with dependency-injected HTTP (no live network, temp-DB fixture).

**Reference spec:** `docs/superpowers/specs/2026-06-05-senate-efd-ingestion-design.md`

**Conventions to follow (from `src/data/house_clerk.py` + `tests/test_house_clerk.py`):**
- All HTTP fetchers are dependency-injected so tests never hit the network.
- Errors → `log_api_call(...)` + mark index row + return empty; never fabricate data.
- `from __future__ import annotations` at top of new modules.
- Timestamps via `datetime.now(tz=timezone.utc)`; dates normalized to ISO `YYYY-MM-DD`.

---

## File Structure

- **Create:** `src/data/senate_efd.py` — Senate eFD ingest (session flow, search, HTML parse, storage, queries).
- **Create:** `tests/test_senate_efd.py` — unit tests (injected HTTP, temp DB).
- **Create:** `tests/test_congress_adapter_union.py` — adapter union/chamber tests.
- **Modify:** `src/utils/db.py` — add two `CREATE TABLE` blocks in `init_db`.
- **Modify:** `src/data/congress.py` — union House + Senate; add `chamber` to `_row_to_trade`; merge `get_top_traded_stocks`; update docstring.
- **Modify:** `api/main.py` — second `schedule_daily_at` job for Senate.
- **Modify:** `src/data/house_clerk.py` — update the "House-only" docstring note.

---

## Task 1: Database schema for Senate tables

**Files:**
- Modify: `src/utils/db.py` (inside `init_db`, after the `house_clerk_index` block ~line 559)
- Test: `tests/test_senate_efd.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_senate_efd.py` with:

```python
"""Tests for Senate eFD PTR ingest pipeline.

Network access is dependency-injected (httpx never called). The DataTables
search JSON and the electronic-PTR HTML are fed as canned fixtures.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data import senate_efd
from src.utils.db import get_connection, init_db


def test_init_db_creates_senate_tables():
    init_db()
    conn = get_connection()
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('senate_efd_trades', 'senate_efd_index')"
        )
    }
    conn.close()
    assert names == {"senate_efd_trades", "senate_efd_index"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_senate_efd.py::test_init_db_creates_senate_tables -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.data.senate_efd'` (module created in Task 2) **or**, once Task 2 exists, the table assertion fails because tables don't exist yet.

> Note: this test imports `senate_efd`. To see the schema failure in isolation before Task 2, temporarily comment the import; otherwise just implement Task 1 and Task 2's module stub together. Simplest: do Step 3 below now, then this test goes green after Task 2 creates the module.

- [ ] **Step 3: Add the schema**

In `src/utils/db.py`, immediately after the `CREATE INDEX IF NOT EXISTS idx_hci_status ON house_clerk_index(status);` line, add:

```python
        -- ── Senate eFD PTR ingest (sibling to house_clerk_*) ──
        CREATE TABLE IF NOT EXISTS senate_efd_trades (
            filing_uuid        TEXT NOT NULL,
            txn_index          INTEGER NOT NULL,
            politician_name    TEXT NOT NULL,
            state              TEXT,
            filing_date        TEXT,
            ticker             TEXT NOT NULL,
            asset_type         TEXT,
            transaction_type   TEXT,
            transaction_date   TEXT,
            notification_date  TEXT,
            amount_low         INTEGER,
            amount_high        INTEGER,
            raw_text           TEXT,
            fetched_at         TEXT NOT NULL,
            PRIMARY KEY (filing_uuid, txn_index)
        );
        CREATE INDEX IF NOT EXISTS idx_sef_ticker     ON senate_efd_trades(ticker);
        CREATE INDEX IF NOT EXISTS idx_sef_date       ON senate_efd_trades(transaction_date);
        CREATE INDEX IF NOT EXISTS idx_sef_politician ON senate_efd_trades(politician_name);

        CREATE TABLE IF NOT EXISTS senate_efd_index (
            filing_uuid     TEXT PRIMARY KEY,
            doc_kind        TEXT,
            filing_type     TEXT,
            politician_name TEXT,
            state           TEXT,
            filing_date     TEXT,
            last_attempted  TEXT,
            status          TEXT,
            error           TEXT,
            fetched_at      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sefi_status ON senate_efd_index(status);
```

> These blocks live inside the same `conn.executescript(...)` string as the house_clerk tables. Match the surrounding indentation exactly.

- [ ] **Step 4: (defer running until Task 2 module exists). Commit**

```bash
git add src/utils/db.py
git commit -m "feat(db): add senate_efd_trades + senate_efd_index tables"
```

---

## Task 2: Module skeleton + normalization helpers

**Files:**
- Create: `src/data/senate_efd.py`
- Test: `tests/test_senate_efd.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_senate_efd.py`:

```python
def test_norm_txn_maps_senate_labels():
    assert senate_efd._norm_txn("Purchase") == "buy"
    assert senate_efd._norm_txn("Sale (Full)") == "sell"
    assert senate_efd._norm_txn("Sale (Partial)") == "sell"
    assert senate_efd._norm_txn("Exchange") == "exchange"
    assert senate_efd._norm_txn("weird") == "unknown"


def test_norm_date_and_amounts():
    assert senate_efd._norm_date("03/16/2026") == "2026-03-16"
    assert senate_efd._norm_date("garbage") == "garbage"
    assert senate_efd._parse_amount_range("$1,001 - $15,000") == (1001, 15000)
    assert senate_efd._parse_amount_range("no dollars here") == (0, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_senate_efd.py -k "norm or amount" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.data.senate_efd'`

- [ ] **Step 3: Create the module with helpers**

Create `src/data/senate_efd.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_senate_efd.py -k "init_db or norm or amount" -v`
Expected: PASS (3 tests: schema, norm_txn, norm_date/amounts).

- [ ] **Step 5: Commit**

```bash
git add src/data/senate_efd.py tests/test_senate_efd.py
git commit -m "feat(senate): module skeleton + date/txn/amount normalizers"
```

---

## Task 3: Parse electronic PTR HTML table

**Files:**
- Modify: `src/data/senate_efd.py`
- Test: `tests/test_senate_efd.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_senate_efd.py`:

```python
# Captured shape of an electronic PTR transactions table (sanitized).
_PTR_HTML = """
<html><body>
<table class="table table-striped">
  <thead><tr>
    <th>#</th><th>Transaction Date</th><th>Owner</th><th>Ticker</th>
    <th>Asset Name</th><th>Asset Type</th><th>Type</th>
    <th>Amount</th><th>Comment</th>
  </tr></thead>
  <tbody>
    <tr>
      <td>1</td><td>03/16/2026</td><td>Self</td>
      <td><a href="/search/...">AAPL</a></td>
      <td>Apple Inc.</td><td>Stock</td><td>Purchase</td>
      <td>$1,001 - $15,000</td><td>--</td>
    </tr>
    <tr>
      <td>2</td><td>03/17/2026</td><td>Spouse</td>
      <td>NVDA</td>
      <td>NVIDIA Corp</td><td>Stock</td><td>Sale (Full)</td>
      <td>$15,001 - $50,000</td><td>--</td>
    </tr>
    <tr>
      <td>3</td><td>03/18/2026</td><td>Self</td>
      <td>--</td>
      <td>US Treasury Bond</td><td>Corporate Bond</td><td>Purchase</td>
      <td>$1,001 - $15,000</td><td>--</td>
    </tr>
  </tbody>
</table>
</body></html>
"""


def test_parse_ptr_html_extracts_tickered_rows():
    out = senate_efd.parse_ptr_html(_PTR_HTML)
    # The tickerless treasury row (ticker '--') is dropped.
    assert len(out) == 2
    by_t = {r["ticker"]: r for r in out}
    assert by_t["AAPL"]["transaction_code"] == "Purchase"
    assert by_t["AAPL"]["asset_type"] == "Stock"
    assert by_t["AAPL"]["transaction_date_raw"] == "03/16/2026"
    assert by_t["AAPL"]["amount_low"] == 1001
    assert by_t["AAPL"]["amount_high"] == 15000
    assert by_t["NVDA"]["transaction_code"] == "Sale (Full)"
    assert by_t["NVDA"]["amount_high"] == 50000


def test_parse_ptr_html_empty_when_no_table():
    assert senate_efd.parse_ptr_html("<html><body>No table</body></html>") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_senate_efd.py -k parse_ptr_html -v`
Expected: FAIL — `AttributeError: module 'src.data.senate_efd' has no attribute 'parse_ptr_html'`

- [ ] **Step 3: Implement `parse_ptr_html`**

Append to `src/data/senate_efd.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_senate_efd.py -k parse_ptr_html -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/senate_efd.py tests/test_senate_efd.py
git commit -m "feat(senate): parse electronic PTR HTML transaction table"
```

---

## Task 4: Fetch + classify the filing index (DataTables search)

**Files:**
- Modify: `src/data/senate_efd.py`
- Test: `tests/test_senate_efd.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_senate_efd.py`:

```python
def _make_data_page(rows: list[list], total: int | None = None) -> dict:
    """Shape of the DataTables /report/data/ JSON response."""
    return {"data": rows, "recordsTotal": total if total is not None else len(rows),
            "recordsFiltered": total if total is not None else len(rows)}


def test_fetch_index_classifies_and_caps():
    # row = [first, last, office, report_link_html, date_received]
    page = _make_data_page([
        ["Mark", "Warner", "Warner, Mark R. (Senator)",
         '<a href="/search/view/ptr/aaa-111/" target="_blank">PTR</a>', "03/31/2026"],
        ["Jane", "Doe", "Doe, Jane (Senator)",
         '<a href="/search/view/paper/bbb-222/">PTR (paper)</a>', "03/30/2026"],
        ["Ron", "Roe", "Roe, Ron (Senator)",
         '<a href="/search/view/ptr/ccc-333/">PTR</a>', "03/29/2026"],
    ])
    calls = []

    def fake_search(start, length, start_date, end_date):
        calls.append((start, length))
        return page if start == 0 else _make_data_page([])

    out = senate_efd.fetch_index(days=30, max_docs=2, search_fn=fake_search)
    assert len(out) == 2  # capped at max_docs
    assert out[0]["filing_uuid"] == "aaa-111"
    assert out[0]["doc_kind"] == "electronic"
    assert out[0]["politician_name"] == "Mark Warner"
    assert out[0]["filing_date"] == "2026-03-31"
    assert out[1]["doc_kind"] == "paper"
    assert out[1]["filing_uuid"] == "bbb-222"


def test_fetch_index_search_error_returns_empty():
    def boom(start, length, start_date, end_date):
        raise RuntimeError("portal down")
    assert senate_efd.fetch_index(days=30, search_fn=boom) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_senate_efd.py -k fetch_index -v`
Expected: FAIL — `AttributeError: ... has no attribute 'fetch_index'`

- [ ] **Step 3: Implement session helpers + `fetch_index`**

Append to `src/data/senate_efd.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_senate_efd.py -k fetch_index -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/senate_efd.py tests/test_senate_efd.py
git commit -m "feat(senate): session/agreement flow + fetch_index with paper/electronic classification"
```

---

## Task 5: Fetch + store one filing

**Files:**
- Modify: `src/data/senate_efd.py`
- Test: `tests/test_senate_efd.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_senate_efd.py`:

```python
class _FakeResp:
    def __init__(self, text: str = "", status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def clean_senate_tables():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM senate_efd_trades")
    conn.execute("DELETE FROM senate_efd_index")
    conn.commit()
    conn.close()
    yield
    conn = get_connection()
    conn.execute("DELETE FROM senate_efd_trades")
    conn.execute("DELETE FROM senate_efd_index")
    conn.commit()
    conn.close()


def test_store_electronic_persists_rows(clean_senate_tables):
    meta = {"filing_uuid": "aaa-111", "doc_kind": "electronic", "filing_type": "P",
            "politician_name": "Mark Warner", "state": "", "filing_date": "2026-03-31"}
    n = senate_efd._fetch_and_store_one(meta, http_get=lambda url: _FakeResp(_PTR_HTML))
    assert n == 2  # AAPL + NVDA; treasury dropped

    conn = get_connection()
    rows = conn.execute(
        "SELECT ticker, transaction_type, transaction_date, amount_high "
        "FROM senate_efd_trades WHERE filing_uuid='aaa-111' ORDER BY txn_index"
    ).fetchall()
    status = conn.execute(
        "SELECT status FROM senate_efd_index WHERE filing_uuid='aaa-111'"
    ).fetchone()["status"]
    conn.close()

    assert status == "parsed"
    by_t = {r["ticker"]: r for r in rows}
    assert by_t["AAPL"]["transaction_type"] == "buy"
    assert by_t["AAPL"]["transaction_date"] == "2026-03-16"
    assert by_t["NVDA"]["transaction_type"] == "sell"
    assert by_t["NVDA"]["amount_high"] == 50000


def test_store_paper_skips_and_marks(clean_senate_tables):
    meta = {"filing_uuid": "bbb-222", "doc_kind": "paper", "filing_type": "P",
            "politician_name": "Jane Doe", "state": "", "filing_date": "2026-03-30"}

    def must_not_call(url):
        raise AssertionError("paper filing should not be fetched")

    n = senate_efd._fetch_and_store_one(meta, http_get=must_not_call)
    assert n == 0
    conn = get_connection()
    status = conn.execute(
        "SELECT status FROM senate_efd_index WHERE filing_uuid='bbb-222'"
    ).fetchone()["status"]
    conn.close()
    assert status == "paper_unparsed"


def test_store_http_error_marked(clean_senate_tables):
    meta = {"filing_uuid": "ccc-333", "doc_kind": "electronic", "filing_type": "P",
            "politician_name": "Ron Roe", "state": "", "filing_date": "2026-03-29"}

    def boom(url):
        raise RuntimeError("503 unavailable")

    n = senate_efd._fetch_and_store_one(meta, http_get=boom)
    assert n == 0
    conn = get_connection()
    row = conn.execute(
        "SELECT status, error FROM senate_efd_index WHERE filing_uuid='ccc-333'"
    ).fetchone()
    conn.close()
    assert row["status"] == "http_error"
    assert "503" in (row["error"] or "")


def test_store_empty_marked(clean_senate_tables):
    meta = {"filing_uuid": "ddd-444", "doc_kind": "electronic", "filing_type": "P",
            "politician_name": "Empty Filer", "state": "", "filing_date": "2026-03-28"}
    n = senate_efd._fetch_and_store_one(
        meta, http_get=lambda url: _FakeResp("<html>no table</html>"))
    assert n == 0
    conn = get_connection()
    status = conn.execute(
        "SELECT status FROM senate_efd_index WHERE filing_uuid='ddd-444'"
    ).fetchone()["status"]
    conn.close()
    assert status == "empty"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_senate_efd.py -k store -v`
Expected: FAIL — `AttributeError: ... has no attribute '_fetch_and_store_one'`

- [ ] **Step 3: Implement `_fetch_and_store_one`**

Append to `src/data/senate_efd.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_senate_efd.py -k store -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/senate_efd.py tests/test_senate_efd.py
git commit -m "feat(senate): fetch+store one filing (electronic parse, paper skip, error marking)"
```

---

## Task 6: `refresh_recent` orchestration (idempotent)

**Files:**
- Modify: `src/data/senate_efd.py`
- Test: `tests/test_senate_efd.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_senate_efd.py`:

```python
def test_refresh_recent_idempotent_and_skips_paper(clean_senate_tables):
    page = _make_data_page([
        ["Mark", "Warner", "Warner (Senator)",
         '<a href="/search/view/ptr/aaa-111/">PTR</a>', "03/31/2026"],
        ["Jane", "Doe", "Doe (Senator)",
         '<a href="/search/view/paper/bbb-222/">PTR</a>', "03/30/2026"],
    ])

    def fake_search(start, length, sd, ed):
        return page if start == 0 else _make_data_page([])

    counts = senate_efd.refresh_recent(
        days=30, max_docs=50,
        search_fn=fake_search,
        http_get=lambda url: _FakeResp(_PTR_HTML),
    )
    assert counts["found"] == 2
    assert counts["parsed"] == 1
    assert counts["paper"] == 1

    # Second run: both filings terminal -> nothing re-attempted.
    counts2 = senate_efd.refresh_recent(
        days=30, max_docs=50,
        search_fn=fake_search,
        http_get=lambda url: (_ for _ in ()).throw(
            AssertionError("should not refetch terminal filings")),
    )
    assert counts2["attempted"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_senate_efd.py -k refresh_recent -v`
Expected: FAIL — `AttributeError: ... has no attribute 'refresh_recent'`

- [ ] **Step 3: Implement `refresh_recent`**

Append to `src/data/senate_efd.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_senate_efd.py -k refresh_recent -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add src/data/senate_efd.py tests/test_senate_efd.py
git commit -m "feat(senate): idempotent refresh_recent orchestration"
```

---

## Task 7: Query functions (by symbol / politician / top-traded)

**Files:**
- Modify: `src/data/senate_efd.py`
- Test: `tests/test_senate_efd.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_senate_efd.py`:

```python
def _seed_trade(conn, uuid, idx, name, ticker, txn, date_iso):
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO senate_efd_trades
          (filing_uuid, txn_index, politician_name, state, filing_date,
           ticker, asset_type, transaction_type, transaction_date,
           notification_date, amount_low, amount_high, raw_text, fetched_at)
        VALUES (?, ?, ?, '', ?, ?, 'Stock', ?, ?, ?, 1001, 15000, 'raw', ?)
        """,
        (uuid, idx, name, date_iso, ticker, txn, date_iso, date_iso, now_iso),
    )


def test_query_functions(clean_senate_tables):
    today = datetime.now(tz=timezone.utc).date().isoformat()
    conn = get_connection()
    _seed_trade(conn, "U1", 0, "Mark Warner", "NVDA", "buy", today)
    _seed_trade(conn, "U1", 1, "Mark Warner", "AAPL", "buy", today)
    _seed_trade(conn, "U2", 0, "Jane Doe", "NVDA", "sell", today)
    conn.commit()
    conn.close()

    by_sym = senate_efd.get_trades_by_symbol("NVDA", days=90)
    assert len(by_sym) == 2
    assert all(r["ticker"] == "NVDA" for r in by_sym)
    assert senate_efd.get_trades_by_symbol("", days=90) == []

    by_pol = senate_efd.get_trades_by_politician("Warner", days=90)
    assert len(by_pol) == 2

    top = senate_efd.get_top_traded_stocks(days=90, limit=10)
    assert top[0] == {"symbol": "NVDA", "trade_count": 2}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_senate_efd.py -k query_functions -v`
Expected: FAIL — `AttributeError: ... has no attribute 'get_trades_by_symbol'`

- [ ] **Step 3: Implement the query functions**

Append to `src/data/senate_efd.py`:

```python
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
```

- [ ] **Step 4: Run the whole module's tests**

Run: `pytest tests/test_senate_efd.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/senate_efd.py tests/test_senate_efd.py
git commit -m "feat(senate): query functions (by symbol/politician/top-traded)"
```

---

## Task 8: Union Senate into the CongressDataProvider adapter

**Files:**
- Modify: `src/data/congress.py`
- Test: `tests/test_congress_adapter_union.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_congress_adapter_union.py`:

```python
"""The CongressDataProvider unions House + Senate rows and tags chamber."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data.congress import CongressDataProvider
from src.utils.db import get_connection, init_db


@pytest.fixture
def seeded_both():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM house_clerk_trades")
    conn.execute("DELETE FROM senate_efd_trades")
    today = datetime.now(tz=timezone.utc).date().isoformat()
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO house_clerk_trades
           (doc_id, txn_index, politician_name, state_dst, filing_date, ticker,
            asset_type, transaction_type, transaction_date, notification_date,
            amount_low, amount_high, raw_text, fetched_at)
           VALUES ('H1', 0, 'Nancy Pelosi', 'CA11', ?, 'NVDA', 'ST', 'buy',
                   ?, ?, 1001, 15000, 'raw', ?)""",
        (today, today, today, now_iso),
    )
    conn.execute(
        """INSERT INTO senate_efd_trades
           (filing_uuid, txn_index, politician_name, state, filing_date, ticker,
            asset_type, transaction_type, transaction_date, notification_date,
            amount_low, amount_high, raw_text, fetched_at)
           VALUES ('S1', 0, 'Mark Warner', 'VA', ?, 'NVDA', 'Stock', 'sell',
                   ?, ?, 15001, 50000, 'raw', ?)""",
        (today, today, today, now_iso),
    )
    conn.commit()
    conn.close()
    # Clear the congress cache so the union path actually runs.
    conn = get_connection()
    conn.execute("DELETE FROM cache WHERE key LIKE 'congress:%'")
    conn.commit()
    conn.close()
    yield
    conn = get_connection()
    conn.execute("DELETE FROM house_clerk_trades")
    conn.execute("DELETE FROM senate_efd_trades")
    conn.execute("DELETE FROM cache WHERE key LIKE 'congress:%'")
    conn.commit()
    conn.close()


def test_symbol_unions_house_and_senate(seeded_both):
    trades = CongressDataProvider().get_trades_by_symbol("NVDA", days=90)
    chambers = {t.chamber for t in trades}
    assert chambers == {"House", "Senate"}
    assert len(trades) == 2
    # Party stays Unknown for both pending the roster join.
    assert all(t.party == "Unknown" for t in trades)
    senate = next(t for t in trades if t.chamber == "Senate")
    assert senate.state == "VA"
    assert senate.transaction_type == "sell"


def test_top_traded_merges_counts(seeded_both):
    top = CongressDataProvider().get_top_traded_stocks(days=90)
    by_sym = {r["symbol"]: r["trade_count"] for r in top}
    assert by_sym["NVDA"] == 2  # 1 House + 1 Senate
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_congress_adapter_union.py -v`
Expected: FAIL — only House rows returned (chamber set is `{"House"}`, count 1).

- [ ] **Step 3: Modify `src/data/congress.py`**

3a. Add the Senate import beside the House one (near line 26):

```python
from src.data import house_clerk, senate_efd
```

3b. Replace `_fetch_trades_by_symbol` and `_fetch_trades_by_politician` (lines ~84-90) with union versions:

```python
    def _fetch_trades_by_symbol(self, symbol: str, days: int) -> list[CongressTrade]:
        house = [self._row_to_trade(r, "House")
                 for r in house_clerk.get_trades_by_symbol(symbol, days=days)]
        senate = [self._row_to_trade(r, "Senate")
                  for r in senate_efd.get_trades_by_symbol(symbol, days=days)]
        return house + senate

    def _fetch_trades_by_politician(self, name: str, days: int) -> list[CongressTrade]:
        house = [self._row_to_trade(r, "House")
                 for r in house_clerk.get_trades_by_politician(name, days=days)]
        senate = [self._row_to_trade(r, "Senate")
                  for r in senate_efd.get_trades_by_politician(name, days=days)]
        return house + senate
```

3c. Change `_row_to_trade` to accept a `chamber` arg and derive `state` per chamber. Replace its signature and the `state` / `chamber` lines (lines ~92-127):

```python
    def _row_to_trade(self, r: dict, chamber: str = "House") -> CongressTrade:
        """Convert a house_clerk_trades / senate_efd_trades row to a CongressTrade.

        Party is left "Unknown" -- neither feed carries it (a roster-join
        follow-up fills it). House state comes from the StateDst prefix (e.g.
        "CA17" -> "CA"); Senate rows carry a 2-letter `state` directly.
        """
        if chamber == "Senate":
            state = (r.get("state") or "").strip()
        else:
            state_dst = (r.get("state_dst") or "").strip()
            state = state_dst[:2] if len(state_dst) >= 2 else ""
```

Then further down in the same method, change the `chamber="House"` literal in the `CongressTrade(...)` constructor to `chamber=chamber`. Leave `party="Unknown"` as-is.

3d. Replace `get_top_traded_stocks` body (lines ~71-80) to merge both sources:

```python
    def get_top_traded_stocks(self, days: int = 90) -> list[dict]:
        cache_key = f"congress:top_traded:{days}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        counts: dict[str, int] = {}
        for src in (house_clerk.get_top_traded_stocks(days=days, limit=50),
                    senate_efd.get_top_traded_stocks(days=days, limit=50)):
            for row in src:
                counts[row["symbol"]] = counts.get(row["symbol"], 0) + row["trade_count"]
        result = [{"symbol": s, "trade_count": c}
                  for s, c in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)][:20]
        cache_set(cache_key, result, ttl_minutes=CACHE_TTL_FUNDAMENTALS)
        log_api_call("congress", "top_traded", "success")
        return result
```

3e. Update the module docstring (lines 14-18): replace the "House-only ... not covered here yet" paragraph with:

```python
Both chambers are now ingested: House via `src.data.house_clerk` and Senate
via `src.data.senate_efd`. Party affiliation is still "Unknown" for both --
the disclosure feeds don't carry it; a separate roster-enrichment join will
fill party + committees later.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_congress_adapter_union.py tests/test_congress_signal.py -v`
Expected: PASS — union returns both chambers; existing congress_signal tests still green.

- [ ] **Step 5: Commit**

```bash
git add src/data/congress.py tests/test_congress_adapter_union.py
git commit -m "feat(congress): union House + Senate trades, tag chamber"
```

---

## Task 9: Wire the Senate nightly refresh into startup

**Files:**
- Modify: `api/main.py` (after the `house_clerk_refresh` block, ~line 65)
- Modify: `src/data/house_clerk.py` (docstring note, lines 18-20)

- [ ] **Step 1: Add the scheduler block**

In `api/main.py`, immediately after the `except Exception as e:` that logs `"house_clerk scheduler failed"` (line ~65), add:

```python
    # Senate eFD PTR refresh — rolling 30-day window, nightly at 6:05 ET
    # (offset 5 min from the House job so both chambers don't refresh at once).
    try:
        from api.services._scheduler import schedule_daily_at
        from src.data.senate_efd import refresh_recent as _refresh_senate

        def _refresh_senate_efd():
            try:
                _refresh_senate(days=30, max_docs=50)
            except Exception:
                pass

        schedule_daily_at(6, 5, _refresh_senate_efd, name="senate_efd_refresh")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("senate_efd scheduler failed: %r", e)
```

- [ ] **Step 2: Update the House Clerk docstring note**

In `src/data/house_clerk.py`, replace lines 18-20 (the "Note: House-only ..." paragraph) with:

```python
Note: House-only. The Senate side lives in `src.data.senate_efd` (efd
search portal); the `congress` adapter unions both. This module stays
House-only by design.
```

- [ ] **Step 3: Verify the app imports cleanly**

Run: `python -c "import api.main"` (or `python3 -c "import api.main"`)
Expected: no ImportError / SyntaxError. (Startup scheduler threads are lazy; importing is enough to catch wiring mistakes.)

- [ ] **Step 4: Run the full congress/senate test suite**

Run: `pytest tests/test_senate_efd.py tests/test_congress_adapter_union.py tests/test_house_clerk.py tests/test_congress_signal.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add api/main.py src/data/house_clerk.py
git commit -m "feat(senate): nightly eFD refresh at 6:05 ET + docstring updates"
```

---

## Task 10: Full-suite regression check

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `pytest tests/ -q`
Expected: PASS (no regressions; the temp-DB fixture isolates everything from `trading.db`).

- [ ] **Step 2: Confirm no production-DB access in new tests**

Run: `grep -nE "trading\.db|DB_PATH|connect\(" tests/test_senate_efd.py tests/test_congress_adapter_union.py`
Expected: no matches (tests use only `get_connection()` / `init_db()`, redirected by the conftest temp-DB fixture).

- [ ] **Step 3: Final commit (if any stragglers)**

```bash
git status
# if clean, nothing to do
```

---

## Self-Review Notes (author)

- **Spec coverage:** schema (T1), session/agreement/CSRF flow (T4 `_establish_session`/`_search_page`), DataTables search + paper/electronic classification (T4), electronic HTML parse + tickerless drop (T3), paper skip + log (T5), idempotent rolling-window refresh (T6), queries (T7), adapter union + chamber + party-Unknown (T8), merged top-traded (T8), scheduler 6:05 ET (T9), docstring updates (T8/T9), tests with injected HTTP + temp DB (all). Roster join correctly left out of scope.
- **Type consistency:** `_fetch_and_store_one` / `fetch_index` / `refresh_recent` / `parse_ptr_html` / `get_trades_by_symbol` / `get_trades_by_politician` / `get_top_traded_stocks` names are used identically across module + tests + adapter. Index record keys (`filing_uuid`, `doc_kind`, `filing_type`, `politician_name`, `state`, `filing_date`) match between `_row_to_index_record`, `_fetch_and_store_one`, and the tests.
- **Note on T1/T2 ordering:** the schema test imports `senate_efd`, so it goes green only after T2 creates the module — call out to the executor that T1's test is verified at the end of T2.
```
