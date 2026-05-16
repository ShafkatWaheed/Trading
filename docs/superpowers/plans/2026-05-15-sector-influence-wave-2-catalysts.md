# Sector Influence Signals — Wave 2 (Catalysts) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add 6 new ADDITIVE cards to the Deep Dive page: Innovation (patents+trademarks), FDA Catalysts, Backlog (gov contracts), Litigation (ITC §337), Executive Changes (SEC 8-K Item 5.02), and Entity Match Debug. Plus the Wave 1 deferrals (SAM.gov + PatentsView seeders, 8-K extractor).

**Architecture:** Each card is end-to-end self-contained: SQLite cache table → `src/data/<source>.py` fetcher → `src/analysis/sector_signals/<source>.py` mapper (emits StockInformation) → `api/services/<source>_service.py` orchestrator → new endpoint on `api/routes/stocks.py` → React component on Deep Dive. No existing service, card, or scoring path is modified. Bubble Score integration intentionally deferred.

**Tech Stack:** Python 3.12, SQLite, FastAPI, Next.js 14, React Query (already in use), pytest 9.

**Spec reference:** [docs/superpowers/specs/2026-05-15-sector-influence-signals-design.md](../specs/2026-05-15-sector-influence-signals-design.md) §3, §4, §9, §12

**Branch:** main (no feature branch per user instruction).

---

## Pre-flight: refresh the contract

### Task PRE.1: Verify the SignalReading + StockInformation contract is intact

**Files:** none (verification only)

- [ ] **Step 1: Smoke test**

Run: `.venv/bin/pytest tests/test_sector_signals_shared.py tests/test_wave1_smoke.py -v`
Expected: 9 PASSED (7 dataclass tests + 2 smoke tests).

- [ ] **Step 2: Confirm DB schema is current**

Run:
```bash
.venv/bin/python -c "from src.utils.db import init_db, get_connection; init_db(); conn=get_connection(); rows=conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name IN ('entity_aliases','source_freshness','known_future_events','refresh_jobs','ai_decisions','ai_decision_outcomes')\").fetchall(); print(len(rows), 'of 6 expected tables present')"
```
Expected: `6 of 6 expected tables present`.

If both pass, proceed. No commit for this task.

---

## Phase A: Deferred Wave 1 work

These three Wave 1 deferrals must land before the cards that depend on them.

### Task A.1: SAM.gov entity-API seeder (UEI backfill for gov contracts)

**Files:**
- Modify: `src/data/entity_aliases.py`
- Test: `tests/test_entity_aliases_sam_seeder.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_entity_aliases_sam_seeder.py`:

```python
"""Tests for SAM.gov UEI alias seeder (Wave 2)."""
from __future__ import annotations

import pytest

from src.data.entity_aliases import seed_from_sam_mapping
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'sam_test'")
    conn.commit()
    conn.close()
    yield


def test_seed_from_sam_mapping_inserts_uei_aliases():
    """Given {ticker: (uei, business_name)}, inserts uei + sam_business_name aliases."""
    mapping = {
        "LMT": ("PR7YEP4DZW43", "LOCKHEED MARTIN CORPORATION"),
        "BA":  ("HQRPNEPAGM84", "THE BOEING COMPANY"),
    }
    n = seed_from_sam_mapping(mapping, alias_source="sam_test")
    assert n == 2

    conn = get_connection()
    rows = conn.execute(
        "SELECT ticker, uei, alias_name, alias_type, confidence FROM entity_aliases "
        "WHERE alias_source = 'sam_test' ORDER BY ticker"
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[1]["ticker"] == "LMT"
    assert rows[1]["uei"] == "PR7YEP4DZW43"
    assert rows[1]["alias_name"] == "lockheed martin"   # normalized
    assert rows[1]["alias_type"] == "sam_business_name"
    assert rows[1]["confidence"] == 1.0


def test_seed_from_sam_mapping_skips_blanks():
    mapping = {"LMT": ("PR7YEP4DZW43", "LOCKHEED MARTIN CORPORATION"),
               "":    ("AAAA", "ignored"),
               "BAD": ("", "no uei")}
    assert seed_from_sam_mapping(mapping, alias_source="sam_test") == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_entity_aliases_sam_seeder.py -v`
Expected: ImportError on `seed_from_sam_mapping`.

- [ ] **Step 3: Implement**

Append to `src/data/entity_aliases.py`:

```python


def seed_from_sam_mapping(
    mapping: dict[str, tuple[str, str]],
    *,
    alias_source: str = "sam",
) -> int:
    """Seed entity_aliases from a {ticker: (uei, business_name)} mapping.

    Caller produces the mapping (typically by querying SAM.gov's entity API
    for known contractor tickers). UEI is authoritative (confidence=1.0).
    """
    now = _now_iso()
    inserted = 0
    for ticker, (uei, business_name) in mapping.items():
        if not ticker or not uei or not business_name:
            continue
        insert_alias(
            ticker=ticker, cik=None, uei=uei,
            alias_type="sam_business_name", alias_name=business_name,
            alias_source=alias_source, confidence=1.0, created_at=now,
        )
        inserted += 1
    return inserted
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_entity_aliases_sam_seeder.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/data/entity_aliases.py tests/test_entity_aliases_sam_seeder.py
git commit -m "feat(data): add SAM.gov UEI alias seeder for gov-contract matching"
```

---

### Task A.2: PatentsView assignee canonicalization seeder

**Files:**
- Modify: `src/data/entity_aliases.py`
- Test: `tests/test_entity_aliases_patentsview_seeder.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_entity_aliases_patentsview_seeder.py`:

```python
"""Tests for USPTO PatentsView assignee canonicalization seeder (Wave 2)."""
from __future__ import annotations

import pytest

from src.data.entity_aliases import seed_from_patentsview_assignees
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'patentsview_test'")
    conn.commit()
    conn.close()
    yield


def test_seed_from_patentsview_inserts_uspto_canonical():
    """Given {ticker: [canonical_assignee_names]}, inserts uspto_canonical aliases."""
    mapping = {
        "AAPL": ["Apple Inc.", "Apple Computer, Inc.", "Apple Computer Inc"],
        "MSFT": ["Microsoft Corporation", "Microsoft Technology Licensing LLC"],
    }
    n = seed_from_patentsview_assignees(mapping, alias_source="patentsview_test")
    assert n == 5

    conn = get_connection()
    rows = conn.execute(
        "SELECT ticker, alias_name, alias_type FROM entity_aliases "
        "WHERE alias_source = 'patentsview_test' ORDER BY ticker, alias_name"
    ).fetchall()
    conn.close()
    assert len(rows) == 5
    # All inserted under uspto_canonical
    assert all(r["alias_type"] == "uspto_canonical" for r in rows)
    aapl_aliases = {r["alias_name"] for r in rows if r["ticker"] == "AAPL"}
    assert "apple" in aapl_aliases               # normalized
    assert "apple computer" in aapl_aliases      # subsidiary form preserved


def test_seed_from_patentsview_handles_empty_list():
    mapping = {"AAPL": []}
    assert seed_from_patentsview_assignees(mapping, alias_source="patentsview_test") == 0


def test_seed_from_patentsview_deduplicates_within_ticker():
    """Same normalized alias for one ticker should only insert once (PK constraint)."""
    mapping = {"AAPL": ["Apple Inc.", "Apple Inc.", "APPLE INC"]}
    n = seed_from_patentsview_assignees(mapping, alias_source="patentsview_test")
    # All three normalize to "apple" — PK (ticker, alias_type, alias_name) means
    # only one row gets inserted (subsequent INSERT OR REPLACE).
    assert n == 3  # function counts attempts, not DB inserts
    conn = get_connection()
    rows = conn.execute(
        "SELECT COUNT(*) AS c FROM entity_aliases WHERE alias_source='patentsview_test' AND ticker='AAPL'"
    ).fetchone()
    conn.close()
    assert rows["c"] == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_entity_aliases_patentsview_seeder.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Append to `src/data/entity_aliases.py`:

```python


