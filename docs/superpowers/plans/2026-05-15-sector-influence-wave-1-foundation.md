# Sector Influence Signals — Wave 1 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation layer for Wave 1 of the sector-influence-signals spec: entity-alias resolver, shared dataclasses (`Fact`, `StockInformation`, `SignalReading`), point-in-time backtest validator, per-source freshness registration, and DB schema additions. No user-visible change. Unblocks Waves 2-4.

**Architecture:** Three new SQLite tables (`entity_aliases`, `source_freshness`, `known_future_events`) added via the existing `init_db()` script. New module `src/analysis/sector_signals/_shared.py` holds frozen dataclasses. New module `src/data/entity_aliases.py` does name normalization + ticker resolution (exact-match for IDs, ≥0.9 fuzzy for scored, ≥0.8 for information). `edge_validator.py` gets a new `assert_no_lookahead()` function called from `backtester.py`. All architecture decisions follow CLAUDE.md dependency rules: `data/` and `analysis/` never cross-import; `analysis/` is pure (no I/O); `Decimal` for financial values.

**Tech Stack:** Python 3.12, SQLite, pytest 9.0.2, dataclasses (frozen), `rapidfuzz` (new dep), PyYAML, existing `src/utils/db.py` helpers.

**Spec reference:** [docs/superpowers/specs/2026-05-15-sector-influence-signals-design.md](../specs/2026-05-15-sector-influence-signals-design.md)

---

## Pre-flight: dependencies

### Task 0: Add `rapidfuzz` dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add rapidfuzz to requirements**

Edit `requirements.txt` and append (after `beautifulsoup4`):

```
rapidfuzz>=3.6.0
pyyaml>=6.0
```

- [ ] **Step 2: Install in the active venv**

Run: `.venv/bin/pip install 'rapidfuzz>=3.6.0' 'pyyaml>=6.0'`
Expected: `Successfully installed rapidfuzz-... pyyaml-...` (or "already installed" for pyyaml)

- [ ] **Step 3: Verify import**

Run: `.venv/bin/python -c "from rapidfuzz import fuzz; print(fuzz.token_set_ratio('Apple Inc', 'apple inc.'))"`
Expected: `100`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add rapidfuzz + pyyaml for entity-alias resolver"
```

---

## Phase A: Database schema

### Task A1: Add `entity_aliases` table

**Files:**
- Modify: `src/utils/db.py` (extend the `init_db()` SQL block)
- Test: `tests/test_entity_aliases_schema.py`

- [ ] **Step 1: Write the failing schema test**

Create `tests/test_entity_aliases_schema.py`:

```python
"""Schema test for entity_aliases table (Wave 1 foundation)."""
from __future__ import annotations

from src.utils.db import get_connection, init_db


def test_entity_aliases_table_exists():
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='entity_aliases'"
    ).fetchone()
    conn.close()
    assert row is not None, "entity_aliases table missing"


def test_entity_aliases_required_columns():
    init_db()
    conn = get_connection()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(entity_aliases)").fetchall()}
    conn.close()
    expected = {
        "ticker", "cik", "uei", "alias_type", "alias_name",
        "alias_source", "confidence", "created_at",
    }
    assert expected.issubset(cols), f"missing columns: {expected - cols}"


def test_entity_aliases_indices():
    init_db()
    conn = get_connection()
    idxs = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='entity_aliases'"
    ).fetchall()}
    conn.close()
    assert "idx_entity_aliases_name" in idxs
    assert "idx_entity_aliases_cik" in idxs
    assert "idx_entity_aliases_uei" in idxs


def test_entity_aliases_check_constraint_on_alias_type():
    init_db()
    conn = get_connection()
    import sqlite3
    with conn:
        try:
            conn.execute(
                "INSERT INTO entity_aliases (ticker, alias_type, alias_name, alias_source, confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("AAPL", "bogus_type", "apple inc", "manual", 1.0, "2026-05-15T00:00:00Z"),
            )
            assert False, "expected CHECK constraint to reject 'bogus_type'"
        except sqlite3.IntegrityError:
            pass
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_entity_aliases_schema.py -v`
Expected: 4 tests FAIL with messages about the missing table.

- [ ] **Step 3: Add the table to `init_db()`**

In `src/utils/db.py`, locate the `init_db()` function. Inside the `conn.executescript(""" ... """)` block, immediately after the existing `CREATE TABLE IF NOT EXISTS ai_decision_outcomes (...)` block and its index, append:

```sql

        -- ── Sector-influence Wave 1: entity alias table ───────────────────
        CREATE TABLE IF NOT EXISTS entity_aliases (
            ticker          TEXT NOT NULL,
            cik             TEXT,
            uei             TEXT,
            alias_type      TEXT NOT NULL CHECK (alias_type IN (
                                'legal', 'common', 'subsidiary',
                                'uspto_canonical', 'sam_business_name',
                                'brand', 'override'
                            )),
            alias_name      TEXT NOT NULL,
            alias_source    TEXT NOT NULL,
            confidence      REAL NOT NULL,
            created_at      TEXT NOT NULL,
            PRIMARY KEY (ticker, alias_type, alias_name)
        );
        CREATE INDEX IF NOT EXISTS idx_entity_aliases_name ON entity_aliases(alias_name);
        CREATE INDEX IF NOT EXISTS idx_entity_aliases_cik ON entity_aliases(cik);
        CREATE INDEX IF NOT EXISTS idx_entity_aliases_uei ON entity_aliases(uei);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_entity_aliases_schema.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/utils/db.py tests/test_entity_aliases_schema.py
git commit -m "feat(db): add entity_aliases table for sector-influence Wave 1"
```

---

### Task A2: Add `source_freshness` table

**Files:**
- Modify: `src/utils/db.py`
- Test: `tests/test_source_freshness_schema.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_source_freshness_schema.py`:

```python
from __future__ import annotations

from src.utils.db import get_connection, init_db


def test_source_freshness_table_exists():
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='source_freshness'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_source_freshness_columns():
    init_db()
    conn = get_connection()
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(source_freshness)"
    ).fetchall()}
    conn.close()
    expected = {
        "source", "cadence", "ttl_seconds", "last_fetched_at",
        "next_due_at", "last_status", "last_error", "last_payload_count",
        "rate_limit_budget", "rate_limit_remaining",
    }
    assert expected.issubset(cols), f"missing columns: {expected - cols}"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_source_freshness_schema.py -v`
Expected: FAIL.

- [ ] **Step 3: Add the table to `init_db()`**

Append inside the `init_db()` SQL block (after the `entity_aliases` block):

```sql

        -- ── Sector-influence Wave 1: per-source freshness registry ───────
        CREATE TABLE IF NOT EXISTS source_freshness (
            source                  TEXT PRIMARY KEY,
            cadence                 TEXT NOT NULL,      -- 'hourly' | 'daily' | 'weekly' | 'monthly' | 'quarterly'
            ttl_seconds             INTEGER NOT NULL,
            last_fetched_at         TEXT,
            next_due_at             TEXT,
            last_status             TEXT,               -- 'ok' | 'error' | 'rate_limited' | 'empty'
            last_error              TEXT,
            last_payload_count      INTEGER,
            rate_limit_budget       INTEGER,
            rate_limit_remaining    INTEGER
        );
```

- [ ] **Step 4: Verify the test passes**

Run: `.venv/bin/pytest tests/test_source_freshness_schema.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/utils/db.py tests/test_source_freshness_schema.py
git commit -m "feat(db): add source_freshness registry for sector-influence Wave 1"
```

---

### Task A3: Add `known_future_events` table

**Files:**
- Modify: `src/utils/db.py`
- Test: `tests/test_known_future_events_schema.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_known_future_events_schema.py`:

```python
from __future__ import annotations

from src.utils.db import get_connection, init_db


def test_known_future_events_table_exists():
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='known_future_events'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_known_future_events_columns():
    init_db()
    conn = get_connection()
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(known_future_events)"
    ).fetchall()}
    conn.close()
    expected = {
        "event_id", "ticker", "event_type", "event_date",
        "source", "source_url", "details_json", "added_at",
    }
    assert expected.issubset(cols)


