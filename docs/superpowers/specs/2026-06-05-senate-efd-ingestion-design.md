# Senate eFD Ingestion — Design Spec

**Date:** 2026-06-05
**Status:** Approved (pending spec review)
**Author:** brainstorming session

## Goal

Add a Senate-side congressional-trade ingester that mirrors the existing House
Clerk pipeline, closing the ~20% coverage gap left by the House-only data. The
Senate eFD portal (`efdsearch.senate.gov`) publishes Periodic Transaction
Reports (PTRs) through a stateful search portal rather than a static file drop,
so the ingester must handle a session/agreement/CSRF flow before it can read
filings.

After this work, `CongressDataProvider` returns House **and** Senate trades from
a single, unchanged public API. Downstream consumers (`congress_signal_service`,
`smart_money_service`, `ai_analyst_service`) keep working without changes.

## Non-Goals (YAGNI)

- **OCR of paper filings.** Senate PTRs come as electronic (HTML tables) or
  paper (scanned PDFs). Paper filings are skipped and logged, not OCR-guessed.
- **Party / chamber enrichment.** Senate trades land with `party="Unknown"`,
  exactly like House today. Filling party (for both chambers) is a separate
  follow-up spec: a shared `congress_members` roster join.
- **Committee data / conflict-of-interest flagging.** Depends on the roster
  join above; out of scope here.
- **Non-PTR reports.** Only `report_type=11` (Periodic Transaction Report).
  Annual reports, amendments, and blind-trust filings are ignored.

## Architecture

A new sibling module **`src/data/senate_efd.py`** mirroring
`src/data/house_clerk.py`. The existing House pipeline is **untouched**. The
`src/data/congress.py` adapter unions House + Senate rows into the existing
`CongressTrade` / `CongressTradesSummary` shapes.

```
congress.py (adapter)
   ├── house_clerk.py   (existing, unchanged)
   └── senate_efd.py    (new)
          ↓
   senate_efd_index / senate_efd_trades  (new tables in trading.db)
```

### Why a sibling module (not a unified table)

The House pipeline is proven and working. Refactoring both chambers into one
`congress_trades` table would require reworking proven code plus a data
migration, for no functional gain. A sibling module + union in the adapter is
the minimal-risk path and keeps each ingester independently testable.

## The Senate eFD protocol

Unlike House's static yearly ZIP, the Senate portal requires a session:

1. **`GET /search/home/`** — read the `csrftoken` cookie and the
   `csrfmiddlewaretoken` hidden form field from the returned HTML.
2. **`POST /search/home/`** with `prohibition_agreement=1` plus the CSRF token
   (sent via the `X-CSRFToken` header and a `Referer`) — accepts the usage
   agreement and establishes a session cookie.
3. **`POST /search/report/data/`** (DataTables AJAX endpoint) with:
   - `report_types[]=11` (Periodic Transaction Report)
   - `submitted_start_date` / `submitted_end_date` (rolling window — see below)
   - DataTables pagination: `draw`, `start`, `length`
   - empty filter fields (`first_name`, `last_name`, `senator_state`, ...)

   Returns JSON: `{ "data": [[first, last, office, report_link_html, date], ...],
   "recordsTotal": N, "recordsFiltered": N }`. Paginate until all rows in the
   window are collected (cap at `max_docs`).
4. **Classify each row's `report_link_html`** (an `<a href>`):
   - `/search/view/ptr/<uuid>/` → **electronic** (parseable HTML table)
   - `/search/view/paper/<uuid>/` → **paper** (scanned PDF → skip + log)
5. **`GET /search/view/ptr/<uuid>/`** — bs4-parse the transactions table.
   Columns: `#`, Transaction Date, Owner, Ticker, Asset Name, Asset Type, Type
   (Purchase/Sale/Exchange), Amount range, Comment.

All HTTP shares a single `httpx.Client` so cookies persist across the flow. A
polite `User-Agent` identifies the tool, same as `house_clerk._HEADERS`.

### Rolling-window approach

The House index is a whole-year file. The Senate portal is date-range-driven,
so `refresh_recent` takes a `days` window (default 30) and queries
`submitted_start_date = today - days`, `submitted_end_date = today`. Filings
already in the index with terminal status are skipped, so re-runs are cheap and
idempotent even with overlapping windows.

## Data model — two new tables (`src/utils/db.py` `init_db`)

### `senate_efd_trades`
Same column shape as `house_clerk_trades`, keyed on `(filing_uuid, txn_index)`:

```sql
CREATE TABLE IF NOT EXISTS senate_efd_trades (
    filing_uuid        TEXT NOT NULL,
    txn_index          INTEGER NOT NULL,
    politician_name    TEXT NOT NULL,
    state              TEXT,
    filing_date        TEXT,
    ticker             TEXT NOT NULL,
    asset_type         TEXT,
    transaction_type   TEXT,            -- buy | sell | exchange
    transaction_date   TEXT,            -- ISO YYYY-MM-DD
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
```

### `senate_efd_index`
Tracks which filings we've attempted (idempotent refresh):