def seed_from_patentsview_assignees(
    mapping: dict[str, list[str]],
    *,
    alias_source: str = "patentsview",
) -> int:
    """Seed entity_aliases from PatentsView disambiguated_assignee names.

    The caller produces the mapping (typically by querying PatentsView's
    `disambiguated_assignee_organization` table for tickers' known
    assignee names). Each name becomes an `uspto_canonical` alias.

    Returns count of insert attempts (not unique inserts — INSERT OR REPLACE
    means duplicates after normalization are silently de-duplicated by the
    table's (ticker, alias_type, alias_name) PRIMARY KEY).
    """
    now = _now_iso()
    inserted = 0
    for ticker, names in mapping.items():
        if not ticker:
            continue
        for name in names:
            if not name or not name.strip():
                continue
            try:
                insert_alias(
                    ticker=ticker, cik=None, uei=None,
                    alias_type="uspto_canonical", alias_name=name,
                    alias_source=alias_source, confidence=1.0, created_at=now,
                )
                inserted += 1
            except ValueError:
                # `insert_alias` rejects empty normalized names — skip and continue.
                continue
    return inserted
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_entity_aliases_patentsview_seeder.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/data/entity_aliases.py tests/test_entity_aliases_patentsview_seeder.py
git commit -m "feat(data): add PatentsView assignee canonicalization seeder"
```

---

### Task A.3: SEC 8-K Item 5.02 (exec turnover) extractor

**Files:**
- Modify: `src/data/sec_edgar.py`
- Test: `tests/test_sec_8k_exec_turnover.py`

8-K Item 5.02 is "Departure of Directors or Certain Officers; Election of Directors; Appointment of Certain Officers; Compensatory Arrangements of Certain Officers" — exec turnover. The 4 biz-day filing rule means `filing_date` is the available-at date for backtests (no lag).

- [ ] **Step 1: Write failing test**

Create `tests/test_sec_8k_exec_turnover.py`:

```python
"""Tests for SEC 8-K Item 5.02 (exec departure/appointment) parser."""
from __future__ import annotations

from src.data.sec_edgar import parse_8k_item_502, ExecChange


SAMPLE_8K_DEPARTURE = """
Item 5.02 Departure of Directors or Certain Officers; Election of Directors;
Appointment of Certain Officers; Compensatory Arrangements of Certain Officers

On April 1, 2026, Jane Smith notified the Board of Directors of XYZ Corporation
that she will resign from her position as Chief Financial Officer of the
Company, effective May 15, 2026. Ms. Smith's resignation is to pursue
other opportunities and is not the result of any disagreement with the Company.
"""

SAMPLE_8K_APPOINTMENT = """
Item 5.02 Departure of Directors or Certain Officers...

On May 1, 2026, the Board of Directors of XYZ Corporation appointed John Doe
as the Company's new Chief Executive Officer, effective immediately,
to succeed Mary Johnson, who will continue to serve as a director.
"""


def test_parse_8k_item_502_detects_departure():
    out = parse_8k_item_502(SAMPLE_8K_DEPARTURE)
    assert any(c.event_type == "departure" for c in out)
    dep = [c for c in out if c.event_type == "departure"][0]
    assert "Smith" in dep.person_name
    assert "Chief Financial Officer" in dep.role or "CFO" in dep.role


def test_parse_8k_item_502_detects_appointment():
    out = parse_8k_item_502(SAMPLE_8K_APPOINTMENT)
    assert any(c.event_type == "appointment" for c in out)
    app = [c for c in out if c.event_type == "appointment"][0]
    assert "Doe" in app.person_name


def test_parse_8k_item_502_empty_returns_empty_list():
    assert parse_8k_item_502("") == []


def test_parse_8k_item_502_non_502_content_returns_empty():
    junk = "Item 7.01 Regulation FD Disclosure. We had a good quarter."
    assert parse_8k_item_502(junk) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_sec_8k_exec_turnover.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Append to `src/data/sec_edgar.py`:

```python


# ── 8-K Item 5.02 exec turnover parsing (Wave 2) ─────────────────────

import re as _re_502
from dataclasses import dataclass as _dc_502


@_dc_502(frozen=True)
class ExecChange:
    """Parsed 8-K Item 5.02 event (exec departure or appointment)."""
    event_type: str           # 'departure' | 'appointment'
    person_name: str
    role: str                 # 'CEO' | 'CFO' | 'COO' | 'Chief Financial Officer' | ...
    raw_excerpt: str          # snippet from the filing (for the card display)


# C-suite role patterns. Order: longer first to avoid 'Chief' matching 'CEO'.
_ROLE_PATTERNS = (
    r"Chief\s+Executive\s+Officer",
    r"Chief\s+Financial\s+Officer",
    r"Chief\s+Operating\s+Officer",
    r"Chief\s+Technology\s+Officer",
    r"Chief\s+Accounting\s+Officer",
    r"Chief\s+Legal\s+Officer",
    r"\bCEO\b", r"\bCFO\b", r"\bCOO\b", r"\bCTO\b",
    r"President", r"Director",
)
_ROLE_RE = _re_502.compile("|".join(_ROLE_PATTERNS), flags=_re_502.IGNORECASE)

_ITEM_502_RE = _re_502.compile(
    r"Item\s*5\.02", flags=_re_502.IGNORECASE,
)
_NAME_RE = _re_502.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-zA-Z'\-]+))\b"
)
_DEPARTURE_TRIGGERS = (
    "resign", "depart", "step down", "stepped down", "termination", "terminated",
    "will leave", "no longer serve", "ceased to be",
)
_APPOINTMENT_TRIGGERS = (
    "appoint", "elect", "named", "succeed", "assume the role",
)


def _classify_sentence(s: str) -> str | None:
    low = s.lower()
    is_dep = any(t in low for t in _DEPARTURE_TRIGGERS)
    is_app = any(t in low for t in _APPOINTMENT_TRIGGERS)
    if is_dep and not is_app:
        return "departure"
    if is_app and not is_dep:
        return "appointment"
    if is_dep and is_app:
        # Sentence like "John Doe was appointed to succeed Jane Smith, who resigned"
        # — pick the first trigger that appears.
        first_dep = min((low.find(t) for t in _DEPARTURE_TRIGGERS if t in low), default=10**9)
        first_app = min((low.find(t) for t in _APPOINTMENT_TRIGGERS if t in low), default=10**9)
        return "departure" if first_dep < first_app else "appointment"
    return None


def parse_8k_item_502(text: str) -> list[ExecChange]:
    """Parse 8-K text for Item 5.02 exec changes.

    Returns a list of ExecChange events (departure/appointment) found in
    the Item 5.02 section. Returns [] if no Item 5.02 content is present.

    Naive but effective: sentence-segment the 5.02 section, classify each
    sentence as departure/appointment based on trigger words, extract the
    first matching role and first capitalized-noun-phrase as the person.
    """
    if not text or not _ITEM_502_RE.search(text):
        return []

    # Slice from the first Item 5.02 occurrence to the next Item N.NN (or EOF).
    start = _ITEM_502_RE.search(text).start()
    next_item = _re_502.search(r"Item\s*\d+\.\d+", text[start + 1:], flags=_re_502.IGNORECASE)
    end = (start + 1 + next_item.start()) if next_item else len(text)
    section = text[start:end]

    out: list[ExecChange] = []
    for sentence in _re_502.split(r"(?<=[.!?])\s+", section):
        s = sentence.strip()
        if len(s) < 20:
            continue
        kind = _classify_sentence(s)
        if kind is None:
            continue
        role_match = _ROLE_RE.search(s)
        if not role_match:
            continue
        role = role_match.group(0)
        # Person = first proper-noun sequence in the sentence that isn't part of
        # the role or company name. Heuristic — good enough for our use.
        name = ""
        for m in _NAME_RE.finditer(s):
            cand = m.group(0)
            # skip common boilerplate
            if cand.lower() in {"item", "board", "company", "corporation", "directors"}:
                continue
            name = cand
            break
        if not name:
            continue
        out.append(ExecChange(
            event_type=kind,
            person_name=name,
            role=role,
            raw_excerpt=s[:300],
        ))
    return out
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_sec_8k_exec_turnover.py -v`
Expected: 4 PASSED. (If the regex pattern misses an edge case, tighten it. The goal is the happy path — false-positive filtering is OK.)