def test_known_future_events_indices():
    init_db()
    conn = get_connection()
    idxs = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='known_future_events'"
    ).fetchall()}
    conn.close()
    assert "idx_known_future_events_date" in idxs
    assert "idx_known_future_events_ticker" in idxs
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_known_future_events_schema.py -v`
Expected: FAIL.

- [ ] **Step 3: Add the table to `init_db()`**

Append inside the `init_db()` SQL block (after the `source_freshness` block):

```sql

        -- ── Sector-influence Wave 1: forward-looking catalysts ───────────
        CREATE TABLE IF NOT EXISTS known_future_events (
            event_id        TEXT PRIMARY KEY,
            ticker          TEXT,
            event_type      TEXT NOT NULL,
            event_date      TEXT NOT NULL,
            source          TEXT NOT NULL,
            source_url      TEXT,
            details_json    TEXT,
            added_at        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_known_future_events_date ON known_future_events(event_date);
        CREATE INDEX IF NOT EXISTS idx_known_future_events_ticker ON known_future_events(ticker);
```

- [ ] **Step 4: Verify the test passes**

Run: `.venv/bin/pytest tests/test_known_future_events_schema.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/utils/db.py tests/test_known_future_events_schema.py
git commit -m "feat(db): add known_future_events table for forward catalysts"
```

---

## Phase B: Shared dataclasses

### Task B1: Create `sector_signals/_shared.py` with `Fact`, `StockInformation`, `SignalReading`

**Files:**
- Create: `src/analysis/sector_signals/__init__.py`
- Create: `src/analysis/sector_signals/_shared.py`
- Test: `tests/test_sector_signals_shared.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_sector_signals_shared.py`:

```python
"""Tests for sector-influence shared dataclasses (Wave 1)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.analysis.sector_signals._shared import (
    Fact,
    SignalReading,
    StockInformation,
)


def test_fact_is_frozen():
    f = Fact(
        text="filed 1247 patents in last 12mo",
        as_of="2026-05-15T00:00:00Z",
        source="uspto",
        source_url="https://patentsview.org/...",
        confidence=1.0,
    )
    with pytest.raises(Exception):
        f.text = "changed"


def test_stock_information_required_fields():
    si = StockInformation(
        ticker="AAPL",
        topic="innovation",
        headline="R&D weighted toward on-device AI",
        facts=[],
        narrative=None,
        implications=["heavy R&D in AI"],
        related_catalysts=[],
        confidence="high",
        as_of="2026-05-15T00:00:00Z",
        sources_used=["uspto"],
        severity="low",
    )
    assert si.ticker == "AAPL"
    assert si.topic == "innovation"
    assert si.severity == "low"


def test_stock_information_severity_must_be_valid():
    with pytest.raises(ValueError):
        StockInformation(
            ticker="AAPL",
            topic="innovation",
            headline="x",
            facts=[],
            narrative=None,
            implications=[],
            related_catalysts=[],
            confidence="high",
            as_of="2026-05-15T00:00:00Z",
            sources_used=[],
            severity="extreme",  # not allowed
        )


def test_signal_reading_uses_decimal_for_value():
    sr = SignalReading(
        ticker="LMT",
        sector=None,
        signal_name="gov_contract_award",
        value=Decimal("4200000000"),
        z_score=Decimal("1.5"),
        direction="bullish",
        confidence="high",
        as_of="2026-05-14T00:00:00Z",
        available_at="2026-05-17T00:00:00Z",
        point_in_time_lag_days=3,
        source="usaspending",
    )
    assert isinstance(sr.value, Decimal)
    assert sr.available_at >= sr.as_of


def test_signal_reading_rejects_float_value():
    with pytest.raises(TypeError):
        SignalReading(
            ticker="X",
            sector=None,
            signal_name="test",
            value=4.2,  # float not allowed for monetary/numeric value
            z_score=None,
            direction="neutral",
            confidence="low",
            as_of="2026-05-15T00:00:00Z",
            available_at="2026-05-15T00:00:00Z",
            point_in_time_lag_days=0,
            source="test",
        )


def test_signal_reading_available_at_must_be_ge_as_of():
    with pytest.raises(ValueError):
        SignalReading(
            ticker="X",
            sector=None,
            signal_name="test",
            value=Decimal("1"),
            z_score=None,
            direction="neutral",
            confidence="low",
            as_of="2026-05-15T00:00:00Z",
            available_at="2026-05-14T00:00:00Z",  # before as_of → lookahead!
            point_in_time_lag_days=0,
            source="test",
        )


def test_signal_reading_either_ticker_or_sector_required():
    with pytest.raises(ValueError):
        SignalReading(
            ticker=None,
            sector=None,
            signal_name="test",
            value=Decimal("1"),
            z_score=None,
            direction="neutral",
            confidence="low",
            as_of="2026-05-15T00:00:00Z",
            available_at="2026-05-15T00:00:00Z",
            point_in_time_lag_days=0,
            source="test",
        )
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_sector_signals_shared.py -v`
Expected: ImportError (module doesn't exist).

- [ ] **Step 3: Create the package marker**

Create `src/analysis/sector_signals/__init__.py` with empty content (zero bytes is fine, but write one line to keep editors happy):

```python
"""Sector-influence signals & information (Wave 1 foundation + later waves)."""
```

- [ ] **Step 4: Create the dataclasses module**

Create `src/analysis/sector_signals/_shared.py`:

```python
"""Shared dataclasses for sector-influence signals and information.

Two output shapes:
  - `StockInformation` — human-facing context. Used by all 15 sources.
  - `SignalReading`    — quant-facing numeric reading. Used ONLY by the
                         7 scored signals (FDA, gov contracts, ITC,
                         exec turnover, container rates, EIA, building
                         permits). Information sources MUST NOT emit
                         SignalReading.

Both carry as_of (when the underlying event is valid). SignalReading
additionally carries available_at (when a backtest can FIRST see it).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

Direction = Literal["bullish", "bearish", "neutral"]
Confidence = Literal["high", "med", "low"]
Severity = Literal["high", "med", "low"]


@dataclass(frozen=True)
class Fact:
    """A single dated fact backing a StockInformation entry."""
    text: str
    as_of: str                  # ISO 8601 UTC
    source: str                 # 'uspto' | 'openfda' | 'usaspending' | ...
    source_url: str | None
    confidence: float           # 0.0–1.0; 1.0 = authoritative ID match


@dataclass(frozen=True)
class StockInformation:
    """Display-only information about a stock, for cards and narratives.

    Emitted by all 15 sector-influence sources. NEVER used to score the
    Bubble Score or feed a backtest — use SignalReading for those.
    """
    ticker: str
    topic: str
    headline: str
    facts: list[Fact]
    narrative: str | None       # Claude-generated; None until generated
    implications: list[str]
    related_catalysts: list[str]
    confidence: Confidence
    as_of: str
    sources_used: list[str]
    severity: Severity          # used by Risk-narrative top-3 prioritization

    def __post_init__(self) -> None:
        if self.confidence not in ("high", "med", "low"):
            raise ValueError(f"invalid confidence: {self.confidence!r}")
        if self.severity not in ("high", "med", "low"):
            raise ValueError(f"invalid severity: {self.severity!r}")


@dataclass(frozen=True)
class SignalReading:
    """Quant-facing numeric reading for the 7 scored signals.

    Strict point-in-time discipline: backtester filters on `available_at`,
    never on `as_of`. Use Decimal for the value field — never float.
    """
    ticker: str | None
    sector: str | None
    signal_name: str
    value: Decimal
    z_score: Decimal | None
    direction: Direction
    confidence: Confidence
    as_of: str
    available_at: str
    point_in_time_lag_days: int
    source: str

    def __post_init__(self) -> None:
        if self.ticker is None and self.sector is None:
            raise ValueError("SignalReading requires ticker or sector")
        if not isinstance(self.value, Decimal):
            raise TypeError(
                f"SignalReading.value must be Decimal, got {type(self.value).__name__}"
            )
        if self.z_score is not None and not isinstance(self.z_score, Decimal):
            raise TypeError("SignalReading.z_score must be Decimal or None")
        if self.direction not in ("bullish", "bearish", "neutral"):
            raise ValueError(f"invalid direction: {self.direction!r}")
        if self.confidence not in ("high", "med", "low"):
            raise ValueError(f"invalid confidence: {self.confidence!r}")
        if self.available_at < self.as_of:
            raise ValueError(
                f"available_at ({self.available_at}) cannot be before as_of ({self.as_of})"
            )
        if self.point_in_time_lag_days < 0:
            raise ValueError("point_in_time_lag_days must be ≥ 0")
```

- [ ] **Step 5: Run the test**

Run: `.venv/bin/pytest tests/test_sector_signals_shared.py -v`
Expected: 7 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/analysis/sector_signals/__init__.py src/analysis/sector_signals/_shared.py tests/test_sector_signals_shared.py
git commit -m "feat(analysis): add StockInformation + SignalReading dataclasses"
```

---

## Phase C: Normalization + entity resolver

### Task C1: Name normalization helper

**Files:**
- Create: `src/data/entity_aliases.py`
- Test: `tests/test_entity_aliases_normalize.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_entity_aliases_normalize.py`:

```python
"""Tests for entity-alias name normalization (Wave 1)."""
from __future__ import annotations

import pytest

from src.data.entity_aliases import normalize_name


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Apple Inc.", "apple"),
        ("APPLE INC", "apple"),
        ("Apple, Inc.", "apple"),
        ("Microsoft Corporation", "microsoft"),
        ("Berkshire Hathaway Inc.", "berkshire hathaway"),
        ("JPMorgan Chase & Co.", "jpmorgan chase"),
        ("Alphabet Inc. Class A", "alphabet class a"),
        ("Tesla, Inc.", "tesla"),
        ("Lockheed Martin Corp", "lockheed martin"),
        ("Beats Electronics, LLC", "beats electronics"),
        ("3M Company", "3m"),
        ("AT&T Inc.", "at&t"),
        ("  whitespace  test  ", "whitespace test"),
    ],
)
def test_normalize_strips_suffixes_and_lowercases(raw: str, expected: str):
    assert normalize_name(raw) == expected


def test_normalize_handles_empty_string():
    assert normalize_name("") == ""


def test_normalize_handles_only_suffix():
    # Edge case: a string that's only suffix words. Don't blow up.
    assert normalize_name("Inc.") == ""


def test_normalize_is_idempotent():
    assert normalize_name(normalize_name("Apple Inc.")) == "apple"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_entity_aliases_normalize.py -v`
Expected: ImportError.

- [ ] **Step 3: Create the module with normalize_name**

Create `src/data/entity_aliases.py`:

```python
"""Entity alias resolution: ticker ↔ company-name mapping.

Single source of truth for the `entity_aliases` table. Two thresholds:
  - Scored signals require ≥0.9 fuzzy confidence (or authoritative ID)
  - Information sources accept ≥0.8 fuzzy confidence

Authoritative ID matches (CIK, UEI) ALWAYS return confidence=1.0 and
bypass fuzzy matching.

Per CLAUDE.md: this module belongs to the `data/` layer. It may call
external APIs (during seeding) and read/write `trading.db`. It must
NOT import from `src/analysis/` or `src/reports/`.
"""
from __future__ import annotations

import re

# Words stripped during normalization (lowercased, after punctuation removal).
# Order matters: longer phrases first to avoid leaving "holdings" when
# we meant to strip "holdings inc".
_SUFFIX_WORDS = (
    "incorporated", "corporation", "company", "limited",
    "holdings", "group", "trust",
    "inc", "corp", "co", "ltd", "llc", "lp", "plc", "nv", "sa", "ag",
)
_SUFFIX_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _SUFFIX_WORDS) + r")\b",
    flags=re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[.,/]")


def normalize_name(raw: str) -> str:
    """Normalize a company name for matching.

    Steps: lowercase → drop period/comma/slash → strip corporate
    suffixes (Inc, Corp, LLC, ...) → collapse whitespace.

    Idempotent. Returns "" for empty input.
    """
    if not raw:
        return ""
    s = raw.lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _SUFFIX_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_entity_aliases_normalize.py -v`
Expected: 16 PASSED (13 parametrized + 3 individual).

- [ ] **Step 5: Commit**

```bash
git add src/data/entity_aliases.py tests/test_entity_aliases_normalize.py
git commit -m "feat(data): add normalize_name for entity-alias matching"
```

---

### Task C2: ResolvedEntity + exact-match resolver

**Files:**
- Modify: `src/data/entity_aliases.py`
- Test: `tests/test_entity_aliases_resolve.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_entity_aliases_resolve.py`:

```python
"""Tests for entity-alias ticker resolution (Wave 1)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data.entity_aliases import (
    ResolvedEntity,
    insert_alias,
    resolve_by_cik,
    resolve_by_uei,
    resolve_ticker,
)
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean_aliases():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source IN ('test_fixture')")
    conn.commit()
    conn.close()
    yield
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source IN ('test_fixture')")
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def test_resolve_by_cik_returns_authoritative_match():
    insert_alias(
        ticker="AAPL", cik="0000320193", uei=None,
        alias_type="legal", alias_name="apple",
        alias_source="test_fixture", confidence=1.0, created_at=_now(),
    )
    r = resolve_by_cik("0000320193")
    assert r == ResolvedEntity(ticker="AAPL", matched_alias="apple", confidence=1.0, alias_type="legal")


def test_resolve_by_cik_returns_none_for_unknown():
    assert resolve_by_cik("9999999999") is None


def test_resolve_by_uei_returns_authoritative_match():
    insert_alias(
        ticker="LMT", cik=None, uei="ABC123DEF456",
        alias_type="sam_business_name", alias_name="lockheed martin",
        alias_source="test_fixture", confidence=1.0, created_at=_now(),
    )
    r = resolve_by_uei("ABC123DEF456")
    assert r is not None and r.ticker == "LMT"
    assert r.confidence == 1.0


def test_resolve_ticker_exact_match_after_normalize():
    insert_alias(
        ticker="MSFT", cik=None, uei=None,
        alias_type="legal", alias_name="microsoft",
        alias_source="test_fixture", confidence=1.0, created_at=_now(),
    )
    r = resolve_ticker("Microsoft Corporation")
    assert r is not None and r.ticker == "MSFT"
    assert r.confidence == 1.0
    assert r.matched_alias == "microsoft"


def test_resolve_ticker_returns_none_for_empty_input():
    assert resolve_ticker("") is None
    assert resolve_ticker("   ") is None


def test_resolve_ticker_returns_none_when_no_match():
    r = resolve_ticker("Nonexistent Hypothetical Co")
    assert r is None
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_entity_aliases_resolve.py -v`
Expected: FAIL (ImportError on resolve_by_cik / insert_alias / etc).

- [ ] **Step 3: Extend `src/data/entity_aliases.py` with the resolver**

Append to `src/data/entity_aliases.py`:

```python


from dataclasses import dataclass

from src.utils.db import get_connection, init_db


@dataclass(frozen=True)
class ResolvedEntity:
    ticker: str
    matched_alias: str
    confidence: float
    alias_type: str


def insert_alias(
    *,
    ticker: str,
    cik: str | None,
    uei: str | None,
    alias_type: str,
    alias_name: str,
    alias_source: str,
    confidence: float,
    created_at: str,
) -> None:
    """Insert (or replace) one alias row. Normalizes alias_name on insert."""
    init_db()
    conn = get_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO entity_aliases
          (ticker, cik, uei, alias_type, alias_name, alias_source, confidence, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker.upper(),
            cik,
            uei,
            alias_type,
            normalize_name(alias_name),
            alias_source,
            float(confidence),
            created_at,
        ),
    )
    conn.commit()
    conn.close()


def resolve_by_cik(cik: str) -> ResolvedEntity | None:
    """Authoritative ID lookup. confidence=1.0 always."""
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT ticker, alias_name, alias_type FROM entity_aliases WHERE cik = ? LIMIT 1",
        (cik,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return ResolvedEntity(
        ticker=row["ticker"],
        matched_alias=row["alias_name"],
        confidence=1.0,
        alias_type=row["alias_type"],
    )


def resolve_by_uei(uei: str) -> ResolvedEntity | None:
    """Authoritative ID lookup. confidence=1.0 always."""
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT ticker, alias_name, alias_type FROM entity_aliases WHERE uei = ? LIMIT 1",
        (uei,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return ResolvedEntity(
        ticker=row["ticker"],
        matched_alias=row["alias_name"],
        confidence=1.0,
        alias_type=row["alias_type"],
    )


def resolve_ticker(
    name: str,
    *,
    min_confidence: float = 0.9,
    use_fuzzy: bool = False,
) -> ResolvedEntity | None:
    """Resolve a free-text company name to a ticker.

    Lookup order:
      1. Exact match on normalized alias_name (confidence=1.0)
      2. Fuzzy match — but ONLY when use_fuzzy=True (see Task C3)

    Returns None when no match passes `min_confidence`.
    """
    if not name or not name.strip():
        return None
    normalized = normalize_name(name)
    if not normalized:
        return None

    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT ticker, alias_name, alias_type FROM entity_aliases WHERE alias_name = ? LIMIT 1",
        (normalized,),
    ).fetchone()
    conn.close()
    if row is not None:
        return ResolvedEntity(
            ticker=row["ticker"],
            matched_alias=row["alias_name"],
            confidence=1.0,
            alias_type=row["alias_type"],
        )

    # Fuzzy path is implemented in Task C3.
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_entity_aliases_resolve.py -v`
Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/data/entity_aliases.py tests/test_entity_aliases_resolve.py
git commit -m "feat(data): add ResolvedEntity + exact-match resolver"
```

---

### Task C3: Fuzzy match with thresholds

**Files:**
- Modify: `src/data/entity_aliases.py`
- Test: `tests/test_entity_aliases_fuzzy.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_entity_aliases_fuzzy.py`:

```python
"""Tests for fuzzy entity-alias matching (Wave 1)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data.entity_aliases import insert_alias, resolve_ticker
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source IN ('test_fixture')")
    conn.commit()
    conn.close()
    yield
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source IN ('test_fixture')")
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _seed(ticker: str, alias: str):
    insert_alias(
        ticker=ticker, cik=None, uei=None,
        alias_type="legal", alias_name=alias,
        alias_source="test_fixture", confidence=1.0, created_at=_now(),
    )


def test_fuzzy_off_does_not_match_typo():
    _seed("AAPL", "apple")
    assert resolve_ticker("Aple Inc.", use_fuzzy=False) is None


def test_fuzzy_on_matches_close_typo_at_high_threshold():
    _seed("MSFT", "microsoft")
    r = resolve_ticker("Microsft Corporation", use_fuzzy=True, min_confidence=0.9)
    assert r is not None and r.ticker == "MSFT"
    assert 0.9 <= r.confidence <= 1.0


def test_fuzzy_rejects_low_confidence_match_at_scored_threshold():
    """Scored signals require ≥0.9 — junk strings should not pass."""
    _seed("AAPL", "apple")
    r = resolve_ticker("zebra giraffe ostrich", use_fuzzy=True, min_confidence=0.9)
    assert r is None


def test_fuzzy_information_threshold_is_looser():
    """Information sources accept ≥0.8 — slightly noisier matches OK."""
    _seed("LMT", "lockheed martin")
    r = resolve_ticker("Lockheed-Martin Co", use_fuzzy=True, min_confidence=0.8)
    assert r is not None and r.ticker == "LMT"


def test_fuzzy_match_returns_actual_confidence_score():
    _seed("AAPL", "apple")
    r = resolve_ticker("aple", use_fuzzy=True, min_confidence=0.8)
    if r is not None:
        # Confidence is the rapidfuzz score / 100, in (0, 1).
        assert 0.0 < r.confidence < 1.0


def test_ambiguous_match_picks_highest_score():
    """If two aliases tie or near-tie, we must return one deterministically.
    Highest token_set_ratio wins; ties broken by ticker alpha order."""
    _seed("AAPL", "apple")
    _seed("APLE", "apple hospitality reit")
    r = resolve_ticker("Apple", use_fuzzy=True, min_confidence=0.8)
    # Exact match on 'apple' must win over partial on 'apple hospitality reit'
    assert r is not None and r.ticker == "AAPL"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_entity_aliases_fuzzy.py -v`
Expected: FAIL — fuzzy path returns None (per Task C2's stub).

- [ ] **Step 3: Implement the fuzzy path**

In `src/data/entity_aliases.py`, replace the existing `resolve_ticker()` body (specifically the `# Fuzzy path is implemented in Task C3.` block and everything after the exact-match return) so the full function becomes:

```python
def resolve_ticker(
    name: str,
    *,
    min_confidence: float = 0.9,
    use_fuzzy: bool = False,
) -> ResolvedEntity | None:
    """Resolve a free-text company name to a ticker.

    Lookup order:
      1. Exact match on normalized alias_name (confidence=1.0)
      2. Fuzzy match via rapidfuzz.token_set_ratio when use_fuzzy=True

    Returns None when no match passes `min_confidence`.

    Threshold convention:
      - Scored signals: min_confidence=0.9 (default)
      - Information sources: min_confidence=0.8
    """
    if not name or not name.strip():
        return None
    normalized = normalize_name(name)
    if not normalized:
        return None

    init_db()
    conn = get_connection()
    try:
        # 1. Exact match (confidence=1.0)
        row = conn.execute(
            "SELECT ticker, alias_name, alias_type FROM entity_aliases WHERE alias_name = ? LIMIT 1",
            (normalized,),
        ).fetchone()
        if row is not None:
            return ResolvedEntity(
                ticker=row["ticker"],
                matched_alias=row["alias_name"],
                confidence=1.0,
                alias_type=row["alias_type"],
            )

        if not use_fuzzy:
            return None

        # 2. Fuzzy match: score the candidate against EVERY alias
        from rapidfuzz import fuzz

        candidates = conn.execute(
            "SELECT ticker, alias_name, alias_type FROM entity_aliases"
        ).fetchall()
        if not candidates:
            return None

        best: tuple[float, str, str, str] | None = None  # (score, ticker, alias, alias_type)
        for c in candidates:
            score = fuzz.token_set_ratio(normalized, c["alias_name"]) / 100.0
            if score < min_confidence:
                continue
            # Highest score wins; ties broken by alpha ticker order
            if best is None or score > best[0] or (score == best[0] and c["ticker"] < best[1]):
                best = (score, c["ticker"], c["alias_name"], c["alias_type"])

        if best is None:
            return None
        return ResolvedEntity(
            ticker=best[1],
            matched_alias=best[2],
            confidence=best[0],
            alias_type=best[3],
        )
    finally:
        conn.close()
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_entity_aliases_fuzzy.py -v`
Expected: 6 PASSED.

- [ ] **Step 5: Also run the prior resolver tests to confirm no regression**

Run: `.venv/bin/pytest tests/test_entity_aliases_resolve.py tests/test_entity_aliases_normalize.py -v`
Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/data/entity_aliases.py tests/test_entity_aliases_fuzzy.py
git commit -m "feat(data): add fuzzy entity-alias matching with threshold gating"
```

---

## Phase D: Seeders

### Task D1: Manual override YAML loader

**Files:**
- Create: `src/data/entity_overrides.yaml`
- Modify: `src/data/entity_aliases.py`
- Test: `tests/test_entity_aliases_overrides.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_entity_aliases_overrides.py`:

```python
"""Tests for manual entity-override YAML loader (Wave 1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.data.entity_aliases import resolve_ticker, seed_from_overrides
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'override'")
    conn.commit()
    conn.close()
    yield


def test_seed_from_overrides_loads_yaml(tmp_path: Path):
    yaml_text = """
overrides:
  - ticker: BRK.B
    aliases:
      - "Berkshire Hathaway Inc Class B"
      - "berkshire b"
  - ticker: GOOGL
    cik: "0001652044"
    aliases:
      - "Alphabet Inc Class A"
  - ticker: AAPL
    subsidiaries:
      - "Beats Electronics LLC"
      - "Apple Operations International"
"""
    p = tmp_path / "overrides.yaml"
    p.write_text(yaml_text)

    inserted = seed_from_overrides(yaml_path=p)
    assert inserted == 5  # 2 BRK + 1 GOOGL alias + 2 AAPL subs

    # alias lookup works (exact)
    r = resolve_ticker("Berkshire Hathaway Inc Class B")
    assert r is not None and r.ticker == "BRK.B"

    # subsidiary rollup
    r = resolve_ticker("Beats Electronics LLC")
    assert r is not None and r.ticker == "AAPL"
    assert r.alias_type == "subsidiary"


def test_seed_from_overrides_missing_file_returns_zero(tmp_path: Path):
    missing = tmp_path / "does_not_exist.yaml"
    assert seed_from_overrides(yaml_path=missing) == 0


def test_seed_from_overrides_default_path_works():
    """Default path points to src/data/entity_overrides.yaml (the real file)."""
    # Should not raise even if file empty/minimal.
    n = seed_from_overrides()
    assert n >= 0
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_entity_aliases_overrides.py -v`
Expected: FAIL (`seed_from_overrides` doesn't exist).

- [ ] **Step 3: Create the default overrides file**

Create `src/data/entity_overrides.yaml`:

```yaml
# Entity-alias manual overrides.
# Used by src/data/entity_aliases.py::seed_from_overrides().
#
# Each override maps a ticker to a list of aliases that fuzzy matching
# may miss (dual-class shares, well-known subsidiaries, common nicknames).
#
# Schema:
#   overrides:
#     - ticker: STR (uppercase)
#       cik: STR (optional, 10-digit zero-padded)
#       uei: STR (optional, 12-char SAM.gov UEI)
#       aliases: [STR, ...]         # alias_type='override'
#       subsidiaries: [STR, ...]    # alias_type='subsidiary'
#       brands: [STR, ...]          # alias_type='brand'

overrides:
  # Dual-class share structures
  - ticker: BRK.B
    aliases:
      - "Berkshire Hathaway Class B"
      - "Berkshire B"
  - ticker: BRK.A
    aliases:
      - "Berkshire Hathaway Class A"
      - "Berkshire A"
  - ticker: GOOGL
    aliases:
      - "Alphabet Class A"
      - "Google Class A"
  - ticker: GOOG
    aliases:
      - "Alphabet Class C"
      - "Google Class C"

  # Well-known subsidiaries (seeded explicitly; 10-K Exhibit 21 will add more)
  - ticker: AAPL
    subsidiaries:
      - "Beats Electronics LLC"
      - "Apple Operations International"
  - ticker: GOOGL
    subsidiaries:
      - "YouTube LLC"
      - "DeepMind Technologies Limited"
      - "Waymo LLC"
  - ticker: META
    subsidiaries:
      - "Instagram LLC"
      - "WhatsApp LLC"
      - "Oculus VR LLC"

  # Brand-name aliases (consumer-facing names that differ from ticker)
  - ticker: MO
    brands:
      - "Philip Morris USA"
      - "Marlboro"
  - ticker: PG
    brands:
      - "Procter and Gamble"
```

- [ ] **Step 4: Add `seed_from_overrides` to `src/data/entity_aliases.py`**

Append to `src/data/entity_aliases.py`:

```python


# ── Seeders ──────────────────────────────────────────────────────────

from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_OVERRIDES_PATH = Path(__file__).resolve().parent / "entity_overrides.yaml"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def seed_from_overrides(yaml_path: Path | None = None) -> int:
    """Load manual overrides from YAML and insert into entity_aliases.

    Returns the count of inserted alias rows. Missing file → 0 (silent).
    """
    import yaml

    path = yaml_path if yaml_path is not None else _DEFAULT_OVERRIDES_PATH
    if not path.exists():
        return 0

    with path.open("r") as f:
        data = yaml.safe_load(f) or {}

    overrides = data.get("overrides", []) or []
    now = _now_iso()
    inserted = 0

    for entry in overrides:
        ticker = entry.get("ticker")
        if not ticker:
            continue
        cik = entry.get("cik")
        uei = entry.get("uei")

        for alias in entry.get("aliases", []) or []:
            insert_alias(
                ticker=ticker, cik=cik, uei=uei,
                alias_type="override", alias_name=alias,
                alias_source="override", confidence=1.0, created_at=now,
            )
            inserted += 1
        for sub in entry.get("subsidiaries", []) or []:
            insert_alias(
                ticker=ticker, cik=None, uei=None,
                alias_type="subsidiary", alias_name=sub,
                alias_source="override", confidence=1.0, created_at=now,
            )
            inserted += 1
        for brand in entry.get("brands", []) or []:
            insert_alias(
                ticker=ticker, cik=None, uei=None,
                alias_type="brand", alias_name=brand,
                alias_source="override", confidence=1.0, created_at=now,
            )
            inserted += 1

    return inserted
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/pytest tests/test_entity_aliases_overrides.py -v`
Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/data/entity_overrides.yaml src/data/entity_aliases.py tests/test_entity_aliases_overrides.py
git commit -m "feat(data): add YAML manual-override seeder for entity aliases"
```

---

### Task D2: SEC EDGAR alias seeder (CIK + company name)

**Files:**
- Modify: `src/data/entity_aliases.py`
- Test: `tests/test_entity_aliases_sec_seeder.py`

- [ ] **Step 1: Inspect the existing CIK lookup pattern**

Run: `grep -n "_get_cik\|company_tickers\|ticker_to_cik" src/data/sec_edgar.py | head -10`
Expected output: shows the existing CIK lookup function.

The seeder will reuse this mapping rather than re-fetching from SEC.

- [ ] **Step 2: Write the failing test**

Create `tests/test_entity_aliases_sec_seeder.py`:

```python
"""Tests for the SEC EDGAR alias seeder (Wave 1)."""
from __future__ import annotations

import pytest

from src.data.entity_aliases import seed_from_sec_mapping
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'sec_test'")
    conn.commit()
    conn.close()
    yield


def test_seed_from_sec_mapping_inserts_cik_aliases():
    """Given a dict of {ticker: (cik, legal_name)}, the seeder inserts rows
    with alias_type='legal', confidence=1.0, and cik populated."""
    mapping = {
        "AAPL": ("0000320193", "Apple Inc."),
        "MSFT": ("0000789019", "Microsoft Corporation"),
    }
    n = seed_from_sec_mapping(mapping, alias_source="sec_test")
    assert n == 2

    conn = get_connection()
    rows = conn.execute(
        "SELECT ticker, cik, alias_name, alias_type, confidence FROM entity_aliases "
        "WHERE alias_source = 'sec_test' ORDER BY ticker"
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["cik"] == "0000320193"
    assert rows[0]["alias_name"] == "apple"   # normalized
    assert rows[0]["alias_type"] == "legal"
    assert rows[0]["confidence"] == 1.0


def test_seed_from_sec_mapping_handles_empty():
    assert seed_from_sec_mapping({}, alias_source="sec_test") == 0


def test_seed_from_sec_mapping_skips_blank_entries():
    mapping = {
        "AAPL": ("0000320193", "Apple Inc."),
        "": ("0000000000", "ignored"),       # blank ticker → skip
        "BAD": ("", "no cik"),               # blank cik → skip
    }
    n = seed_from_sec_mapping(mapping, alias_source="sec_test")
    assert n == 1
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/pytest tests/test_entity_aliases_sec_seeder.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `seed_from_sec_mapping`**

Append to `src/data/entity_aliases.py`:

```python


def seed_from_sec_mapping(
    mapping: dict[str, tuple[str, str]],
    *,
    alias_source: str = "sec",
) -> int:
    """Seed entity_aliases from a {ticker: (cik, legal_name)} mapping.

    Caller is responsible for producing the mapping — typically from
    SECEdgarProvider's existing CIK lookup (a one-time fetch of the
    SEC company_tickers.json file).

    Returns count of inserted rows. CIK is stored as the authoritative
    ID (confidence=1.0). Skips entries with blank ticker or blank CIK.
    """
    now = _now_iso()
    inserted = 0
    for ticker, (cik, legal_name) in mapping.items():
        if not ticker or not cik or not legal_name:
            continue
        insert_alias(
            ticker=ticker, cik=cik, uei=None,
            alias_type="legal", alias_name=legal_name,
            alias_source=alias_source, confidence=1.0, created_at=now,
        )
        inserted += 1
    return inserted


def load_sec_mapping_from_provider() -> dict[str, tuple[str, str]]:
    """Convenience: build the {ticker: (cik, name)} mapping from the
    existing SECEdgarProvider. Network call.

    Returns {} on failure (so seeders don't crash mid-pipeline).
    """
    try:
        import httpx
        # SEC publishes the full ticker→CIK list as a single JSON file.
        # This is the standard source SECEdgarProvider uses for CIK lookup.
        resp = httpx.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": "Trading-Research-App research@example.com"},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return {}

    mapping: dict[str, tuple[str, str]] = {}
    # company_tickers.json shape: {"0": {"cik_str": int, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    for entry in data.values():
        ticker = entry.get("ticker", "")
        cik_int = entry.get("cik_str")
        title = entry.get("title", "")
        if not ticker or cik_int is None or not title:
            continue
        cik_padded = str(cik_int).zfill(10)
        mapping[ticker.upper()] = (cik_padded, title)
    return mapping
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/pytest tests/test_entity_aliases_sec_seeder.py -v`
Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/data/entity_aliases.py tests/test_entity_aliases_sec_seeder.py
git commit -m "feat(data): add SEC EDGAR alias seeder"
```

---

### Task D3: 10-K Exhibit 21 subsidiary parser

**Files:**
- Modify: `src/data/sec_10k_extractor.py`
- Test: `tests/test_sec_10k_exhibit21.py`

- [ ] **Step 1: Inspect existing 10-K extractor structure**

Run: `grep -n "^def \|^class \|^    def " src/data/sec_10k_extractor.py | head -30`
Expected: shows public functions/classes of the existing extractor.

- [ ] **Step 2: Write the failing test**

Create `tests/test_sec_10k_exhibit21.py`:

```python
"""Tests for 10-K Exhibit 21 subsidiary parser (Wave 1)."""
from __future__ import annotations

from src.data.sec_10k_extractor import parse_exhibit_21_subsidiaries


SAMPLE_EXHIBIT_21 = """
Exhibit 21

List of Subsidiaries of the Registrant

Name                                     Jurisdiction of Incorporation
Apple Operations International           Ireland
Apple Operations Europe Limited          Ireland
Beats Electronics, LLC                   Delaware
Beddit Oy                                Finland
Braeburn Capital, Inc.                   Nevada
Filemaker, Inc.                          California
"""


SAMPLE_EXHIBIT_21_HTML = """
<HTML>
<BODY>
<H1>EXHIBIT 21</H1>
<P>SUBSIDIARIES OF THE REGISTRANT</P>
<TABLE>
<TR><TD>Subsidiary</TD><TD>State / Country</TD></TR>
<TR><TD>Lockheed Martin International, S.A.</TD><TD>Belgium</TD></TR>
<TR><TD>Sikorsky Aircraft Corporation</TD><TD>Delaware</TD></TR>
</TABLE>
</BODY>
</HTML>
"""


def test_parse_exhibit_21_plaintext_extracts_subsidiaries():
    subs = parse_exhibit_21_subsidiaries(SAMPLE_EXHIBIT_21)
    assert "Apple Operations International" in subs
    assert "Beats Electronics, LLC" in subs
    assert "Braeburn Capital, Inc." in subs
    # Header lines and the "List of Subsidiaries" preamble should NOT be subs
    assert "Name" not in subs
    assert "Jurisdiction of Incorporation" not in subs
    assert "List of Subsidiaries of the Registrant" not in subs


def test_parse_exhibit_21_html_extracts_subsidiaries():
    subs = parse_exhibit_21_subsidiaries(SAMPLE_EXHIBIT_21_HTML)
    assert "Lockheed Martin International, S.A." in subs
    assert "Sikorsky Aircraft Corporation" in subs


def test_parse_exhibit_21_empty_string_returns_empty_list():
    assert parse_exhibit_21_subsidiaries("") == []


def test_parse_exhibit_21_no_subs_section_returns_empty():
    junk = "This is just some text with no exhibit data."
    assert parse_exhibit_21_subsidiaries(junk) == []
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/pytest tests/test_sec_10k_exhibit21.py -v`
Expected: ImportError on `parse_exhibit_21_subsidiaries`.

- [ ] **Step 4: Add the parser to `src/data/sec_10k_extractor.py`**

Append at the end of `src/data/sec_10k_extractor.py`:

```python


# ── Exhibit 21 (Subsidiaries of the Registrant) ──────────────────────
# Used by sector-influence Wave 1 to seed parent→subsidiary aliases
# in `entity_aliases`. See Plan: 2026-05-15-sector-influence-wave-1.

import re

from bs4 import BeautifulSoup


_EXHIBIT_HEADER_RE = re.compile(
    r"(?:exhibit\s*21|list\s+of\s+subsidiaries|subsidiaries\s+of\s+the\s+registrant)",
    flags=re.IGNORECASE,
)

# Boilerplate strings that look like rows but aren't subsidiary names.
_NOISE_LINES = {
    "name", "subsidiary", "subsidiaries",
    "jurisdiction of incorporation", "state / country",
    "state of incorporation", "country of incorporation",
    "list of subsidiaries of the registrant",
    "subsidiaries of the registrant",
    "exhibit 21",
    "name jurisdiction of incorporation",
}


def _is_html(text: str) -> bool:
    return "<html" in text.lower() or "<body" in text.lower() or "<table" in text.lower()


def _extract_subsidiaries_from_html(text: str) -> list[str]:
    """Pull subsidiary names from HTML tables (TD cells, first column)."""
    soup = BeautifulSoup(text, "html.parser")
    names: list[str] = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            first = cells[0].get_text(strip=True)
            if not first:
                continue
            if first.lower() in _NOISE_LINES:
                continue
            # Heuristic: a subsidiary name should have at least one letter
            # and not be a pure header like "name" or "subsidiary".
            if re.search(r"[A-Za-z]", first):
                names.append(first)
    return names


def _extract_subsidiaries_from_text(text: str) -> list[str]:
    """Pull subsidiary names from plaintext Exhibit 21 (one per line)."""
    lines = text.splitlines()
    names: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.lower() in _NOISE_LINES:
            continue
        if _EXHIBIT_HEADER_RE.search(line):
            continue
        # Plaintext exhibit-21 layout is typically:
        #   <Subsidiary Name>          <Jurisdiction>
        # Many filings use multiple spaces or tabs as a column separator.
        # We take everything before the first run of 2+ spaces.
        parts = re.split(r"\s{2,}", line, maxsplit=1)
        candidate = parts[0].strip()
        if not candidate or candidate.lower() in _NOISE_LINES:
            continue
        # Require at least one alpha char to filter out "1" / "—" lines.
        if not re.search(r"[A-Za-z]", candidate):
            continue
        names.append(candidate)
    return names


def parse_exhibit_21_subsidiaries(text: str) -> list[str]:
    """Parse a 10-K Exhibit 21 (subsidiary list) into subsidiary names.

    Accepts plaintext or HTML. Returns a list of subsidiary names as
    they appear in the filing (NOT normalized — call normalize_name
    when inserting into entity_aliases).

    Returns [] when no recognizable Exhibit 21 content is found.
    """
    if not text:
        return []
    if not _EXHIBIT_HEADER_RE.search(text):
        return []

    if _is_html(text):
        names = _extract_subsidiaries_from_html(text)
    else:
        names = _extract_subsidiaries_from_text(text)

    # De-duplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        key = n.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/pytest tests/test_sec_10k_exhibit21.py -v`
Expected: 4 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/data/sec_10k_extractor.py tests/test_sec_10k_exhibit21.py
git commit -m "feat(data): parse 10-K Exhibit 21 for subsidiary list"
```

---

### Task D4: Subsidiary alias seeder (uses Task D3)

**Files:**
- Modify: `src/data/entity_aliases.py`
- Test: `tests/test_entity_aliases_subsidiary_seeder.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_entity_aliases_subsidiary_seeder.py`:

```python
"""Tests for parent→subsidiary alias seeding (Wave 1)."""
from __future__ import annotations

import pytest

from src.data.entity_aliases import resolve_ticker, seed_subsidiaries_from_text
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'exhibit21_test'")
    conn.commit()
    conn.close()
    yield


EXHIBIT_21 = """
Exhibit 21
List of Subsidiaries of the Registrant

Name                                     Jurisdiction
Beats Electronics, LLC                   Delaware
Apple Operations International           Ireland
"""


def test_seed_subsidiaries_inserts_rows_pointing_to_parent():
    n = seed_subsidiaries_from_text(
        parent_ticker="AAPL",
        exhibit_21_text=EXHIBIT_21,
        alias_source="exhibit21_test",
    )
    assert n == 2

    r = resolve_ticker("Beats Electronics LLC")
    assert r is not None and r.ticker == "AAPL"
    assert r.alias_type == "subsidiary"

    r2 = resolve_ticker("Apple Operations International")
    assert r2 is not None and r2.ticker == "AAPL"


def test_seed_subsidiaries_empty_text_returns_zero():
    n = seed_subsidiaries_from_text(
        parent_ticker="AAPL",
        exhibit_21_text="",
        alias_source="exhibit21_test",
    )
    assert n == 0


def test_seed_subsidiaries_requires_uppercase_ticker():
    # Lowercase ticker should be uppercased before insert.
    n = seed_subsidiaries_from_text(
        parent_ticker="aapl",
        exhibit_21_text=EXHIBIT_21,
        alias_source="exhibit21_test",
    )
    assert n == 2
    r = resolve_ticker("Beats Electronics LLC")
    assert r is not None and r.ticker == "AAPL"  # stored uppercase
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_entity_aliases_subsidiary_seeder.py -v`
Expected: ImportError on `seed_subsidiaries_from_text`.

- [ ] **Step 3: Add the seeder**

Append to `src/data/entity_aliases.py`:

```python


def seed_subsidiaries_from_text(
    *,
    parent_ticker: str,
    exhibit_21_text: str,
    alias_source: str = "exhibit21",
) -> int:
    """Parse Exhibit 21 text and insert subsidiary aliases pointing at the parent ticker.

    Uses src.data.sec_10k_extractor.parse_exhibit_21_subsidiaries to do
    the parsing — this seeder only handles DB insertion.

    Returns count of inserted alias rows.
    """
    from src.data.sec_10k_extractor import parse_exhibit_21_subsidiaries

    subs = parse_exhibit_21_subsidiaries(exhibit_21_text)
    if not subs:
        return 0

    now = _now_iso()
    inserted = 0
    for sub in subs:
        insert_alias(
            ticker=parent_ticker,    # insert_alias uppercases internally
            cik=None, uei=None,
            alias_type="subsidiary",
            alias_name=sub,
            alias_source=alias_source,
            confidence=1.0,
            created_at=now,
        )
        inserted += 1
    return inserted
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_entity_aliases_subsidiary_seeder.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/data/entity_aliases.py tests/test_entity_aliases_subsidiary_seeder.py
git commit -m "feat(data): seed parent->subsidiary aliases from Exhibit 21"
```

---

## Phase E: Point-in-time backtest validator

### Task E1: `assert_no_lookahead()` in `edge_validator.py`

**Files:**
- Modify: `src/analysis/edge_validator.py`
- Test: `tests/test_lookahead_assertion.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_lookahead_assertion.py`:

```python
"""Tests for the point-in-time lookahead assertion (Wave 1)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.analysis.edge_validator import LookaheadViolation, assert_no_lookahead
from src.analysis.sector_signals._shared import SignalReading


def _r(*, as_of: str, available_at: str) -> SignalReading:
    return SignalReading(
        ticker="X", sector=None, signal_name="test",
        value=Decimal("1"), z_score=None,
        direction="neutral", confidence="low",
        as_of=as_of, available_at=available_at,
        point_in_time_lag_days=0, source="test",
    )


def test_no_violation_when_all_available_at_le_decision():
    rs = [
        _r(as_of="2026-05-10T00:00:00Z", available_at="2026-05-10T00:00:00Z"),
        _r(as_of="2026-05-12T00:00:00Z", available_at="2026-05-13T00:00:00Z"),
    ]
    # Should not raise
    assert_no_lookahead(rs, decision_timestamp="2026-05-15T00:00:00Z")


def test_raises_when_a_reading_is_in_the_future():
    rs = [
        _r(as_of="2026-05-10T00:00:00Z", available_at="2026-05-10T00:00:00Z"),
        _r(as_of="2026-05-20T00:00:00Z", available_at="2026-05-20T00:00:00Z"),  # future!
    ]
    with pytest.raises(LookaheadViolation) as exc_info:
        assert_no_lookahead(rs, decision_timestamp="2026-05-15T00:00:00Z")
    msg = str(exc_info.value)
    assert "test" in msg                          # signal_name surfaced
    assert "2026-05-20" in msg                    # offending date surfaced


def test_raises_on_equal_only_when_strict():
    # By default, available_at == decision_timestamp is allowed (boundary).
    rs = [_r(as_of="2026-05-15T00:00:00Z", available_at="2026-05-15T00:00:00Z")]
    assert_no_lookahead(rs, decision_timestamp="2026-05-15T00:00:00Z")
    # When strict=True, equal is rejected.
    with pytest.raises(LookaheadViolation):
        assert_no_lookahead(rs, decision_timestamp="2026-05-15T00:00:00Z", strict=True)


def test_empty_list_is_a_noop():
    assert_no_lookahead([], decision_timestamp="2026-05-15T00:00:00Z")


def test_aggregates_multiple_violations_in_message():
    rs = [
        _r(as_of="2026-05-20T00:00:00Z", available_at="2026-05-21T00:00:00Z"),
        _r(as_of="2026-05-22T00:00:00Z", available_at="2026-05-23T00:00:00Z"),
    ]
    with pytest.raises(LookaheadViolation) as exc_info:
        assert_no_lookahead(rs, decision_timestamp="2026-05-15T00:00:00Z")
    msg = str(exc_info.value)
    assert "2 violation" in msg.lower() or "2 readings" in msg.lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_lookahead_assertion.py -v`
Expected: ImportError on `LookaheadViolation` / `assert_no_lookahead`.

- [ ] **Step 3: Add the assertion to `src/analysis/edge_validator.py`**

Append to the **top** of `src/analysis/edge_validator.py` (after the existing imports, before the `@dataclass` line for `ExposureValidation`):

```python


# ── Point-in-time backtest validator (Wave 1) ──────────────────────


class LookaheadViolation(Exception):
    """Raised when a SignalReading's available_at is after the decision timestamp."""


def assert_no_lookahead(
    readings: "list",
    *,
    decision_timestamp: str,
    strict: bool = False,
) -> None:
    """Raise LookaheadViolation if any reading is not available at decision time.

    Args:
      readings: list of SignalReading
      decision_timestamp: ISO 8601 UTC. A reading must have
                          available_at <= decision_timestamp (or < if strict).
      strict: when True, treat available_at == decision_timestamp as a violation.

    No-op on empty input. Aggregates all violations into a single
    exception message (do not stop at first).
    """
    if not readings:
        return

    violations = []
    for r in readings:
        available = r.available_at
        if strict:
            bad = available >= decision_timestamp
        else:
            bad = available > decision_timestamp
        if bad:
            violations.append(
                f"signal={r.signal_name} ticker={r.ticker} sector={r.sector} "
                f"available_at={available} > decision={decision_timestamp}"
            )

    if violations:
        n = len(violations)
        msg = f"{n} violation(s) found ({n} readings not yet available at decision time):\n  " + "\n  ".join(violations)
        raise LookaheadViolation(msg)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_lookahead_assertion.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Run the existing edge_validator tests to confirm no regression**

Run: `.venv/bin/pytest tests/test_edge_validator.py -v`
Expected: all PASSED (the existing edge_validator tests don't touch the new code path).

- [ ] **Step 6: Commit**

```bash
git add src/analysis/edge_validator.py tests/test_lookahead_assertion.py
git commit -m "feat(analysis): add assert_no_lookahead for point-in-time backtests"
```

---

### Task E2: Wire lookahead assertion into `backtester.py`

**Files:**
- Modify: `src/analysis/backtester.py`
- Test: `tests/test_backtester_lookahead_integration.py`

- [ ] **Step 1: Locate the decision-step entry point**

Run: `grep -n "^def \|^class " src/analysis/backtester.py | head -20`
Expected: lists the backtester's public functions. Identify the function that processes signals for a single decision timestamp (the per-step entry point).

- [ ] **Step 2: Write the failing integration test**

Create `tests/test_backtester_lookahead_integration.py`:

```python
"""Integration: backtester must reject SignalReading with future availability."""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.analysis.edge_validator import LookaheadViolation
from src.analysis.backtester import check_readings_point_in_time
from src.analysis.sector_signals._shared import SignalReading


def _r(as_of: str, available_at: str) -> SignalReading:
    return SignalReading(
        ticker="X", sector=None, signal_name="dummy",
        value=Decimal("1"), z_score=None, direction="neutral",
        confidence="low", as_of=as_of, available_at=available_at,
        point_in_time_lag_days=0, source="test",
    )


def test_check_readings_point_in_time_passes_when_ok():
    rs = [_r("2026-05-10", "2026-05-10"), _r("2026-05-12", "2026-05-13")]
    check_readings_point_in_time(rs, decision_timestamp="2026-05-15")


def test_check_readings_point_in_time_raises_on_lookahead():
    rs = [_r("2026-05-20", "2026-05-20")]
    with pytest.raises(LookaheadViolation):
        check_readings_point_in_time(rs, decision_timestamp="2026-05-15")
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/pytest tests/test_backtester_lookahead_integration.py -v`
Expected: ImportError on `check_readings_point_in_time`.

- [ ] **Step 4: Add the helper to `src/analysis/backtester.py`**

Open `src/analysis/backtester.py`. At the top of the file (after the existing imports), add:

```python
from src.analysis.edge_validator import LookaheadViolation, assert_no_lookahead
```

At the **bottom** of the file (after all existing functions), append:

```python


# ── Point-in-time gate for sector-influence SignalReading inputs ──
#
# Called by per-step backtest code that consumes the new SignalReading
# stream (Wave 2+). Fail-loud, not warn-soft: a lookahead bug must
# crash the backtest. See:
#   src/analysis/edge_validator.py::assert_no_lookahead
#   docs/superpowers/specs/2026-05-15-sector-influence-signals-design.md  §8


def check_readings_point_in_time(readings, *, decision_timestamp: str) -> None:
    """Thin wrapper used by backtest decision steps.

    Re-exports assert_no_lookahead in the backtester namespace so the
    backtest loop can `from src.analysis.backtester import check_readings_point_in_time`.
    """
    assert_no_lookahead(readings, decision_timestamp=decision_timestamp)
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/pytest tests/test_backtester_lookahead_integration.py -v`
Expected: 2 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/analysis/backtester.py tests/test_backtester_lookahead_integration.py
git commit -m "feat(backtester): wire point-in-time lookahead gate"
```

---

## Phase F: Per-source freshness registration

### Task F1: `source_freshness` register + query helpers

**Files:**
- Create: `src/data/source_freshness.py`
- Test: `tests/test_source_freshness.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_source_freshness.py`:

```python
"""Tests for per-source freshness registration (Wave 1)."""
from __future__ import annotations

import pytest

from src.data.source_freshness import (
    SourceFreshness,
    get_all_sources,
    get_source,
    record_fetch,
    register_source,
)
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM source_freshness WHERE source LIKE 'test_%'")
    conn.commit()
    conn.close()
    yield
    conn = get_connection()
    conn.execute("DELETE FROM source_freshness WHERE source LIKE 'test_%'")
    conn.commit()
    conn.close()


def test_register_source_inserts_row():
    register_source(
        source="test_uspto", cadence="weekly", ttl_seconds=7 * 86400,
        rate_limit_budget=None,
    )
    s = get_source("test_uspto")
    assert s is not None
    assert s.cadence == "weekly"
    assert s.ttl_seconds == 7 * 86400


def test_register_source_is_idempotent():
    register_source(source="test_a", cadence="daily", ttl_seconds=86400, rate_limit_budget=240)
    register_source(source="test_a", cadence="daily", ttl_seconds=86400, rate_limit_budget=240)
    # Single row, no duplicate-key error
    assert get_source("test_a") is not None


def test_record_fetch_updates_freshness():
    register_source(source="test_b", cadence="daily", ttl_seconds=86400, rate_limit_budget=240)
    record_fetch(
        source="test_b", status="ok", payload_count=12,
        rate_limit_remaining=239, error=None,
    )
    s = get_source("test_b")
    assert s.last_status == "ok"
    assert s.last_payload_count == 12
    assert s.rate_limit_remaining == 239
    assert s.last_fetched_at is not None
    assert s.next_due_at is not None
    assert s.next_due_at > s.last_fetched_at


def test_record_fetch_empty_payload_shortens_ttl(monkeypatch):
    """Per spec §6.2 empty-payload pitfall: 0 records → next_due_at within 1h."""
    register_source(source="test_c", cadence="weekly", ttl_seconds=7 * 86400, rate_limit_budget=None)
    record_fetch(source="test_c", status="empty", payload_count=0, rate_limit_remaining=None, error=None)
    s = get_source("test_c")
    # last_fetched_at + 3600s ≤ next_due_at ≤ last_fetched_at + 3700s (1h window with small slack)
    from datetime import datetime
    last = datetime.fromisoformat(s.last_fetched_at.replace("Z", "+00:00"))
    nxt = datetime.fromisoformat(s.next_due_at.replace("Z", "+00:00"))
    delta_s = (nxt - last).total_seconds()
    assert 3500 <= delta_s <= 3700


def test_get_all_sources_returns_registered_sources():
    register_source(source="test_x", cadence="daily", ttl_seconds=86400, rate_limit_budget=None)
    register_source(source="test_y", cadence="weekly", ttl_seconds=7 * 86400, rate_limit_budget=None)
    sources = {s.source for s in get_all_sources()}
    assert "test_x" in sources
    assert "test_y" in sources
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_source_freshness.py -v`
Expected: ImportError.

- [ ] **Step 3: Create the module**

Create `src/data/source_freshness.py`:

```python
"""Per-source freshness registry for Wave 1+ external data sources.

Each external source (USPTO, openFDA, USAspending, Drewry WCI, …)
registers once with its cadence and TTL. After each fetch attempt,
`record_fetch()` updates the row with last_status, last_fetched_at,
next_due_at, and rate-limit residual.

Empty-payload pitfall (spec §6.2): when payload_count is 0, we set
next_due_at to fetched_at + 1 hour (NOT the normal TTL) so the
scheduler re-attempts soon. Memory pointer:
  ~/.claude/projects/-home-shafkat-project-Trading/memory/
    project_cache_strategy.md
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.utils.db import get_connection, init_db


@dataclass(frozen=True)
class SourceFreshness:
    source: str
    cadence: str
    ttl_seconds: int
    last_fetched_at: str | None
    next_due_at: str | None
    last_status: str | None
    last_error: str | None
    last_payload_count: int | None
    rate_limit_budget: int | None
    rate_limit_remaining: int | None


_EMPTY_RETRY_SECONDS = 3600   # 1h, per spec §6.2


def register_source(
    *,
    source: str,
    cadence: str,
    ttl_seconds: int,
    rate_limit_budget: int | None,
) -> None:
    """Insert or update the registry row for a source. Idempotent."""
    init_db()
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO source_freshness
          (source, cadence, ttl_seconds, rate_limit_budget, rate_limit_remaining)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(source) DO UPDATE SET
          cadence = excluded.cadence,
          ttl_seconds = excluded.ttl_seconds,
          rate_limit_budget = excluded.rate_limit_budget
        """,
        (source, cadence, int(ttl_seconds), rate_limit_budget, rate_limit_budget),
    )
    conn.commit()
    conn.close()


def record_fetch(
    *,
    source: str,
    status: str,
    payload_count: int | None,
    rate_limit_remaining: int | None,
    error: str | None,
) -> None:
    """Update last_fetched_at, next_due_at, status, payload_count.

    Empty-payload short TTL: when payload_count == 0, next_due_at is
    `fetched_at + 1h` instead of the source's normal TTL.
    """
    init_db()
    now = datetime.now(tz=timezone.utc)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT ttl_seconds FROM source_freshness WHERE source = ?",
            (source,),
        ).fetchone()
        if row is None:
            raise ValueError(f"source not registered: {source}")
        ttl = int(row["ttl_seconds"])
        wait_s = _EMPTY_RETRY_SECONDS if payload_count == 0 else ttl
        next_due = now + timedelta(seconds=wait_s)

        conn.execute(
            """
            UPDATE source_freshness SET
              last_fetched_at = ?,
              next_due_at = ?,
              last_status = ?,
              last_error = ?,
              last_payload_count = ?,
              rate_limit_remaining = ?
            WHERE source = ?
            """,
            (
                now.isoformat(),
                next_due.isoformat(),
                status,
                error,
                int(payload_count) if payload_count is not None else None,
                rate_limit_remaining,
                source,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_source(row) -> SourceFreshness:
    return SourceFreshness(
        source=row["source"],
        cadence=row["cadence"],
        ttl_seconds=int(row["ttl_seconds"]),
        last_fetched_at=row["last_fetched_at"],
        next_due_at=row["next_due_at"],
        last_status=row["last_status"],
        last_error=row["last_error"],
        last_payload_count=row["last_payload_count"],
        rate_limit_budget=row["rate_limit_budget"],
        rate_limit_remaining=row["rate_limit_remaining"],
    )


def get_source(source: str) -> SourceFreshness | None:
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM source_freshness WHERE source = ?", (source,)
    ).fetchone()
    conn.close()
    return _row_to_source(row) if row is not None else None


def get_all_sources() -> list[SourceFreshness]:
    init_db()
    conn = get_connection()
    rows = conn.execute("SELECT * FROM source_freshness ORDER BY source").fetchall()
    conn.close()
    return [_row_to_source(r) for r in rows]
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_source_freshness.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/data/source_freshness.py tests/test_source_freshness.py
git commit -m "feat(data): add per-source freshness registry with empty-payload short TTL"
```

---

### Task F2: Pre-register the 15 Wave 1+ sources

**Files:**
- Create: `src/data/source_freshness_registry.py`
- Test: `tests/test_source_freshness_registry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_source_freshness_registry.py`:

```python
"""All 15 sector-influence sources must pre-register on import."""
from __future__ import annotations

from src.data.source_freshness import get_all_sources
from src.data.source_freshness_registry import (
    EXPECTED_SOURCES,
    register_all_wave1_plus_sources,
)


def test_all_15_sources_registered_after_call():
    register_all_wave1_plus_sources()
    registered = {s.source for s in get_all_sources()}
    for src in EXPECTED_SOURCES:
        assert src in registered, f"source not registered: {src}"


def test_expected_sources_list_size():
    # Spec §3 lists 15 "sources" but several are aggregates of multiple
    # endpoints with distinct cadences. Container rates = Drewry + Freightos
    # (2 endpoints); the Goods Flow card draws from 5 endpoints; the
    # "USDA NASS + NOAA weather" spec row is 2 sources. We track 18
    # endpoints independently for freshness.
    assert len(EXPECTED_SOURCES) == 18


def test_expected_sources_have_unique_names():
    assert len(EXPECTED_SOURCES) == len(set(EXPECTED_SOURCES))


def test_idempotent_registration():
    register_all_wave1_plus_sources()
    n1 = len(get_all_sources())
    register_all_wave1_plus_sources()
    n2 = len(get_all_sources())
    assert n1 == n2
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_source_freshness_registry.py -v`
Expected: ImportError.

- [ ] **Step 3: Create the registry**

Create `src/data/source_freshness_registry.py`:

```python
"""Catalog of the 15 sector-influence sources (Wave 1+ spec §3).

Calling `register_all_wave1_plus_sources()` makes them visible on the
`source_freshness` table — even before their data fetchers exist. The
admin /freshness page then shows them with last_fetched_at=NULL so we
can see staleness uniformly as fetchers are added wave by wave.
"""
from __future__ import annotations

from src.data.source_freshness import register_source


# (source, cadence, ttl_seconds, rate_limit_budget_per_day)
_SOURCES: tuple[tuple[str, str, int, int | None], ...] = (
    # ── Scored signals (7) ────────────────────────────────────────
    ("openfda",            "daily",     86400,   240 * 60 * 24),   # 240/min unauth
    ("usaspending",        "daily",     86400,   1000),
    ("sam_gov_entity",     "monthly",   30 * 86400, 1000),
    ("itc_edis",           "twice_daily", 12 * 3600, None),
    ("sec_8k",             "hourly",    3600,    None),            # piggybacks on existing SEC EDGAR pipeline
    ("drewry_wci",         "weekly",    7 * 86400, None),          # scrape
    ("freightos_fbx",      "daily",     86400,   None),
    ("eia_inventories",    "weekly",    7 * 86400, 5000 * 24),
    ("census_bps",         "monthly",   30 * 86400, None),
    # ── Information sources (8) ───────────────────────────────────
    ("uspto_patentsview",  "weekly",    7 * 86400, None),
    ("uspto_tsdr",         "daily",     86400,   None),
    ("cass_freight",       "monthly",   30 * 86400, None),         # scrape
    ("aar_rail",           "weekly",    7 * 86400, None),          # scrape
    ("port_of_la",         "weekly",    7 * 86400, None),          # scrape
    ("lda_lobbying",       "weekly",    7 * 86400, None),
    ("ustr_federal_register", "daily",  86400,   1000),
    ("usda_nass",          "monthly",   30 * 86400, None),
    ("noaa_weather",       "daily",     86400,   None),
)


EXPECTED_SOURCES: tuple[str, ...] = tuple(s[0] for s in _SOURCES)


def register_all_wave1_plus_sources() -> int:
    """Register all sector-influence endpoints with the freshness registry. Idempotent.

    Returns the count registered (== len(_SOURCES) on success).

    Note: spec §3 lists 15 "sources" but we track 18 endpoints because
    several spec sources are aggregates (e.g. container rates =
    Drewry + Freightos; the Goods Flow card draws on Drewry, Freightos,
    Cass, AAR, and Port of LA; USDA NASS + NOAA weather is one spec
    row = 2 endpoints).
    """
    count = 0
    for source, cadence, ttl, budget in _SOURCES:
        register_source(
            source=source, cadence=cadence,
            ttl_seconds=ttl, rate_limit_budget=budget,
        )
        count += 1
    return count
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_source_freshness_registry.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/data/source_freshness_registry.py tests/test_source_freshness_registry.py
git commit -m "feat(data): register all 15 sector-influence sources for freshness tracking"
```

---

### Task F3: Expose source-freshness via existing `/freshness` admin route

**Files:**
- Modify: `api/services/freshness_service.py`
- Test: `tests/test_freshness_service_sources.py`

- [ ] **Step 1: Inspect the existing /freshness route**

Run: `grep -n "freshness" api/routes/*.py | head -10`
Expected: shows the existing `/freshness` route (likely in `api/routes/freshness.py`).

- [ ] **Step 2: Write the failing test**

Create `tests/test_freshness_service_sources.py`:

```python
"""Tests for the extended freshness service that surfaces source registry."""
from __future__ import annotations

from api.services.freshness_service import get_sources_status
from src.data.source_freshness_registry import (
    EXPECTED_SOURCES,
    register_all_wave1_plus_sources,
)


def test_get_sources_status_returns_all_registered():
    register_all_wave1_plus_sources()
    status = get_sources_status()
    assert "sources" in status
    sources = {row["source"] for row in status["sources"]}
    for src in EXPECTED_SOURCES:
        assert src in sources


def test_get_sources_status_includes_counts_by_status():
    register_all_wave1_plus_sources()
    status = get_sources_status()
    assert "counts" in status
    # All sources are freshly registered with no fetch yet → 'never_fetched'
    assert status["counts"].get("never_fetched", 0) >= len(EXPECTED_SOURCES)
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/pytest tests/test_freshness_service_sources.py -v`
Expected: ImportError on `get_sources_status`.

- [ ] **Step 4: Add `get_sources_status` to `api/services/freshness_service.py`**

Append to `api/services/freshness_service.py`:

```python


# ── Sector-influence Wave 1: per-source freshness surface ────────────


def get_sources_status() -> dict:
    """Return the per-source freshness registry for the admin /freshness page.

    Shape:
        {
          "sources": [ {source, cadence, ttl_seconds, last_fetched_at,
                        next_due_at, last_status, last_payload_count,
                        rate_limit_remaining, ...}, ... ],
          "counts": {"never_fetched": N, "ok": M, "error": K, "empty": E, ...},
        }
    """
    from src.data.source_freshness import get_all_sources

    rows = get_all_sources()
    out: list[dict] = []
    counts: dict[str, int] = {}
    for r in rows:
        status_key = r.last_status if r.last_status else "never_fetched"
        counts[status_key] = counts.get(status_key, 0) + 1
        out.append({
            "source": r.source,
            "cadence": r.cadence,
            "ttl_seconds": r.ttl_seconds,
            "last_fetched_at": r.last_fetched_at,
            "next_due_at": r.next_due_at,
            "last_status": r.last_status,
            "last_error": r.last_error,
            "last_payload_count": r.last_payload_count,
            "rate_limit_budget": r.rate_limit_budget,
            "rate_limit_remaining": r.rate_limit_remaining,
        })
    return {"sources": out, "counts": counts}
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/pytest tests/test_freshness_service_sources.py -v`
Expected: 2 PASSED.

- [ ] **Step 6: Commit**

```bash
git add api/services/freshness_service.py tests/test_freshness_service_sources.py
git commit -m "feat(freshness): expose sector-influence source registry via /freshness"
```

---

### Task F4: Per-source rate-limit token bucket (gateway scaffold)

Per spec §6.3 — extend `gateway.py` with per-source token buckets so Wave 2+ fetchers can call a single `acquire()` before hitting external APIs. Wave 1 only builds the scaffold (no fetcher uses it yet).

**Files:**
- Create: `src/data/rate_limit.py`
- Test: `tests/test_rate_limit.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rate_limit.py`:

```python
"""Tests for per-source token-bucket rate limiter (Wave 1 scaffold)."""
from __future__ import annotations

import time

import pytest

from src.data.rate_limit import RateLimited, TokenBucket, acquire, configure


def test_token_bucket_initial_capacity_allows_n_calls():
    tb = TokenBucket(capacity=3, refill_per_second=0)  # no refill
    assert tb.try_acquire() is True
    assert tb.try_acquire() is True
    assert tb.try_acquire() is True
    assert tb.try_acquire() is False


def test_token_bucket_refills_over_time():
    tb = TokenBucket(capacity=2, refill_per_second=10.0)  # 10/s refill
    assert tb.try_acquire() is True
    assert tb.try_acquire() is True
    assert tb.try_acquire() is False
    time.sleep(0.15)  # refill ~1.5 tokens
    assert tb.try_acquire() is True


def test_configure_and_acquire_for_named_source():
    configure(source="test_source_X", capacity=2, refill_per_second=0)
    acquire("test_source_X")   # 1
    acquire("test_source_X")   # 2
    with pytest.raises(RateLimited):
        acquire("test_source_X")  # exceeds capacity


def test_acquire_for_unconfigured_source_is_noop():
    # Unknown sources have no limit (caller controls); acquire never raises.
    acquire("totally_unknown_source_zzz")
    acquire("totally_unknown_source_zzz")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_rate_limit.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement the rate limiter**

Create `src/data/rate_limit.py`:

```python
"""Per-source token-bucket rate limiter (Wave 1 scaffold).

Wave 2+ fetchers call `acquire(source)` before each external request.
Unconfigured sources are unlimited — `configure()` must be called once
(typically at app start, alongside `register_all_wave1_plus_sources`).

Per CLAUDE.md: this is `data/` — it may be imported by all fetchers but
NOT by `analysis/`, `reports/`, or `models/`.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


class RateLimited(Exception):
    """Raised when a source's bucket is empty. Caller may sleep and retry."""


@dataclass
class TokenBucket:
    capacity: int
    refill_per_second: float
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.capacity)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed > 0 and self.refill_per_second > 0:
            self._tokens = min(
                float(self.capacity),
                self._tokens + elapsed * self.refill_per_second,
            )
            self._last_refill = now

    def try_acquire(self, n: int = 1) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return True
            return False


_BUCKETS: dict[str, TokenBucket] = {}
_BUCKETS_LOCK = threading.Lock()


def configure(*, source: str, capacity: int, refill_per_second: float) -> None:
    """Register (or replace) a bucket for a source. Idempotent."""
    with _BUCKETS_LOCK:
        _BUCKETS[source] = TokenBucket(capacity=capacity, refill_per_second=refill_per_second)


def acquire(source: str, n: int = 1) -> None:
    """Acquire `n` tokens from a source's bucket. Raises RateLimited when empty.

    Unconfigured sources are unlimited (returns immediately).
    """
    with _BUCKETS_LOCK:
        bucket = _BUCKETS.get(source)
    if bucket is None:
        return
    if not bucket.try_acquire(n):
        raise RateLimited(f"rate-limited on source={source}")
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_rate_limit.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/data/rate_limit.py tests/test_rate_limit.py
git commit -m "feat(data): add per-source token-bucket rate limiter scaffold"
```

---

## Phase G: Full Wave 1 verification + smoke test

### Task G1: End-to-end Wave 1 smoke test

**Files:**
- Test: `tests/test_wave1_smoke.py`

- [ ] **Step 1: Write the smoke test**

Create `tests/test_wave1_smoke.py`:

```python
"""End-to-end smoke test of Wave 1 foundation.

Walks every public surface added in Wave 1:
  - Schema tables exist
  - Manual override seeder works
  - Resolver returns the right ticker
  - Source registry knows about all 15 sources
  - assert_no_lookahead enforces point-in-time
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.analysis.edge_validator import LookaheadViolation, assert_no_lookahead
from src.analysis.sector_signals._shared import (
    Fact,
    SignalReading,
    StockInformation,
)
from src.data.entity_aliases import (
    insert_alias,
    resolve_ticker,
    seed_from_overrides,
)
from src.data.source_freshness import get_all_sources
from src.data.source_freshness_registry import (
    EXPECTED_SOURCES,
    register_all_wave1_plus_sources,
)
from src.utils.db import get_connection, init_db


def test_wave1_smoke_end_to_end():
    init_db()

    # 1) Manual overrides seed: BRK.B dual-class
    seed_from_overrides()
    r = resolve_ticker("Berkshire Hathaway Class B")
    assert r is not None and r.ticker == "BRK.B"

    # 2) Subsidiary rollup: Beats Electronics LLC → AAPL
    r = resolve_ticker("Beats Electronics LLC")
    assert r is not None and r.ticker == "AAPL"

    # 3) Fuzzy match (information threshold)
    insert_alias(
        ticker="LMT", cik=None, uei=None,
        alias_type="legal", alias_name="lockheed martin",
        alias_source="smoke_test", confidence=1.0,
        created_at="2026-05-15T00:00:00Z",
    )
    r = resolve_ticker("Lockheed-Martin Co", use_fuzzy=True, min_confidence=0.8)
    assert r is not None and r.ticker == "LMT"

    # 4) Source registry has all 15+ sources
    register_all_wave1_plus_sources()
    registered = {s.source for s in get_all_sources()}
    for src in EXPECTED_SOURCES:
        assert src in registered

    # 5) StockInformation construction (information-only output)
    si = StockInformation(
        ticker="AAPL", topic="innovation",
        headline="Filed 1,247 patents in last 12mo",
        facts=[Fact(
            text="1247 patents", as_of="2026-05-15T00:00:00Z",
            source="uspto", source_url=None, confidence=1.0,
        )],
        narrative=None, implications=[], related_catalysts=[],
        confidence="high", as_of="2026-05-15T00:00:00Z",
        sources_used=["uspto"], severity="low",
    )
    assert si.ticker == "AAPL"

    # 6) SignalReading construction with Decimal
    sr = SignalReading(
        ticker="LMT", sector=None, signal_name="gov_contract_award",
        value=Decimal("4200000000"), z_score=None,
        direction="bullish", confidence="high",
        as_of="2026-05-10T00:00:00Z",
        available_at="2026-05-13T00:00:00Z",
        point_in_time_lag_days=3, source="usaspending",
    )

    # 7) Lookahead gate: a reading available 2026-05-13 is OK for 2026-05-15 decision
    assert_no_lookahead([sr], decision_timestamp="2026-05-15T00:00:00Z")

    # 8) Lookahead gate: a reading available 2026-05-20 is NOT OK for 2026-05-15 decision
    sr_future = SignalReading(
        ticker="X", sector=None, signal_name="x",
        value=Decimal("1"), z_score=None,
        direction="neutral", confidence="low",
        as_of="2026-05-20T00:00:00Z",
        available_at="2026-05-20T00:00:00Z",
        point_in_time_lag_days=0, source="test",
    )
    with pytest.raises(LookaheadViolation):
        assert_no_lookahead([sr_future], decision_timestamp="2026-05-15T00:00:00Z")
```

- [ ] **Step 2: Run the smoke test**

Run: `.venv/bin/pytest tests/test_wave1_smoke.py -v`
Expected: 1 PASSED.

- [ ] **Step 3: Run the full test suite to confirm zero regressions**

Run: `.venv/bin/pytest tests/ -v --ignore=tests/test_news_impact_api.py 2>&1 | tail -40`

(The ignore is just because that test may hit external APIs; check whether your suite typically skips it.)

Expected: all Wave 1 tests + pre-existing tests PASS. Investigate any newly-failing pre-existing test before continuing.

- [ ] **Step 4: Commit**

```bash
git add tests/test_wave1_smoke.py
git commit -m "test: end-to-end smoke test for sector-influence Wave 1"
```

---

## Phase H: Documentation

### Task H1: Mark Wave 1 verifications complete in the spec

**Files:**
- Modify: `docs/superpowers/specs/2026-05-15-sector-influence-signals-design.md` (§11)

- [ ] **Step 1: Update the spec's "Open verifications" section**

The spec's §11 lists four pre-implementation verifications. Now we know:

| Item | Status |
|---|---|
| EIA coverage in `src/data/macro.py` | **NOT present.** New module `src/data/eia_inventories.py` required in Wave 3. |
| 8-K Item 5.02 extraction in `src/data/sec_edgar.py` | **NOT present.** Needs to be added in Wave 2 (exec turnover signal). |
| 10-K Exhibit 21 parsing | **Added in Wave 1** by Task D3 — `parse_exhibit_21_subsidiaries`. |
| `RefreshableResponse` shape | Verify in Wave 2 first task. |

Edit `docs/superpowers/specs/2026-05-15-sector-influence-signals-design.md` and replace §11 (the "Open verifications before implementation" section) with the resolved status above. Use this exact text:

```markdown
## 11. Verifications resolved during Wave 1

| Item | Outcome | Where addressed |
|---|---|---|
| EIA coverage in `src/data/macro.py` | NOT present | Build new `src/data/eia_inventories.py` in Wave 3 |
| 8-K Item 5.02 extraction in `src/data/sec_edgar.py` | NOT present | Add in Wave 2 (exec turnover signal) |
| 10-K Exhibit 21 parsing | Added in Wave 1 | `src/data/sec_10k_extractor.py::parse_exhibit_21_subsidiaries` |
| `RefreshableResponse` shape | Open | Verify as first task of Wave 2 plan |
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-15-sector-influence-signals-design.md
git commit -m "docs: resolve Wave 1 verifications in sector-influence spec"
```

---

## Wave 1 complete — handoff to Wave 2

At this point:
- Three new tables live in `trading.db`: `entity_aliases`, `source_freshness`, `known_future_events`
- `StockInformation` and `SignalReading` dataclasses live at `src/analysis/sector_signals/_shared.py`
- Entity-alias resolver supports exact (CIK/UEI) + ≥0.9 (scored) / ≥0.8 (information) fuzzy matching
- Manual overrides loaded from `src/data/entity_overrides.yaml`
- 10-K Exhibit 21 parsing seeds parent→subsidiary aliases
- Lookahead gate (`assert_no_lookahead`) wired into the backtester
- All 18 sector-influence endpoints pre-registered for freshness tracking
- `/freshness` admin route surfaces source-level status
- Per-source token-bucket rate limiter scaffold (`src/data/rate_limit.py`) ready for Wave 2+ fetchers to call

Wave 2 plan will:
- Add SAM.gov entity-API seeder + PatentsView assignee canonicalization (deferred from Wave 1)
- Build USPTO patents + trademarks → Innovation card
- Build openFDA → FDA Catalysts card
- Build USAspending + SAM.gov → Backlog card
- Build ITC EDIS → Alerts + Risk narrative bullets
- Build SEC 8-K Item 5.02 extraction → Alerts + Risk narrative bullets
- Integrate the 6 new scored signals into Bubble Score with documented default weights