```sql
CREATE TABLE IF NOT EXISTS senate_efd_index (
    filing_uuid     TEXT PRIMARY KEY,
    doc_kind        TEXT,              -- electronic | paper
    filing_type     TEXT,             -- always 'P' (PTR)
    politician_name TEXT,
    state           TEXT,
    filing_date     TEXT,
    last_attempted  TEXT,
    status          TEXT,             -- parsed | paper_unparsed | empty | http_error
    error           TEXT,
    fetched_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_sefi_status ON senate_efd_index(status);
```

Refresh skips filings whose status is `parsed` or `paper_unparsed` (terminal —
no point re-fetching an unparseable scan or an already-parsed filing).

## Public functions (`src/data/senate_efd.py`)

Parallel to `house_clerk`'s, so the adapter calls are symmetric:

- `fetch_index(*, days=30, max_docs=50, http_post=None, http_get=None) -> list[dict]`
  — run the session/agreement/search flow, return filing metadata records
  (`filing_uuid`, `doc_kind`, `politician_name`, `state`, `filing_date`).
- `parse_ptr_html(html: str) -> list[dict]` — bs4-parse one electronic PTR
  view into raw transaction dicts. Returns `[]` on missing/empty table.
- `_fetch_and_store_one(meta, *, http_get=None) -> int` — fetch + parse + store
  one filing; mark index status. Paper filings short-circuit to
  `status='paper_unparsed'`, return 0.
- `refresh_recent(*, days=30, max_docs=50, http_*=None) -> dict` — counts
  `{found, attempted, parsed, errored, empty, paper}`.
- `get_trades_by_symbol(symbol, days=180) -> list[dict]`
- `get_trades_by_politician(name, days=180) -> list[dict]`
- `get_top_traded_stocks(days=90, *, limit=20) -> list[dict]`

All HTTP fetchers are dependency-injected (default to real `httpx`) so tests
never touch the network — same pattern as `house_clerk`.

Normalization helpers reused/mirrored: `_norm_date`, `_norm_txn`
(Purchase→buy, Sale→sell, Exchange→exchange), `_parse_amount`.

## Adapter changes (`src/data/congress.py`)

- `_fetch_trades_by_symbol` / `_fetch_trades_by_politician`: union
  `house_clerk.*` + `senate_efd.*` rows.
- `_row_to_trade(r, chamber="House")`: add a `chamber` parameter. Senate rows
  pass `chamber="Senate"`. Party stays `"Unknown"` for both. Senate rows carry
  a plain 2-letter `state` (no `StateDst` split needed).
- `get_top_traded_stocks`: merge both sources' per-ticker counts.
- Update the module docstring: remove the "House-only" caveat; note Senate is
  now ingested but party remains `Unknown` pending the roster-join follow-up.

## Scheduler (`api/main.py`)

Add a second daily job right after the House one, offset 5 minutes so both
chambers don't refresh simultaneously:

```python
from src.data.senate_efd import refresh_recent as refresh_senate
def _refresh_senate_efd():
    try:
        refresh_senate(days=30, max_docs=50)
    except Exception:
        pass
schedule_daily_at(6, 5, _refresh_senate_efd, name="senate_efd_refresh")
```

Wrapped in the same try/except so a scheduler failure never breaks startup.

## Error handling & data integrity (per CLAUDE.md)

- Every HTTP / parse failure → `log_api_call("senate_efd", url, "error", ...)`,
  mark the index row, **return empty lists**. Never fabricate or fall back to
  synthetic data.
- Paper filings are explicitly skipped (`paper_unparsed`), never OCR-guessed.
- Tickerless rows (options/funds without a resolvable ticker) are dropped, same
  as House — no guessed symbols.
- **Point-in-time integrity:** use the actual filing / notification date as the
  "available at" timestamp. No lookahead.
- All prices/amounts handled as integers (cents-free dollar bounds) at storage,
  converted to `Decimal` in the adapter — consistent with House.

## Testing (`tests/`)

All tests use the temp-DB fixture and injected HTTP — no live calls, no prod DB,
synthetic data only in fixtures.

1. **`test_senate_efd_index`** — feed a captured DataTables JSON fixture to
   `fetch_index`; assert filing list, electronic vs paper classification, and
   `max_docs` cap.
2. **`test_senate_efd_parse`** — feed a captured electronic-PTR HTML fixture to
   `parse_ptr_html`; assert transactions including a multi-row table, a
   Purchase/Sale/Exchange of each type, and a tickerless row (dropped).
3. **`test_senate_efd_refresh`** — `refresh_recent` with injected fetchers;
   assert rows land in `senate_efd_trades`, paper filings marked
   `paper_unparsed` and not retried on a second run (idempotency).
4. **`test_congress_adapter_union`** — seed both `house_clerk_trades` and
   `senate_efd_trades` (synthetic symbols); assert the adapter unions them and
   sets `chamber` correctly (`House` vs `Senate`), party `Unknown` for both.

HTML/JSON fixtures live under `tests/fixtures/senate_efd/` and are captured
samples (sanitized), never live-fetched in CI.

## Follow-up (separate spec)

`congress_members` roster-enrichment join: load the
`unitedstates/congress-legislators` dataset into a `congress_members` table,
match `politician_name` → bioguide member, and fill `party` + `chamber` +
`committees` for **both** chambers in the adapter. Unlocks the
committee-vs-sector conflict-of-interest flag described in CLAUDE.md.