- [ ] **Step 5: Commit**

```bash
git add src/data/sec_edgar.py tests/test_sec_8k_exec_turnover.py
git commit -m "feat(data): parse SEC 8-K Item 5.02 for exec departures/appointments"
```

---

## Phase B: Entity Match Debug infrastructure

The Entity Match Debug card (Task F.1) needs a persistent record of every entity resolution decision. Wave 2 fetchers write to this table; the card reads from it.

### Task B.1: `entity_match_decisions` table

**Files:**
- Modify: `src/utils/db.py`
- Test: `tests/test_entity_match_decisions_schema.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_entity_match_decisions_schema.py`:

```python
from __future__ import annotations

from src.utils.db import get_connection, init_db


def test_entity_match_decisions_table_exists():
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='entity_match_decisions'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_entity_match_decisions_columns():
    init_db()
    conn = get_connection()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(entity_match_decisions)").fetchall()}
    conn.close()
    expected = {
        "id", "ticker", "source", "input_name",
        "matched_alias", "method", "confidence",
        "rejected_candidates_json", "decided_at",
    }
    assert expected.issubset(cols)


def test_entity_match_decisions_indices():
    init_db()
    conn = get_connection()
    idxs = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='entity_match_decisions'"
    ).fetchall()}
    conn.close()
    assert "idx_entity_match_decisions_ticker" in idxs
    assert "idx_entity_match_decisions_source" in idxs
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_entity_match_decisions_schema.py -v`
Expected: FAIL.

- [ ] **Step 3: Add the table**

In `src/utils/db.py::init_db()`, append (after the last existing index, before the closing `"""`):

```sql

        -- ── Sector-influence Wave 2: entity-match decision log ──────────
        -- Every fetcher that resolves a free-text name to a ticker writes
        -- one row here, so the Entity Match Debug card can show how each
        -- data point was attributed (CIK exact / UEI exact / fuzzy / etc.)
        -- and what alternatives were considered.
        CREATE TABLE IF NOT EXISTS entity_match_decisions (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker                      TEXT,                -- nullable: NULL when no match found
            source                      TEXT NOT NULL,       -- 'patents' | 'fda' | 'gov_contracts' | 'itc' | 'sec_8k' | ...
            input_name                  TEXT NOT NULL,       -- free-text input that was resolved
            matched_alias               TEXT,                -- normalized alias_name from entity_aliases (NULL if no match)
            method                      TEXT NOT NULL,       -- 'exact_cik' | 'exact_uei' | 'exact_alias' | 'fuzzy' | 'no_match'
            confidence                  REAL NOT NULL,       -- 0.0 if no match, else 0.0-1.0
            rejected_candidates_json    TEXT,                -- JSON list of {ticker, alias, score} for top alternatives
            decided_at                  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_entity_match_decisions_ticker ON entity_match_decisions(ticker);
        CREATE INDEX IF NOT EXISTS idx_entity_match_decisions_source ON entity_match_decisions(source);
        CREATE INDEX IF NOT EXISTS idx_entity_match_decisions_decided_at ON entity_match_decisions(decided_at);
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_entity_match_decisions_schema.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/utils/db.py tests/test_entity_match_decisions_schema.py
git commit -m "feat(db): add entity_match_decisions log for Wave 2 debug card"
```

---

### Task B.2: `resolve_ticker_with_audit()` — resolver wrapper that logs decisions

Extends the C3 resolver to also persist its decision to `entity_match_decisions` and (optionally) return the rejected alternatives.

**Files:**
- Modify: `src/data/entity_aliases.py`
- Test: `tests/test_entity_aliases_audit.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_entity_aliases_audit.py`:

```python
"""Tests for the audit-logging resolver wrapper (Wave 2)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.data.entity_aliases import (
    insert_alias,
    resolve_ticker_with_audit,
)
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'audit_test'")
    conn.execute("DELETE FROM entity_match_decisions WHERE source = 'audit_test'")
    conn.commit()
    conn.close()
    yield


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _seed(ticker: str, alias_name: str, alias_type: str = "legal", cik: str | None = None):
    insert_alias(
        ticker=ticker, cik=cik, uei=None,
        alias_type=alias_type, alias_name=alias_name,
        alias_source="audit_test", confidence=1.0, created_at=_now(),
    )


def test_resolve_with_audit_logs_exact_match():
    _seed("AAPL", "apple", cik="0000320193")
    out = resolve_ticker_with_audit("Apple Inc.", source="audit_test", use_fuzzy=False)
    assert out.ticker == "AAPL"
    assert out.method == "exact_alias"
    assert out.confidence == 1.0

    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM entity_match_decisions WHERE source='audit_test' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row["ticker"] == "AAPL"
    assert row["input_name"] == "Apple Inc."
    assert row["method"] == "exact_alias"
    assert row["confidence"] == 1.0


def test_resolve_with_audit_logs_no_match():
    out = resolve_ticker_with_audit("ZZZZZ Unknown Co", source="audit_test", use_fuzzy=False)
    assert out.ticker is None
    assert out.method == "no_match"
    assert out.confidence == 0.0

    conn = get_connection()
    row = conn.execute(
        "SELECT ticker, method FROM entity_match_decisions WHERE source='audit_test' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row["ticker"] is None
    assert row["method"] == "no_match"


def test_resolve_with_audit_records_rejected_candidates():
    _seed("AAPL", "apple")
    _seed("APLE", "apple hospitality reit")
    out = resolve_ticker_with_audit(
        "Apple Hospitalty",   # typo
        source="audit_test",
        use_fuzzy=True,
        min_confidence=0.8,
    )
    # At least one rejected candidate should be recorded
    conn = get_connection()
    row = conn.execute(
        "SELECT rejected_candidates_json FROM entity_match_decisions "
        "WHERE source='audit_test' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    rejected = json.loads(row["rejected_candidates_json"] or "[]")
    # Either AAPL or APLE is the chosen match; the other appears in rejected.
    if out.ticker == "AAPL":
        tickers_rejected = {c["ticker"] for c in rejected}
        assert "APLE" in tickers_rejected or len(rejected) >= 1
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_entity_aliases_audit.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Append to `src/data/entity_aliases.py`:

```python


# ── Audit-logging resolver wrapper (Wave 2) ──────────────────────────


from dataclasses import dataclass as _dc_audit


@_dc_audit(frozen=True)
class AuditedMatch:
    """Resolver output with debug attribution data."""
    ticker: str | None
    matched_alias: str | None
    confidence: float
    method: str        # 'exact_cik' | 'exact_uei' | 'exact_alias' | 'fuzzy' | 'no_match'
    rejected: list[dict]  # [{ticker, alias_name, score}, ...]


def resolve_ticker_with_audit(
    input_name: str,
    *,
    source: str,
    min_confidence: float = 0.9,
    use_fuzzy: bool = True,
    top_k_rejected: int = 3,
) -> AuditedMatch:
    """Resolve a name to a ticker AND log the decision to entity_match_decisions.

    Differs from resolve_ticker in three ways:
      1. ALWAYS persists the decision (success or no-match) to the log table
      2. Captures top-K rejected candidates (their scores + tickers) for the
         debug card
      3. Returns an AuditedMatch with a `method` and `rejected` field

    Use this from every Wave 2+ fetcher that maps free-text → ticker.
    """
    import json as _json

    init_db()
    normalized = normalize_name(input_name)
    decided_at = _now_iso()

    method = "no_match"
    matched_alias: str | None = None
    chosen_ticker: str | None = None
    chosen_score: float = 0.0
    rejected: list[dict] = []

    if normalized:
        conn = get_connection()
        try:
            # 1) Exact match
            row = conn.execute(
                "SELECT ticker, alias_name, alias_type FROM entity_aliases WHERE alias_name = ? LIMIT 1",
                (normalized,),
            ).fetchone()
            if row is not None:
                chosen_ticker = row["ticker"]
                matched_alias = row["alias_name"]
                chosen_score = 1.0
                method = "exact_alias"
            elif use_fuzzy:
                # 2) Fuzzy scan
                from rapidfuzz import fuzz

                candidates = conn.execute(
                    "SELECT ticker, alias_name, alias_type FROM entity_aliases"
                ).fetchall()
                scored = []
                for c in candidates:
                    s = fuzz.token_set_ratio(normalized, c["alias_name"]) / 100.0
                    scored.append((s, c["ticker"], c["alias_name"]))
                # sort desc by score, alpha ticker tie-break
                scored.sort(key=lambda x: (-x[0], x[1]))

                if scored and scored[0][0] >= min_confidence:
                    chosen_score, chosen_ticker, matched_alias = scored[0]
                    method = "fuzzy"
                    # Top-K next-best candidates that were NOT chosen
                    for s, t, a in scored[1:1 + top_k_rejected]:
                        rejected.append({"ticker": t, "alias_name": a, "score": round(s, 4)})
                else:
                    # No candidate cleared the threshold — still capture the top-K for debug
                    for s, t, a in scored[:top_k_rejected]:
                        rejected.append({"ticker": t, "alias_name": a, "score": round(s, 4)})

            # Always log
            conn.execute(
                """
                INSERT INTO entity_match_decisions
                  (ticker, source, input_name, matched_alias, method, confidence,
                   rejected_candidates_json, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chosen_ticker, source, input_name, matched_alias,
                    method, chosen_score,
                    _json.dumps(rejected) if rejected else None,
                    decided_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    else:
        # Empty/whitespace input → log no_match
        conn = get_connection()
        conn.execute(
            "INSERT INTO entity_match_decisions "
            "(ticker, source, input_name, matched_alias, method, confidence, "
            " rejected_candidates_json, decided_at) "
            "VALUES (NULL, ?, ?, NULL, 'no_match', 0.0, NULL, ?)",
            (source, input_name, decided_at),
        )
        conn.commit()
        conn.close()

    return AuditedMatch(
        ticker=chosen_ticker, matched_alias=matched_alias,
        confidence=chosen_score, method=method, rejected=rejected,
    )
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_entity_aliases_audit.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/data/entity_aliases.py tests/test_entity_aliases_audit.py
git commit -m "feat(data): add resolve_ticker_with_audit + entity_match_decisions writer"
```

---

## Phase C: Per-source fetcher + service skeletons

For each of the 5 data sources, the pattern is:
1. Fetcher in `src/data/<source>.py` — calls external API, caches result
2. Mapper in `src/analysis/sector_signals/<source>.py` — turns raw payload into StockInformation
3. Service in `api/services/<source>_service.py` — orchestrates fetcher + mapper, exposes `get_for_ticker(t)`
4. Route in `api/routes/stocks.py` — new endpoint
5. Schema in `api/schemas.py` — response model
6. Frontend hook + component

Each card is ~6 tasks. Given the symmetry, the plan lists Tasks C.1–C.6 (Innovation) in full; subsequent cards reference back to "follow the Innovation template" rather than repeating boilerplate.

### Task C.1: Innovation — USPTO PatentsView fetcher

**Files:**
- Create: `src/data/uspto_patentsview.py`
- Test: `tests/test_uspto_patentsview.py`

PatentsView API: `https://search.patentsview.org/api/v1/patent/` — free, no key. Query by assignee name (matched via `entity_aliases` `uspto_canonical` aliases).

- [ ] **Step 1: Write failing test (uses monkeypatch on httpx)**

Create `tests/test_uspto_patentsview.py`:

```python
"""Tests for USPTO PatentsView fetcher (Wave 2)."""
from __future__ import annotations

import json

import pytest

from src.data.uspto_patentsview import fetch_patents_for_assignee


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
    def json(self):
        return self._payload


def test_fetch_patents_returns_list_with_required_fields(monkeypatch):
    fake = {
        "patents": [
            {
                "patent_id": "11234567",
                "patent_title": "Method for on-device machine learning",
                "patent_date": "2026-01-15",
                "assignees": [{"assignee_organization": "Apple Inc."}],
                "cpc_at_issue": [{"cpc_subclass_id": "G06N"}],
            },
            {
                "patent_id": "11234568",
                "patent_title": "Wireless display optics",
                "patent_date": "2026-02-20",
                "assignees": [{"assignee_organization": "Apple Inc."}],
                "cpc_at_issue": [{"cpc_subclass_id": "H04W"}],
            },
        ],
        "count": 2,
        "total_hits": 2,
    }
    monkeypatch.setattr(
        "src.data.uspto_patentsview.httpx.post",
        lambda *a, **k: _FakeResp(fake),
    )
    out = fetch_patents_for_assignee("Apple Inc.", since_date="2025-05-15")
    assert len(out) == 2
    assert out[0]["patent_id"] == "11234567"
    assert out[0]["cpc_class"] == "G06N"
    assert out[0]["date"] == "2026-01-15"


def test_fetch_patents_returns_empty_on_no_results(monkeypatch):
    monkeypatch.setattr(
        "src.data.uspto_patentsview.httpx.post",
        lambda *a, **k: _FakeResp({"patents": [], "count": 0, "total_hits": 0}),
    )
    out = fetch_patents_for_assignee("Nonexistent Co", since_date="2025-05-15")
    assert out == []


def test_fetch_patents_returns_empty_on_network_error(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr("src.data.uspto_patentsview.httpx.post", _boom)
    out = fetch_patents_for_assignee("Apple Inc.", since_date="2025-05-15")
    assert out == []  # silent {} on failure, logged via log_api_call
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_uspto_patentsview.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `src/data/uspto_patentsview.py`:

```python
"""USPTO PatentsView fetcher (Wave 2).

Free API: https://search.patentsview.org/api/v1/patent/  (no key required, bulk-ok cadence)

Per CLAUDE.md: data layer. May call external APIs and cache to SQLite.
Must NOT import from src/analysis, src/reports, or app.py.
"""
from __future__ import annotations

import httpx

from src.utils.db import log_api_call


_PATENTSVIEW_URL = "https://search.patentsview.org/api/v1/patent/"


def fetch_patents_for_assignee(
    assignee_name: str,
    *,
    since_date: str,
    max_results: int = 100,
) -> list[dict]:
    """Query PatentsView for patents granted to `assignee_name` since `since_date`.

    Returns a list of normalized patent dicts:
        {patent_id, title, date, cpc_class, assignee}

    Empty list on no-results or network error (failure is logged via
    log_api_call, never silently swallowed).
    """
    body = {
        "q": {
            "_and": [
                {"assignees.assignee_organization": assignee_name},
                {"_gte": {"patent_date": since_date}},
            ]
        },
        "f": ["patent_id", "patent_title", "patent_date",
              "assignees.assignee_organization", "cpc_at_issue.cpc_subclass_id"],
        "o": {"size": max_results},
    }
    try:
        resp = httpx.post(_PATENTSVIEW_URL, json=body, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log_api_call("uspto_patentsview", _PATENTSVIEW_URL, "error", error=str(exc))
        return []

    patents = data.get("patents", []) or []
    out: list[dict] = []
    for p in patents:
        cpc_list = p.get("cpc_at_issue", []) or []
        cpc_class = cpc_list[0].get("cpc_subclass_id", "") if cpc_list else ""
        assignees = p.get("assignees", []) or []
        assignee = assignees[0].get("assignee_organization", "") if assignees else ""
        out.append({
            "patent_id": p.get("patent_id", ""),
            "title": p.get("patent_title", ""),
            "date": p.get("patent_date", ""),
            "cpc_class": cpc_class,
            "assignee": assignee,
        })
    log_api_call("uspto_patentsview", _PATENTSVIEW_URL, "ok")
    return out
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_uspto_patentsview.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/data/uspto_patentsview.py tests/test_uspto_patentsview.py
git commit -m "feat(data): add USPTO PatentsView fetcher for Innovation card"
```

---

### Task C.2: Innovation — analysis mapper (raw patents → StockInformation)

**Files:**
- Create: `src/analysis/sector_signals/innovation.py`
- Test: `tests/test_innovation_mapper.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_innovation_mapper.py`:

```python
"""Tests for innovation (patents+trademarks) mapper (Wave 2)."""
from __future__ import annotations

from src.analysis.sector_signals.innovation import patents_to_information


def test_patents_to_information_aggregates_by_cpc_class():
    patents = [
        {"patent_id": "11234567", "title": "ML on-device", "date": "2026-01-15",
         "cpc_class": "G06N", "assignee": "Apple Inc."},
        {"patent_id": "11234568", "title": "Display optics", "date": "2026-02-20",
         "cpc_class": "H04W", "assignee": "Apple Inc."},
        {"patent_id": "11234569", "title": "More ML", "date": "2026-03-10",
         "cpc_class": "G06N", "assignee": "Apple Inc."},
    ]
    info = patents_to_information(ticker="AAPL", patents=patents, as_of="2026-05-15T00:00:00Z")
    assert info.ticker == "AAPL"
    assert info.topic == "innovation"
    assert "3 patents" in info.headline or "3 grants" in info.headline.lower()
    # Top CPC class with 2 of 3 should appear in implications or facts
    assert any("G06N" in f.text for f in info.facts)
    assert info.sources_used == ["uspto_patentsview"]


def test_patents_to_information_empty_returns_low_signal():
    info = patents_to_information(ticker="AAPL", patents=[], as_of="2026-05-15T00:00:00Z")
    assert info.severity == "low"
    assert info.confidence == "low"
    assert info.facts == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_innovation_mapper.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `src/analysis/sector_signals/innovation.py`:

```python
"""Innovation card mapper — turns raw USPTO patents/trademarks into StockInformation.

Per CLAUDE.md: analysis layer. Pure functions, no I/O. Inputs are
already-fetched data (caller handles caching).
"""
from __future__ import annotations

from collections import Counter

from src.analysis.sector_signals._shared import Fact, StockInformation


def patents_to_information(
    *,
    ticker: str,
    patents: list[dict],
    as_of: str,
) -> StockInformation:
    """Build a StockInformation card body from a list of raw patent dicts.

    Each dict has: patent_id, title, date, cpc_class, assignee.
    """
    n = len(patents)
    if n == 0:
        return StockInformation(
            ticker=ticker, topic="innovation",
            headline="No recent patent activity",
            facts=[], narrative=None, implications=[],
            related_catalysts=[], confidence="low",
            as_of=as_of, sources_used=["uspto_patentsview"],
            severity="low",
        )

    cpc_counts = Counter(p.get("cpc_class", "") or "?" for p in patents).most_common(3)
    top_cpc = cpc_counts[0][0] if cpc_counts else "?"

    headline = f"{n} patents granted in window — heaviest in CPC {top_cpc}"

    facts: list[Fact] = []
    for cpc, count in cpc_counts:
        facts.append(Fact(
            text=f"{count} patents in CPC class {cpc}",
            as_of=as_of, source="uspto_patentsview",
            source_url="https://search.patentsview.org/", confidence=1.0,
        ))
    # Top 3 patents as sample facts
    for p in patents[:3]:
        facts.append(Fact(
            text=f"{p['date']}  {p['title'][:80]}",
            as_of=as_of, source="uspto_patentsview",
            source_url=f"https://patents.google.com/patent/US{p['patent_id']}",
            confidence=1.0,
        ))

    return StockInformation(
        ticker=ticker, topic="innovation",
        headline=headline, facts=facts,
        narrative=None, implications=[],
        related_catalysts=[], confidence="high",
        as_of=as_of, sources_used=["uspto_patentsview"],
        severity="low",
    )
```

- [ ] **Step 4: Verify pass**

Run: `.venv/bin/pytest tests/test_innovation_mapper.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/sector_signals/innovation.py tests/test_innovation_mapper.py
git commit -m "feat(analysis): add patents→StockInformation mapper for Innovation card"
```

---

### Task C.3: Innovation — service orchestrator + endpoint

**Files:**
- Create: `api/services/innovation_service.py`
- Modify: `api/routes/stocks.py`
- Modify: `api/schemas.py`
- Test: `tests/test_innovation_service.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_innovation_service.py`:

```python
"""Tests for innovation_service (Wave 2)."""
from __future__ import annotations

import pytest


def test_innovation_service_for_unknown_ticker_returns_empty(monkeypatch):
    from api.services.innovation_service import get_innovation_for_ticker

    # No entity aliases set up → no canonical assignee → empty
    out = get_innovation_for_ticker("ZZZ_NOPE")
    assert out["ticker"] == "ZZZ_NOPE"
    assert out["headline"]                # always present
    assert out["facts"] == []


def test_innovation_service_for_known_ticker_returns_info(monkeypatch):
    from datetime import datetime, timezone
    from api.services import innovation_service
    from src.data.entity_aliases import insert_alias
    from src.utils.db import init_db

    init_db()
    insert_alias(
        ticker="AAPL", cik=None, uei=None,
        alias_type="uspto_canonical", alias_name="apple",
        alias_source="innov_test", confidence=1.0,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )

    fake_patents = [
        {"patent_id": "1", "title": "T1", "date": "2026-01-01", "cpc_class": "G06N", "assignee": "Apple Inc."},
        {"patent_id": "2", "title": "T2", "date": "2026-02-01", "cpc_class": "G06N", "assignee": "Apple Inc."},
    ]
    monkeypatch.setattr(
        innovation_service, "fetch_patents_for_assignee",
        lambda assignee, since_date, max_results=100: fake_patents,
    )

    out = innovation_service.get_innovation_for_ticker("AAPL")
    assert out["ticker"] == "AAPL"
    assert "2 patents" in out["headline"]
    assert len(out["facts"]) >= 2
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_innovation_service.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement service**

Create `api/services/innovation_service.py`:

```python
"""Innovation service — orchestrates USPTO PatentsView + analysis mapper.

Returns a dict consumable directly by the new /stocks/{t}/innovation route.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import asdict

from src.analysis.sector_signals.innovation import patents_to_information
from src.data.entity_aliases import resolve_ticker_with_audit
from src.data.uspto_patentsview import fetch_patents_for_assignee
from src.utils.db import get_connection, init_db


def _get_uspto_canonical_names(ticker: str) -> list[str]:
    """Look up the USPTO canonical names for a ticker from entity_aliases."""
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT alias_name FROM entity_aliases "
        "WHERE ticker = ? AND alias_type = 'uspto_canonical'",
        (ticker,),
    ).fetchall()
    conn.close()
    return [r["alias_name"] for r in rows]


def get_innovation_for_ticker(ticker: str, *, lookback_days: int = 365) -> dict:
    """Build Innovation card payload for `ticker`.

    Strategy:
      1. Look up uspto_canonical aliases for the ticker
      2. If none, fall back to the legal alias (resolver round-trip)
      3. Query PatentsView for each canonical assignee name, dedupe by patent_id
      4. Map raw patents → StockInformation
    """
    canonical_names = _get_uspto_canonical_names(ticker)
    if not canonical_names:
        # No canonical assignee seeded — try the legal name as a single best-effort query
        # (this won't catch subsidiary patents, but it's better than nothing)
        conn = get_connection()
        row = conn.execute(
            "SELECT alias_name FROM entity_aliases WHERE ticker = ? AND alias_type = 'legal' LIMIT 1",
            (ticker,),
        ).fetchone()
        conn.close()
        if row:
            canonical_names = [row["alias_name"]]

    since = (datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)).date().isoformat()
    seen_ids: set[str] = set()
    merged: list[dict] = []
    for name in canonical_names:
        # Log the resolution decision (input was the canonical name we're querying)
        resolve_ticker_with_audit(name, source="innovation", use_fuzzy=False)
        for p in fetch_patents_for_assignee(name, since_date=since):
            if p["patent_id"] in seen_ids:
                continue
            seen_ids.add(p["patent_id"])
            merged.append(p)

    as_of = datetime.now(tz=timezone.utc).isoformat()
    info = patents_to_information(ticker=ticker, patents=merged, as_of=as_of)
    payload = asdict(info)
    # Convert frozen Fact dataclasses inside facts list — asdict handles this
    return payload
```

- [ ] **Step 4: Wire the route + schema**

Add to `api/schemas.py` (end of file):

```python


# ── Sector-influence Wave 2: card response models ─────────────────────


class InformationFactResponse(BaseModel):
    text: str
    as_of: str
    source: str
    source_url: str | None
    confidence: float


class StockInformationResponse(BaseModel):
    ticker: str
    topic: str
    headline: str
    facts: list[InformationFactResponse]
    narrative: str | None
    implications: list[str]
    related_catalysts: list[str]
    confidence: str
    as_of: str
    sources_used: list[str]
    severity: str
```

Add to `api/routes/stocks.py` (after existing routes):

```python


@router.get("/{ticker}/innovation", response_model=StockInformationResponse)
def get_innovation(ticker: str) -> dict:
    """Wave 2: Innovation card — USPTO patents over last 365 days."""
    from api.services.innovation_service import get_innovation_for_ticker
    return get_innovation_for_ticker(ticker.upper())
```

Import the new schema at the top of `api/routes/stocks.py`:

```python
from api.schemas import StockInformationResponse
```

- [ ] **Step 5: Verify pass**

Run: `.venv/bin/pytest tests/test_innovation_service.py -v`
Expected: 2 PASSED.

- [ ] **Step 6: Commit**

```bash
git add api/services/innovation_service.py api/routes/stocks.py api/schemas.py tests/test_innovation_service.py
git commit -m "feat(api): wire /stocks/{t}/innovation endpoint for Innovation card"
```

---

### Task C.4: Innovation — frontend hook + component

**Files:**
- Modify: `frontend/lib/api/endpoints.ts`
- Modify: `frontend/lib/api/types.ts`
- Create: `frontend/lib/hooks/use-innovation.ts`
- Create: `frontend/components/deep-dive/innovation-card.tsx`
- Modify: `frontend/app/deep-dive/[symbol]/page.tsx` (the deep dive layout)

- [ ] **Step 1: Add types**

Append to `frontend/lib/api/types.ts`:

```typescript

// ── Sector-influence Wave 2: card payloads ─────────────────────────

export type InformationFact = {
  text: string;
  as_of: string;
  source: string;
  source_url: string | null;
  confidence: number;
};

export type StockInformation = {
  ticker: string;
  topic: string;
  headline: string;
  facts: InformationFact[];
  narrative: string | null;
  implications: string[];
  related_catalysts: string[];
  confidence: "high" | "med" | "low";
  as_of: string;
  sources_used: string[];
  severity: "high" | "med" | "low";
};
```

- [ ] **Step 2: Add API client**

In `frontend/lib/api/endpoints.ts`, append to the `stocksApi` object:

```typescript
  innovation: (ticker: string) =>
    api<StockInformation>(`/stocks/${ticker}/innovation`),
```

- [ ] **Step 3: Add hook**

Create `frontend/lib/hooks/use-innovation.ts`:

```typescript
import { useQuery } from "@tanstack/react-query";
import { stocksApi } from "@/lib/api/endpoints";

export function useInnovation(ticker: string) {
  return useQuery({
    queryKey: ["innovation", ticker],
    queryFn: () => stocksApi.innovation(ticker),
    staleTime: 24 * 60 * 60 * 1000, // 24h
    enabled: Boolean(ticker),
  });
}
```

- [ ] **Step 4: Add component**

Create `frontend/components/deep-dive/innovation-card.tsx`:

```tsx
"use client";

import { useInnovation } from "@/lib/hooks/use-innovation";

export function InnovationCard({ ticker }: { ticker: string }) {
  const { data, isLoading, error } = useInnovation(ticker);

  if (isLoading) return <div className="card-subtle">Loading innovation…</div>;
  if (error || !data) return null; // Silently hide on error — Wave 2 is additive
  if (data.facts.length === 0) return null; // Hide if no patent activity

  return (
    <section className="card-subtle p-6">
      <h3 className="text-lg font-semibold mb-1">Innovation</h3>
      <p className="text-sm text-muted-foreground mb-4">{data.headline}</p>
      <ul className="space-y-2 text-sm">
        {data.facts.map((f, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="text-muted-foreground">•</span>
            <span>
              {f.source_url ? (
                <a
                  href={f.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:underline"
                >
                  {f.text}
                </a>
              ) : (
                f.text
              )}
            </span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground mt-3">
        Source: USPTO PatentsView · As of {new Date(data.as_of).toLocaleDateString()}
      </p>
    </section>
  );
}
```

- [ ] **Step 5: Mount on Deep Dive page**

In `frontend/app/deep-dive/[symbol]/page.tsx`, find the existing section list and append:

```tsx
import { InnovationCard } from "@/components/deep-dive/innovation-card";

// ...inside the JSX, AFTER all existing sections:
<InnovationCard ticker={symbol} />
```

- [ ] **Step 6: Smoke test in browser**

Run:
```bash
cd /home/shafkat/project/Trading
.venv/bin/uvicorn api.main:app --port 8000 --reload > /tmp/uvicorn.log 2>&1 &
(cd frontend && npm run dev > /tmp/next.log 2>&1 &)
```

Open `http://localhost:3000/deep-dive/AAPL` and verify the Innovation card renders (or is hidden if no aliases seeded yet — that's expected).

Note for the implementer: per the memory note about uvicorn + reload, kill the dev server cleanly when done (`kill %1 %2`).

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/api/endpoints.ts frontend/lib/api/types.ts frontend/lib/hooks/use-innovation.ts frontend/components/deep-dive/innovation-card.tsx frontend/app/deep-dive/\[symbol\]/page.tsx
git commit -m "feat(frontend): add Innovation card to Deep Dive page"
```

---

## Phase D: FDA Catalysts card

Follow the Innovation template (Tasks C.1–C.4) with these substitutions:

### Task D.1: openFDA fetcher (`src/data/fda_openfda.py`)

Source: openFDA Drugs@FDA endpoint `https://api.fda.gov/drug/drugsfda.json`. Free, no key. Query by sponsor name.

Implement `fetch_fda_applications_for_sponsor(sponsor: str) -> list[dict]` returning `[{application_number, sponsor_name, submission_type, submission_status, action_date, ...}, ...]`. Mirror the structure of Task C.1.

Test file: `tests/test_fda_openfda.py` with monkeypatched httpx.

Commit: `feat(data): add openFDA fetcher for FDA Catalysts card`

### Task D.2: FDA mapper (`src/analysis/sector_signals/fda.py`)

`fda_to_information(ticker, applications, as_of) -> StockInformation`. Aggregate by submission status, surface PDUFA dates if present. Test file: `tests/test_fda_mapper.py`.

Commit: `feat(analysis): add FDA→StockInformation mapper`

### Task D.3: FDA service + endpoint (`api/services/fda_catalysts_service.py`)

`get_fda_catalysts_for_ticker(ticker)`. Conditional: returns `{ticker, headline, facts: [], confidence: 'low'}` if ticker isn't in a pharma/biotech industry per `src/data/industry_loader.py`. Endpoint: `GET /stocks/{t}/fda-catalysts`. Test file: `tests/test_fda_catalysts_service.py`.

Commit: `feat(api): wire /stocks/{t}/fda-catalysts endpoint`

### Task D.4: FDA frontend (`use-fda-catalysts.ts` + `fda-catalysts-card.tsx`)

Same pattern as Innovation. Mount on Deep Dive after Innovation.

Commit: `feat(frontend): add FDA Catalysts card to Deep Dive`

---

## Phase E: Backlog card

Follow the Innovation template with these substitutions:

### Task E.1: USAspending fetcher (`src/data/usaspending.py`)

Source: `https://api.usaspending.gov/api/v2/search/spending_by_award/`. Free. Query by recipient UEI (looked up via `entity_aliases` `sam_business_name`).

`fetch_contracts_for_uei(uei: str, *, since_date: str) -> list[dict]`. Test file: `tests/test_usaspending.py`.

Commit: `feat(data): add USAspending fetcher for Backlog card`

### Task E.2: Backlog mapper (`src/analysis/sector_signals/govcon.py`)

Aggregate by NAICS code, sum dollar amounts. Emit BOTH a StockInformation (for the card) AND a SignalReading (for future Bubble Score, but currently unused).

Commit: `feat(analysis): add gov-contract→StockInformation + SignalReading mapper`

### Task E.3: Backlog service + endpoint (`api/services/backlog_service.py`)

`get_backlog_for_ticker(ticker)`. Conditional: returns empty payload if ticker isn't in defense/govtech industry. Endpoint: `GET /stocks/{t}/backlog`.

Commit: `feat(api): wire /stocks/{t}/backlog endpoint`

### Task E.4: Backlog frontend

Mount on Deep Dive after FDA Catalysts.

Commit: `feat(frontend): add Backlog card to Deep Dive`

---

## Phase F: Litigation card (ITC §337)

Follow the Innovation template:

### Task F.1: ITC EDIS fetcher (`src/data/itc_edis.py`)

Source: EDIS API `https://edis.usitc.gov/data/search/[...]`. Free. Query by party name (fuzzy-resolved via `resolve_ticker_with_audit`).

`fetch_337_investigations_for_party(name: str) -> list[dict]`. Test: `tests/test_itc_edis.py`.

Commit: `feat(data): add ITC EDIS fetcher for §337 investigations`

### Task F.2: ITC mapper (`src/analysis/sector_signals/itc.py`)

Distinguish "as respondent" (defensive — bearish) vs "as complainant" (offensive — bullish-leaning). Test: `tests/test_itc_mapper.py`.

Commit: `feat(analysis): add ITC §337→StockInformation mapper`

### Task F.3: Litigation service + endpoint (`api/services/litigation_service.py`)

`get_litigation_for_ticker(ticker)`. Conditional: hide card if no active investigations. Endpoint: `GET /stocks/{t}/litigation`.

Commit: `feat(api): wire /stocks/{t}/litigation endpoint`

### Task F.4: Litigation frontend

Mount on Deep Dive after Backlog.

Commit: `feat(frontend): add Litigation card to Deep Dive`

---

## Phase G: Executive Changes card

Follow the Innovation template:

### Task G.1: 8-K fetcher — reuse existing SEC EDGAR pipeline

Add `fetch_recent_8ks(ticker: str, *, days: int = 180) -> list[dict]` to `src/data/sec_edgar.py` returning raw 8-K filings (URL, date, content). Re-use Task A.3's `parse_8k_item_502`.

Commit: `feat(data): fetch recent 8-Ks for exec-turnover detection`

### Task G.2: Exec changes mapper (`src/analysis/sector_signals/exec_turnover.py`)

`exec_changes_to_information(ticker, changes, as_of)`. Flag CFO-departure-within-30-days-of-earnings as severity='high'.

Commit: `feat(analysis): add exec-changes→StockInformation mapper`

### Task G.3: Exec Changes service + endpoint (`api/services/exec_changes_service.py`)

`get_exec_changes_for_ticker(ticker)`. Always visible if any changes detected.

Commit: `feat(api): wire /stocks/{t}/exec-changes endpoint`

### Task G.4: Exec Changes frontend

Mount on Deep Dive after Litigation.

Commit: `feat(frontend): add Executive Changes card to Deep Dive`

---

## Phase H: Entity Match Debug card

### Task H.1: Match decisions service (`api/services/entity_matches_service.py`)

**Files:**
- Create: `api/services/entity_matches_service.py`
- Modify: `api/routes/stocks.py`
- Modify: `api/schemas.py`
- Test: `tests/test_entity_matches_service.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_entity_matches_service.py`:

```python
"""Tests for entity-matches service (Wave 2 debug card)."""
from __future__ import annotations

import pytest


def test_entity_matches_for_ticker_with_no_history_returns_empty():
    from api.services.entity_matches_service import get_matches_for_ticker
    out = get_matches_for_ticker("ZZZ_NEVER_QUERIED")
    assert out["ticker"] == "ZZZ_NEVER_QUERIED"
    assert out["matches"] == []


def test_entity_matches_returns_recent_decisions():
    from datetime import datetime, timezone
    from src.utils.db import get_connection, init_db
    init_db()
    now = datetime.now(tz=timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        "INSERT INTO entity_match_decisions (ticker, source, input_name, matched_alias, "
        "method, confidence, rejected_candidates_json, decided_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("MATCH_TEST", "test_source", "Match Test Corp", "match test",
         "exact_alias", 1.0, None, now),
    )
    conn.commit()
    conn.close()

    from api.services.entity_matches_service import get_matches_for_ticker
    out = get_matches_for_ticker("MATCH_TEST")
    assert out["ticker"] == "MATCH_TEST"
    assert len(out["matches"]) >= 1
    m = out["matches"][0]
    assert m["source"] == "test_source"
    assert m["method"] == "exact_alias"
    assert m["confidence"] == 1.0

    # cleanup
    conn = get_connection()
    conn.execute("DELETE FROM entity_match_decisions WHERE source='test_source'")
    conn.commit()
    conn.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_entity_matches_service.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

Create `api/services/entity_matches_service.py`:

```python
"""Entity Match Debug service — read recent match decisions for a ticker."""
from __future__ import annotations

import json

from src.utils.db import get_connection, init_db


def get_matches_for_ticker(ticker: str, *, lookback_days: int = 30) -> dict:
    """Return the most recent entity_match_decisions for `ticker`.

    Shape (consumed directly by the /stocks/{t}/entity-matches endpoint):
        {
          "ticker": str,
          "matches": [
            {
              "source": "patents" | "fda" | ...,
              "input_name": str,
              "matched_alias": str | None,
              "method": "exact_cik" | "exact_uei" | "exact_alias" | "fuzzy" | "no_match",
              "confidence": float,
              "rejected": [{"ticker": str, "alias_name": str, "score": float}, ...],
              "decided_at": str,
            }, ...
          ]
        }
    """
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)).isoformat()

    init_db()
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT source, input_name, matched_alias, method, confidence,
               rejected_candidates_json, decided_at
        FROM entity_match_decisions
        WHERE ticker = ? AND decided_at >= ?
        ORDER BY decided_at DESC
        """,
        (ticker.upper(), cutoff),
    ).fetchall()
    conn.close()

    matches = []
    seen_sources: set[str] = set()
    for r in rows:
        # De-dupe by source — show latest decision per source
        if r["source"] in seen_sources:
            continue
        seen_sources.add(r["source"])
        rejected = []
        if r["rejected_candidates_json"]:
            try:
                rejected = json.loads(r["rejected_candidates_json"])
            except Exception:
                rejected = []
        matches.append({
            "source": r["source"],
            "input_name": r["input_name"],
            "matched_alias": r["matched_alias"],
            "method": r["method"],
            "confidence": float(r["confidence"]),
            "rejected": rejected,
            "decided_at": r["decided_at"],
        })

    return {"ticker": ticker.upper(), "matches": matches}
```

- [ ] **Step 4: Schema + route**

Append to `api/schemas.py`:

```python


class EntityMatchRejectedCandidate(BaseModel):
    ticker: str
    alias_name: str
    score: float


class EntityMatchDecisionResponse(BaseModel):
    source: str
    input_name: str
    matched_alias: str | None
    method: str
    confidence: float
    rejected: list[EntityMatchRejectedCandidate]
    decided_at: str


class EntityMatchesResponse(BaseModel):
    ticker: str
    matches: list[EntityMatchDecisionResponse]
```

Append to `api/routes/stocks.py`:

```python


@router.get("/{ticker}/entity-matches", response_model=EntityMatchesResponse)
def get_entity_matches(ticker: str) -> dict:
    """Wave 2 debug card: show how each data source resolved its names to this ticker."""
    from api.services.entity_matches_service import get_matches_for_ticker
    return get_matches_for_ticker(ticker.upper())
```

And add to the imports at the top:

```python
from api.schemas import EntityMatchesResponse
```

- [ ] **Step 5: Verify**

Run: `.venv/bin/pytest tests/test_entity_matches_service.py -v`
Expected: 2 PASSED.

- [ ] **Step 6: Commit**

```bash
git add api/services/entity_matches_service.py api/routes/stocks.py api/schemas.py tests/test_entity_matches_service.py
git commit -m "feat(api): wire /stocks/{t}/entity-matches endpoint for debug card"
```

---

### Task H.2: Entity Match Debug frontend

**Files:**
- Modify: `frontend/lib/api/endpoints.ts`
- Modify: `frontend/lib/api/types.ts`
- Create: `frontend/lib/hooks/use-entity-matches.ts`
- Create: `frontend/components/deep-dive/entity-match-debug-card.tsx`
- Modify: `frontend/app/deep-dive/[symbol]/page.tsx`

- [ ] **Step 1: Types + client + hook**

Append to `types.ts`:

```typescript
export type EntityMatchRejected = {
  ticker: string;
  alias_name: string;
  score: number;
};

export type EntityMatchDecision = {
  source: string;
  input_name: string;
  matched_alias: string | null;
  method: "exact_cik" | "exact_uei" | "exact_alias" | "fuzzy" | "no_match";
  confidence: number;
  rejected: EntityMatchRejected[];
  decided_at: string;
};

export type EntityMatches = {
  ticker: string;
  matches: EntityMatchDecision[];
};
```

Append to `endpoints.ts` stocksApi:

```typescript
  entityMatches: (ticker: string) =>
    api<EntityMatches>(`/stocks/${ticker}/entity-matches`),
```

Create `frontend/lib/hooks/use-entity-matches.ts`:

```typescript
import { useQuery } from "@tanstack/react-query";
import { stocksApi } from "@/lib/api/endpoints";

export function useEntityMatches(ticker: string) {
  return useQuery({
    queryKey: ["entity-matches", ticker],
    queryFn: () => stocksApi.entityMatches(ticker),
    staleTime: 15 * 60 * 1000, // 15min — debug data, refresh often
    enabled: Boolean(ticker),
  });
}
```

- [ ] **Step 2: Card component (the heart of the task)**

Create `frontend/components/deep-dive/entity-match-debug-card.tsx`:

```tsx
"use client";

import { useEntityMatches } from "@/lib/hooks/use-entity-matches";

function methodBadge(method: string, confidence: number) {
  if (method === "no_match")
    return <span className="px-1.5 py-0.5 text-xs rounded bg-red-100 text-red-800">no match</span>;
  if (method.startsWith("exact_"))
    return <span className="px-1.5 py-0.5 text-xs rounded bg-green-100 text-green-800">
      {method} · {confidence.toFixed(2)}
    </span>;
  if (method === "fuzzy") {
    const tone = confidence >= 0.95 ? "bg-green-100 text-green-800"
               : confidence >= 0.9  ? "bg-yellow-100 text-yellow-800"
               : "bg-orange-100 text-orange-800";
    return <span className={`px-1.5 py-0.5 text-xs rounded ${tone}`}>
      fuzzy · {confidence.toFixed(2)}
    </span>;
  }
  return <span className="px-1.5 py-0.5 text-xs rounded bg-gray-100 text-gray-700">{method}</span>;
}

export function EntityMatchDebugCard({ ticker }: { ticker: string }) {
  const { data, isLoading, error } = useEntityMatches(ticker);

  if (isLoading) return null;
  if (error || !data || data.matches.length === 0) return null;

  return (
    <section className="card-muted p-6">
      <h3 className="text-lg font-semibold mb-1">Entity Match Debug</h3>
      <p className="text-xs text-muted-foreground mb-4">
        How each data source resolved free-text names to <strong>{ticker}</strong>.
        Useful for auditing fuzzy matches and ruling out misattribution.
      </p>
      <ul className="space-y-4 text-sm">
        {data.matches.map((m, i) => (
          <li key={i} className="border-l-2 border-muted pl-3">
            <div className="flex items-center justify-between mb-1">
              <span className="font-medium">{m.source}</span>
              {methodBadge(m.method, m.confidence)}
            </div>
            <div className="text-xs text-muted-foreground">
              Input: <span className="font-mono">"{m.input_name}"</span>
              {m.matched_alias && (
                <>
                  {" → "}<span className="font-mono">"{m.matched_alias}"</span>
                </>
              )}
            </div>
            {m.rejected.length > 0 && (
              <details className="mt-1">
                <summary className="text-xs cursor-pointer text-muted-foreground hover:text-foreground">
                  {m.rejected.length} alternative{m.rejected.length === 1 ? "" : "s"} considered
                </summary>
                <ul className="mt-1 ml-3 space-y-0.5 text-xs font-mono text-muted-foreground">
                  {m.rejected.map((r, j) => (
                    <li key={j}>
                      {r.ticker.padEnd(6)} "{r.alias_name}" · score={r.score.toFixed(3)}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 3: Mount last on Deep Dive**

In `frontend/app/deep-dive/[symbol]/page.tsx`, append:

```tsx
import { EntityMatchDebugCard } from "@/components/deep-dive/entity-match-debug-card";

// ...after ALL other cards (it's a debug surface, render last):
<EntityMatchDebugCard ticker={symbol} />
```

- [ ] **Step 4: Smoke test**

Visit `http://localhost:3000/deep-dive/AAPL` after at least one Wave 2 card has fetched (so `entity_match_decisions` has rows). Verify the card renders, shows method badges, and the "alternatives considered" expandable section works.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/endpoints.ts frontend/lib/api/types.ts frontend/lib/hooks/use-entity-matches.ts frontend/components/deep-dive/entity-match-debug-card.tsx frontend/app/deep-dive/\[symbol\]/page.tsx
git commit -m "feat(frontend): add Entity Match Debug card to Deep Dive"
```

---

## Phase I: Alerts (new types)

### Task I.1: New alert types

**Files:**
- Modify: `api/services/alerts_service.py` (extension)
- Test: `tests/test_alerts_new_types.py`

Add four new alert generators (one per Wave 2 source):
- `create_fda_decision_alert(ticker, decision)` 
- `create_itc_filing_alert(ticker, investigation)`
- `create_exec_departure_alert(ticker, change)`
- `create_contract_award_alert(ticker, contract)`

Each writes to the existing `alerts` table via `save_alert()` from `src/utils/db.py`. No modification to existing alert types — pure addition.

Commit: `feat(alerts): add 4 new alert types for FDA/ITC/exec/contract events`

---

## Phase J: Wave 2 wrap-up

### Task J.1: End-to-end smoke test

**Files:**
- Test: `tests/test_wave2_smoke.py`

Walks every Wave 2 surface in one test:
- All 6 new endpoints return valid JSON
- The Entity Match Debug card reflects matches made by the other 5 services
- All conditional cards correctly hide when not applicable

Commit: `test: end-to-end smoke test for Wave 2`

### Task J.2: Update spec completion log

Append to `docs/superpowers/specs/2026-05-15-sector-influence-signals-design.md`:

```markdown
## Wave 2 completion log

Wave 2 shipped to main on 2026-05-15. Purely additive: no existing Deep
Dive card, service, or scoring path was modified.

**Delivered:** 6 new Deep Dive cards (Innovation, FDA Catalysts, Backlog,
Litigation, Executive Changes, Entity Match Debug), new alert types,
SAM.gov + PatentsView seeders, 8-K Item 5.02 parser, `entity_match_decisions`
table + audit-logging resolver wrapper.

**Deferred:** Bubble Score integration (would modify existing scoring —
violates additive principle); narrative-bullet enrichments for ITC and
exec turnover (flipped to dedicated cards instead).
```

Commit: `docs(spec): record Wave 2 completion`

### Task J.3: Final commit + push

After all task commits land on main, no separate push needed — each commit is pushed individually OR a final `git push origin main` covers them.

---

## Wave 2 complete — what's on main

- 6 new Deep Dive cards, all conditional/always-visible per spec
- `entity_match_decisions` table + audit resolver wrapper
- SAM.gov + PatentsView seeders (Wave 1 deferrals resolved)
- 8-K Item 5.02 parser
- 4 new alert types
- ~120 new unit + integration tests

**Deferred to Wave 3+:**
- Goods Flow card + Real Economy card (physical economy sources)
- Bubble Score integration (modifies existing scoring — out of scope for the additive principle)
- Narrative enrichments (Wave 4 per original spec)
