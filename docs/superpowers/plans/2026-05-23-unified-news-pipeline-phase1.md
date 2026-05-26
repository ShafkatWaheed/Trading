# Unified News Pipeline — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify per-stock news fetching from eight sources (Finnhub, Tiingo, Tavily, Exa, Yahoo Finance RSS, Google News RSS, GDELT, Reddit) behind one `NewsItem` schema with deduplication, importance scoring, quota cooldown for paid APIs, and a single ticker-feed endpoint.

**Architecture:** New adapters in `src/data/news_adapters/` (each pure: dict → `NewsItem`). New `src/analysis/news_*.py` modules hold pure dedup + scoring. A single orchestrator in `src/reports/news_feed.py` fans out across data fetchers, normalizes, dedups, scores, persists. Four new zero-cost / no-key sources (Yahoo Finance RSS, Google News RSS, GDELT DOC 2.0, Reddit search) act as quota-free primaries so the feed stays useful even when Tavily/Exa quotas are exhausted. Reddit posts carry `source_type="social"` and use the `volume_metric` field for upvote scores so social hype is distinguishable from financial news downstream. New SQLite tables `news_items` + `news_ticker_tags` are the store. Existing fetchers (`src/data/finnhub.get_company_news`, `src/data/tiingo.get_news`, `src/data/news.NewsProvider`) are reused.

**Tech Stack:** Python 3.11+, pydantic v2, SQLite (via `src.utils.db`), pytest. No new external dependencies.

---

## File Structure

**New files:**
- `src/models/news_item.py` — Pydantic `NewsItem` model
- `src/data/news_adapters/__init__.py` — package init
- `src/data/news_adapters/finnhub_adapter.py` — Finnhub dict → NewsItem
- `src/data/news_adapters/tiingo_adapter.py` — Tiingo dict → NewsItem
- `src/data/news_adapters/tavily_adapter.py` — Tavily dict → NewsItem
- `src/data/news_adapters/exa_adapter.py` — Exa dict → NewsItem
- `src/data/yahoo_finance_rss.py` — Yahoo Finance ticker RSS fetcher (no key)
- `src/data/news_adapters/yahoo_finance_adapter.py` — Yahoo dict → NewsItem
- `src/data/google_news_rss.py` — Google News RSS fetcher (no key)
- `src/data/news_adapters/google_news_adapter.py` — Google News dict → NewsItem
- `src/data/gdelt_doc.py` — GDELT DOC 2.0 JSON fetcher (no key)
- `src/data/news_adapters/gdelt_adapter.py` — GDELT dict → NewsItem
- `src/data/reddit_search.py` — Reddit ticker search across financial subreddits (no key)
- `src/data/news_adapters/reddit_adapter.py` — Reddit post → NewsItem (source_type="social")
- `src/data/news_store.py` — DB read/write for `news_items`
- `src/data/quota_tracker.py` — cache-backed source cooldown for quota-bound APIs
- `src/analysis/news_dedup.py` — pure clustering
- `src/analysis/news_importance.py` — pure scoring
- `src/reports/news_feed.py` — orchestrator (fetch + normalize + dedup + score + save)
- `api/routes/news_unified.py` — new route exposing the unified feed
- `tests/test_news_adapters.py`
- `tests/test_news_store.py`
- `tests/test_news_dedup.py`
- `tests/test_news_importance.py`
- `tests/test_quota_tracker.py`
- `tests/test_yahoo_finance_rss.py`
- `tests/test_google_news_rss.py`
- `tests/test_gdelt_doc.py`
- `tests/test_reddit_search.py`
- `tests/test_news_feed_orchestrator.py`

**Modified files:**
- `src/utils/db.py` — add three `CREATE TABLE` statements to `init_db()`
- `src/data/news.py` — make `NewsProvider._tavily_search` / `_exa_search` mark quota exhaustion on 402/403/429
- `api/services/news_feed_service.py` — swap implementation to call the orchestrator (last task)
- `api/main.py` — register `news_unified` router

> Note: We use `news_adapters` (not `news/`) as the package name because `src/data/news.py` (the existing `NewsProvider` module) already occupies the `src.data.news` import path. Renaming would break callers.

---

## Task 1: SQLite schema for unified news

**Files:**
- Modify: `src/utils/db.py:498` (inside the `init_db()` executescript block, before `conn.commit()`)
- Test: `tests/test_news_store.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_news_store.py`:

```python
"""Schema sanity tests for unified news tables.

All tests run against the session-scoped temp DB (see conftest.py).
"""
from __future__ import annotations

import sqlite3
import pytest

from src.utils.db import get_connection, init_db


def test_news_tables_exist():
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name IN ('news_items', 'news_ticker_tags', 'news_clusters')"
    ).fetchall()
    conn.close()
    names = {r["name"] for r in rows}
    assert names == {"news_items", "news_ticker_tags", "news_clusters"}


def test_news_items_columns():
    init_db()
    conn = get_connection()
    cols = {row["name"]: row["type"] for row in conn.execute("PRAGMA table_info(news_items)").fetchall()}
    conn.close()
    expected = {
        "id", "source", "source_type", "external_id", "url", "title",
        "summary", "body", "published_at", "fetched_at",
        "author", "sentiment_score", "importance_score",
        "volume_metric", "cluster_id", "raw_json",
    }
    assert expected.issubset(cols.keys())


def test_news_items_url_unique_constraint():
    init_db()
    conn = get_connection()
    conn.execute(
        "INSERT INTO news_items (source, source_type, url, title, published_at, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("finnhub", "news", "https://example.com/a", "T", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO news_items (source, source_type, url, title, published_at, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("tiingo", "news", "https://example.com/a", "T2", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_news_store.py -v`
Expected: 3 FAILs ("no such table: news_items", etc).

- [ ] **Step 3: Add the schema to `init_db()`**

In `src/utils/db.py`, inside the `conn.executescript("""...""")` block in `init_db()` (around line 497, immediately after the existing `entity_match_decisions` indexes and before the closing `""")`), append:

```sql
-- ── Unified news pipeline (Phase 1) ─────────────────────────────────
-- One row per de-duplicated article from any source. `url` is unique
-- across sources so the same article fetched twice collapses to one row.
CREATE TABLE IF NOT EXISTS news_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,                  -- 'finnhub' | 'tiingo' | 'tavily' | 'exa'
    source_type     TEXT NOT NULL,                  -- 'news' | 'social' | 'filing' | 'transcript'
    external_id     TEXT,                           -- source-native id when available
    url             TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    summary         TEXT,
    body            TEXT,
    published_at    TEXT NOT NULL,                  -- ISO 8601 UTC
    fetched_at      TEXT NOT NULL,                  -- ISO 8601 UTC
    author          TEXT,
    sentiment_score REAL,                           -- -1..+1, native if provided else NULL
    importance_score REAL,                          -- 0..1, computed downstream
    volume_metric   REAL,                           -- mentions / upvotes (social only)
    cluster_id      TEXT,                           -- groups duplicate stories across sources
    raw_json        TEXT                            -- original source payload (debugging)
);
CREATE INDEX IF NOT EXISTS idx_news_items_published ON news_items(published_at);
CREATE INDEX IF NOT EXISTS idx_news_items_source ON news_items(source);
CREATE INDEX IF NOT EXISTS idx_news_items_cluster ON news_items(cluster_id);

-- Ticker tags (M2M): a single article can mention multiple tickers.
CREATE TABLE IF NOT EXISTS news_ticker_tags (
    news_id     INTEGER NOT NULL,
    ticker      TEXT NOT NULL,
    PRIMARY KEY (news_id, ticker),
    FOREIGN KEY (news_id) REFERENCES news_items(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_news_ticker_tags_ticker ON news_ticker_tags(ticker);

-- Cluster metadata: one row per cluster, tracks how many sources covered the story.
CREATE TABLE IF NOT EXISTS news_clusters (
    cluster_id      TEXT PRIMARY KEY,
    representative_title TEXT NOT NULL,
    first_seen_at   TEXT NOT NULL,
    source_count    INTEGER NOT NULL DEFAULT 1
);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_news_store.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/utils/db.py tests/test_news_store.py
git commit -m "feat(data): add unified news_items schema for Phase 1 pipeline"
```

---

## Task 2: NewsItem Pydantic model

**Files:**
- Create: `src/models/news_item.py`
- Test: `tests/test_news_item_model.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_news_item_model.py`:

```python
"""Tests for the unified NewsItem pydantic model."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.models.news_item import NewsItem


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_news_item_minimum_required_fields():
    item = NewsItem(
        source="finnhub",
        source_type="news",
        url="https://example.com/a",
        title="Headline",
        published_at=_now_iso(),
        fetched_at=_now_iso(),
    )
    assert item.tickers == []
    assert item.sentiment_score is None
    assert item.importance_score is None


def test_news_item_with_tickers():
    item = NewsItem(
        source="finnhub",
        source_type="news",
        url="https://example.com/b",
        title="AAPL beats earnings",
        published_at=_now_iso(),
        fetched_at=_now_iso(),
        tickers=["AAPL", "MSFT"],
    )
    assert "AAPL" in item.tickers
    assert "MSFT" in item.tickers


def test_news_item_rejects_invalid_source_type():
    with pytest.raises(Exception):
        NewsItem(
            source="finnhub",
            source_type="not_a_real_type",
            url="https://example.com/c",
            title="X",
            published_at=_now_iso(),
            fetched_at=_now_iso(),
        )


def test_news_item_rejects_invalid_sentiment_range():
    with pytest.raises(Exception):
        NewsItem(
            source="finnhub",
            source_type="news",
            url="https://example.com/d",
            title="X",
            published_at=_now_iso(),
            fetched_at=_now_iso(),
            sentiment_score=2.5,
        )


def test_news_item_published_at_must_be_iso():
    with pytest.raises(Exception):
        NewsItem(
            source="finnhub",
            source_type="news",
            url="https://example.com/e",
            title="X",
            published_at="not-a-date",
            fetched_at=_now_iso(),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_news_item_model.py -v`
Expected: 5 FAILs ("No module named 'src.models.news_item'").

- [ ] **Step 3: Implement the model**

Create `src/models/news_item.py`:

```python
"""Unified news item — one schema across all news sources.

Every adapter in src/data/news_adapters/ produces NewsItem instances.
The orchestrator (src/reports/news_feed.py) accepts and persists them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


SourceType = Literal["news", "social", "filing", "transcript"]


class NewsItem(BaseModel):
    """Normalized news item.

    Timestamps are ISO 8601 UTC strings (project convention — see CLAUDE.md).
    sentiment_score is -1..+1 when available; importance_score is 0..1.
    """

    source: str = Field(..., description="e.g. 'finnhub', 'tiingo', 'tavily', 'exa'")
    source_type: SourceType
    external_id: str | None = None
    url: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    summary: str | None = None
    body: str | None = None
    published_at: str
    fetched_at: str
    author: str | None = None
    sentiment_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    importance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    volume_metric: float | None = None
    cluster_id: str | None = None
    tickers: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    raw_json: str | None = None

    @field_validator("published_at", "fetched_at")
    @classmethod
    def _iso_timestamp(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            raise ValueError(f"timestamp must be ISO 8601, got {v!r}") from e
        return v

    @field_validator("tickers")
    @classmethod
    def _uppercase_tickers(cls, v: list[str]) -> list[str]:
        return [t.upper().strip() for t in v if t and t.strip()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_news_item_model.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/models/news_item.py tests/test_news_item_model.py
git commit -m "feat(models): add unified NewsItem pydantic model"
```

---

## Task 3: Finnhub adapter

**Files:**
- Create: `src/data/news_adapters/__init__.py`
- Create: `src/data/news_adapters/finnhub_adapter.py`
- Test: `tests/test_news_adapters.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_news_adapters.py`:

```python
"""Tests for source-specific dict → NewsItem adapters.

Each adapter is a pure function over a single source's response dict.
Tests construct fake response dicts — they never hit the network.
"""
from __future__ import annotations

from src.data.news_adapters.finnhub_adapter import finnhub_to_news_item


def test_finnhub_adapter_basic():
    raw = {
        "category": "company",
        "datetime": 1735689600,  # 2025-01-01T00:00:00Z
        "headline": "AAPL beats Q4 earnings",
        "id": 7401234,
        "image": "https://img.example.com/x.jpg",
        "related": "AAPL",
        "source": "Reuters",
        "summary": "Apple reported strong iPhone sales...",
        "url": "https://reuters.example.com/aapl-q4",
    }
    item = finnhub_to_news_item(raw, symbol="AAPL")
    assert item is not None
    assert item.source == "finnhub"
    assert item.source_type == "news"
    assert item.url == "https://reuters.example.com/aapl-q4"
    assert item.title == "AAPL beats Q4 earnings"
    assert item.summary == "Apple reported strong iPhone sales..."
    assert item.external_id == "7401234"
    assert "AAPL" in item.tickers
    assert item.author == "Reuters"
    assert item.published_at.startswith("2025-01-01T")


def test_finnhub_adapter_missing_url_returns_none():
    raw = {"datetime": 1735689600, "headline": "X"}
    assert finnhub_to_news_item(raw, symbol="AAPL") is None


def test_finnhub_adapter_missing_headline_returns_none():
    raw = {"datetime": 1735689600, "url": "https://x.com/a"}
    assert finnhub_to_news_item(raw, symbol="AAPL") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_news_adapters.py -v`
Expected: FAIL ("No module named 'src.data.news_adapters.finnhub_adapter'").

- [ ] **Step 3: Implement the adapter**

Create `src/data/news_adapters/__init__.py`:

```python
"""Source-specific news adapters. Each module exports a pure function
that converts one source's response dict into a NewsItem.

Adapters never make network calls — that's the job of src/data/*.py fetchers.
"""
```

Create `src/data/news_adapters/finnhub_adapter.py`:

```python
"""Finnhub /company-news row → NewsItem.

Source row shape (from src.data.finnhub.get_company_news):
    {"datetime": int (epoch seconds),
     "headline": str, "summary": str, "url": str, "source": str,
     "id": int, "image": str, "related": str, "category": str}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.models.news_item import NewsItem


def finnhub_to_news_item(row: dict, *, symbol: str) -> NewsItem | None:
    """Convert one Finnhub company-news row to a NewsItem.

    Returns None if the row is missing fields the NewsItem requires
    (url or headline). Caller filters Nones.
    """
    url = (row.get("url") or "").strip()
    title = (row.get("headline") or "").strip()
    if not url or not title:
        return None

    ts = row.get("datetime")
    try:
        published_at = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None

    return NewsItem(
        source="finnhub",
        source_type="news",
        external_id=str(row["id"]) if row.get("id") is not None else None,
        url=url,
        title=title,
        summary=(row.get("summary") or "").strip() or None,
        published_at=published_at,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        author=(row.get("source") or "").strip() or None,
        tickers=[symbol.upper()],
        raw_json=json.dumps(row, default=str),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_news_adapters.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data/news_adapters/__init__.py src/data/news_adapters/finnhub_adapter.py tests/test_news_adapters.py
git commit -m "feat(data): add Finnhub → NewsItem adapter"
```

---

## Task 4: Tiingo adapter

**Files:**
- Create: `src/data/news_adapters/tiingo_adapter.py`
- Test: append to `tests/test_news_adapters.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_news_adapters.py`:

```python
from src.data.news_adapters.tiingo_adapter import tiingo_to_news_item


def test_tiingo_adapter_basic():
    raw = {
        "id": 12345,
        "title": "Apple unveils new chip",
        "description": "At its annual event...",
        "url": "https://tiingo.example.com/aapl-chip",
        "publishedDate": "2025-01-15T14:30:00Z",
        "source": "tiingo-bloomberg",
        "tickers": ["aapl", "msft"],
        "tags": ["earnings", "tech"],
        "crawlDate": "2025-01-15T14:31:00Z",
    }
    item = tiingo_to_news_item(raw)
    assert item.source == "tiingo"
    assert item.url == "https://tiingo.example.com/aapl-chip"
    assert "AAPL" in item.tickers and "MSFT" in item.tickers
    assert item.topics == ["earnings", "tech"]
    assert item.published_at.startswith("2025-01-15T14:30")


def test_tiingo_adapter_skips_when_no_url():
    assert tiingo_to_news_item({"title": "x", "publishedDate": "2025-01-15T14:30:00Z"}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_news_adapters.py -v`
Expected: 2 new FAILs ("No module named 'src.data.news_adapters.tiingo_adapter'").

- [ ] **Step 3: Implement the adapter**

Create `src/data/news_adapters/tiingo_adapter.py`:

```python
"""Tiingo /tiingo/news row → NewsItem.

Source row shape (from src.data.tiingo.get_news):
    {"id": int, "title": str, "description": str, "url": str,
     "publishedDate": str (ISO), "source": str,
     "tickers": list[str], "tags": list[str], "crawlDate": str}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.models.news_item import NewsItem


def tiingo_to_news_item(row: dict) -> NewsItem | None:
    url = (row.get("url") or "").strip()
    title = (row.get("title") or "").strip()
    published = (row.get("publishedDate") or "").strip()
    if not url or not title or not published:
        return None

    try:
        # Tiingo emits trailing 'Z' or +HH:MM offsets — fromisoformat handles both
        # in py3.11+ as long as Z is normalized.
        datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return None

    tickers = row.get("tickers") or []
    tags = row.get("tags") or []

    return NewsItem(
        source="tiingo",
        source_type="news",
        external_id=str(row["id"]) if row.get("id") is not None else None,
        url=url,
        title=title,
        summary=(row.get("description") or "").strip() or None,
        published_at=published,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        author=(row.get("source") or "").strip() or None,
        tickers=[t for t in tickers if isinstance(t, str)],
        topics=[t for t in tags if isinstance(t, str)],
        raw_json=json.dumps(row, default=str),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_news_adapters.py -v`
Expected: 5 PASS total.

- [ ] **Step 5: Commit**

```bash
git add src/data/news_adapters/tiingo_adapter.py tests/test_news_adapters.py
git commit -m "feat(data): add Tiingo → NewsItem adapter"
```

---

## Task 5: Tavily adapter

**Files:**
- Create: `src/data/news_adapters/tavily_adapter.py`
- Test: append to `tests/test_news_adapters.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_news_adapters.py`:

```python
from src.data.news_adapters.tavily_adapter import tavily_to_news_item


def test_tavily_adapter_basic():
    raw = {
        "title": "Microsoft expands Azure",
        "url": "https://techcrunch.example.com/msft-azure",
        "source": "techcrunch.example.com",
        "published": "2025-02-10T09:00:00Z",
        "content_snippet": "Microsoft announced today...",
    }
    item = tavily_to_news_item(raw, symbol="MSFT")
    assert item.source == "tavily"
    assert "MSFT" in item.tickers
    assert item.author == "techcrunch.example.com"
    assert item.published_at.startswith("2025-02-10")


def test_tavily_adapter_defaults_published_when_blank():
    raw = {
        "title": "Some headline",
        "url": "https://example.com/x",
        "source": "example.com",
        "published": "",
        "content_snippet": "...",
    }
    item = tavily_to_news_item(raw, symbol="AAPL")
    # When the source omits the published date, the adapter defaults to fetched_at
    # so the article is still usable in the feed.
    assert item is not None
    assert item.published_at == item.fetched_at


def test_tavily_adapter_skips_when_no_url():
    raw = {"title": "x", "url": "", "source": "y", "published": "2025-02-10T09:00:00Z"}
    assert tavily_to_news_item(raw, symbol="AAPL") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_news_adapters.py -v`
Expected: 3 new FAILs.

- [ ] **Step 3: Implement the adapter**

Create `src/data/news_adapters/tavily_adapter.py`:

```python
"""Tavily search result → NewsItem.

Source row shape (from src.data.news.NewsProvider._tavily_search):
    {"title": str, "url": str, "source": str (host),
     "published": str (ISO or empty), "content_snippet": str}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.models.news_item import NewsItem


def tavily_to_news_item(row: dict, *, symbol: str) -> NewsItem | None:
    url = (row.get("url") or "").strip()
    title = (row.get("title") or "").strip()
    if not url or not title:
        return None

    fetched_at = datetime.now(timezone.utc).isoformat()
    published_raw = (row.get("published") or "").strip()
    published_at = fetched_at
    if published_raw:
        try:
            datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
            published_at = published_raw
        except ValueError:
            published_at = fetched_at

    return NewsItem(
        source="tavily",
        source_type="news",
        url=url,
        title=title,
        summary=(row.get("content_snippet") or "").strip() or None,
        published_at=published_at,
        fetched_at=fetched_at,
        author=(row.get("source") or "").strip() or None,
        tickers=[symbol.upper()],
        raw_json=json.dumps(row, default=str),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_news_adapters.py -v`
Expected: 8 PASS total.

- [ ] **Step 5: Commit**

```bash
git add src/data/news_adapters/tavily_adapter.py tests/test_news_adapters.py
git commit -m "feat(data): add Tavily → NewsItem adapter"
```

---

## Task 6: Exa adapter

**Files:**
- Create: `src/data/news_adapters/exa_adapter.py`
- Test: append to `tests/test_news_adapters.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_news_adapters.py`:

```python
from src.data.news_adapters.exa_adapter import exa_to_news_item


def test_exa_adapter_basic():
    raw = {
        "title": "Tesla announces new factory",
        "url": "https://reuters.example.com/tsla-factory",
        "source": "reuters.example.com",
        "published": "2025-03-01T12:00:00Z",
        "content_snippet": "Tesla said today that it will build...",
    }
    item = exa_to_news_item(raw, symbol="TSLA")
    assert item.source == "exa"
    assert "TSLA" in item.tickers
    assert item.author == "reuters.example.com"


def test_exa_adapter_skips_when_no_url():
    raw = {"title": "x", "url": "", "source": "y"}
    assert exa_to_news_item(raw, symbol="TSLA") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_news_adapters.py -v`
Expected: 2 new FAILs.

- [ ] **Step 3: Implement the adapter**

Create `src/data/news_adapters/exa_adapter.py`:

```python
"""Exa search result → NewsItem.

Same shape as Tavily (NewsProvider normalizes both to the same dict shape),
but tagged with source='exa' so callers can tell them apart.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.models.news_item import NewsItem


def exa_to_news_item(row: dict, *, symbol: str) -> NewsItem | None:
    url = (row.get("url") or "").strip()
    title = (row.get("title") or "").strip()
    if not url or not title:
        return None

    fetched_at = datetime.now(timezone.utc).isoformat()
    published_raw = (row.get("published") or "").strip()
    published_at = fetched_at
    if published_raw:
        try:
            datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
            published_at = published_raw
        except ValueError:
            published_at = fetched_at

    return NewsItem(
        source="exa",
        source_type="news",
        url=url,
        title=title,
        summary=(row.get("content_snippet") or "").strip() or None,
        published_at=published_at,
        fetched_at=fetched_at,
        author=(row.get("source") or "").strip() or None,
        tickers=[symbol.upper()],
        raw_json=json.dumps(row, default=str),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_news_adapters.py -v`
Expected: 10 PASS total.

- [ ] **Step 5: Commit**

```bash
git add src/data/news_adapters/exa_adapter.py tests/test_news_adapters.py
git commit -m "feat(data): add Exa → NewsItem adapter"
```

---

## Task 7: News deduplication (pure analysis)

**Files:**
- Create: `src/analysis/news_dedup.py`
- Test: `tests/test_news_dedup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_news_dedup.py`:

```python
"""Tests for cross-source news clustering.

Two articles cluster together when:
  - URLs are identical, OR
  - Normalized titles match AND published_at falls in the same hour bucket.
"""
from __future__ import annotations

from src.analysis.news_dedup import cluster_news_items, normalize_title
from src.models.news_item import NewsItem


def _item(source: str, url: str, title: str, published: str) -> NewsItem:
    return NewsItem(
        source=source,
        source_type="news",
        url=url,
        title=title,
        published_at=published,
        fetched_at="2026-01-01T00:00:00+00:00",
        tickers=["SYN_X"],
    )


def test_normalize_title_strips_punctuation_and_case():
    assert normalize_title("Apple's Q4 Beats!!! (Strong iPhone)") == normalize_title("APPLE'S Q4 beats strong iphone")


def test_cluster_identical_urls():
    a = _item("finnhub", "https://example.com/a", "Headline One", "2026-01-01T10:00:00+00:00")
    b = _item("tiingo", "https://example.com/a", "Different Title", "2026-01-01T10:00:00+00:00")
    clusters = cluster_news_items([a, b])
    assert a.cluster_id == b.cluster_id
    assert len(clusters) == 1


def test_cluster_same_title_same_hour():
    a = _item("finnhub", "https://x.com/a", "Apple beats Q4 earnings", "2026-01-01T10:05:00+00:00")
    b = _item("tiingo", "https://y.com/b", "Apple beats Q4 earnings!", "2026-01-01T10:55:00+00:00")
    clusters = cluster_news_items([a, b])
    assert a.cluster_id == b.cluster_id


def test_different_hour_does_not_cluster():
    a = _item("finnhub", "https://x.com/a", "Apple beats Q4 earnings", "2026-01-01T10:00:00+00:00")
    b = _item("tiingo", "https://y.com/b", "Apple beats Q4 earnings", "2026-01-01T11:30:00+00:00")
    cluster_news_items([a, b])
    assert a.cluster_id != b.cluster_id


def test_different_title_does_not_cluster():
    a = _item("finnhub", "https://x.com/a", "Apple beats earnings", "2026-01-01T10:00:00+00:00")
    b = _item("tiingo", "https://y.com/b", "Microsoft hires CFO", "2026-01-01T10:00:00+00:00")
    cluster_news_items([a, b])
    assert a.cluster_id != b.cluster_id


def test_cluster_id_is_stable_across_calls():
    a = _item("finnhub", "https://x.com/a", "Apple beats Q4", "2026-01-01T10:00:00+00:00")
    cluster_news_items([a])
    first = a.cluster_id
    cluster_news_items([a])
    assert a.cluster_id == first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_news_dedup.py -v`
Expected: 6 FAILs ("No module named 'src.analysis.news_dedup'").

- [ ] **Step 3: Implement dedup**

Create `src/analysis/news_dedup.py`:

```python
"""Pure clustering of NewsItems across sources.

Cluster key strategy:
  1. URL is the strongest signal — same URL is always the same article.
  2. Fallback: normalized-title + hour-bucket. Catches the case where two
     sources publish their own URL for a wire story (Reuters via Finnhub
     and via Tiingo, same headline, within an hour).

Pure: takes a list of NewsItems, sets cluster_id on each, returns
the cluster → items mapping. No DB access.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime

from src.models.news_item import NewsItem


_PUNCT = re.compile(r"[^a-z0-9\s]")
_WHITESPACE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    t = title.lower()
    t = _PUNCT.sub(" ", t)
    t = _WHITESPACE.sub(" ", t).strip()
    return t


def _hour_bucket(iso_ts: str) -> str:
    dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%dT%H")


def _cluster_key(item: NewsItem) -> str:
    norm = normalize_title(item.title)
    bucket = _hour_bucket(item.published_at)
    raw = f"{norm}|{bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cluster_news_items(items: list[NewsItem]) -> dict[str, list[NewsItem]]:
    """Assign cluster_id to each item; return cluster_id → items.

    Mutates items in place (sets .cluster_id). Returns the grouping.
    """
    # Pass 1: index items by URL so exact-URL duplicates share a cluster id
    # before we try title-bucket clustering.
    url_to_cluster: dict[str, str] = {}
    for item in items:
        if item.url in url_to_cluster:
            item.cluster_id = url_to_cluster[item.url]
            continue
        key = _cluster_key(item)
        url_to_cluster[item.url] = key
        item.cluster_id = key

    # Pass 2: collapse title-bucket collisions
    by_key: dict[str, list[NewsItem]] = defaultdict(list)
    for item in items:
        by_key[item.cluster_id].append(item)

    return dict(by_key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_news_dedup.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/news_dedup.py tests/test_news_dedup.py
git commit -m "feat(analysis): add cross-source news deduplication"
```

---

## Task 8: Importance scoring (pure analysis)

**Files:**
- Create: `src/analysis/news_importance.py`
- Test: `tests/test_news_importance.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_news_importance.py`:

```python
"""Tests for the importance scoring function.

Score = source_authority * recency_decay * cluster_breadth.
Range: 0..1. Higher = more important for the per-ticker feed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.analysis.news_importance import score_importance, SOURCE_AUTHORITY
from src.models.news_item import NewsItem


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _item(source: str, published: str, cluster_size: int = 1) -> tuple[NewsItem, int]:
    return (
        NewsItem(
            source=source,
            source_type="news",
            url=f"https://x/{source}/{published}",
            title="t",
            published_at=published,
            fetched_at=published,
            tickers=["SYN_X"],
        ),
        cluster_size,
    )


def test_score_is_in_unit_range():
    now = datetime.now(timezone.utc)
    item, _ = _item("finnhub", _iso(now))
    s = score_importance(item, cluster_size=1, now=now)
    assert 0.0 <= s <= 1.0


def test_finnhub_outranks_tavily_at_same_time():
    now = datetime.now(timezone.utc)
    a, _ = _item("finnhub", _iso(now))
    b, _ = _item("tavily", _iso(now))
    assert score_importance(a, cluster_size=1, now=now) > score_importance(b, cluster_size=1, now=now)


def test_recent_outranks_old():
    now = datetime.now(timezone.utc)
    recent, _ = _item("finnhub", _iso(now))
    old, _ = _item("finnhub", _iso(now - timedelta(days=14)))
    assert score_importance(recent, cluster_size=1, now=now) > score_importance(old, cluster_size=1, now=now)


def test_more_sources_in_cluster_boosts_score():
    now = datetime.now(timezone.utc)
    item, _ = _item("finnhub", _iso(now))
    solo = score_importance(item, cluster_size=1, now=now)
    multi = score_importance(item, cluster_size=4, now=now)
    assert multi > solo


def test_source_authority_table_covers_all_sources():
    for src in ("finnhub", "tiingo", "yahoo_finance_rss",
                "google_news_rss", "gdelt", "tavily", "exa", "reddit"):
        assert src in SOURCE_AUTHORITY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_news_importance.py -v`
Expected: 5 FAILs.

- [ ] **Step 3: Implement scoring**

Create `src/analysis/news_importance.py`:

```python
"""Importance score for a single NewsItem.

Score = source_authority * recency_decay * cluster_breadth.

Range: 0..1. Used to rank the per-ticker feed; the orchestrator may filter
items below a threshold before showing them to the user or running expensive
LLM-based scoring on the body.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from src.models.news_item import NewsItem


# Hand-tuned authority weights for Phase 1.
# Structured sources (Finnhub) beat general search (Tavily/Exa) because they
# are ticker-tagged and editorially curated. Tiingo's news is wire-style;
# Tavily/Exa pull from the open web with broader noise.
SOURCE_AUTHORITY: dict[str, float] = {
    "finnhub": 0.90,
    "tiingo": 0.85,
    "yahoo_finance_rss": 0.80,    # ticker-tagged, authoritative
    "google_news_rss": 0.65,      # broad aggregator, varied quality
    "gdelt": 0.55,                # global coverage, event-flavored
    "tavily": 0.55,
    "exa": 0.55,
    "reddit": 0.45,               # social hype, noisier — useful for volume / sentiment signal
}

# Recency halflife: importance drops by half every N hours.
_HALFLIFE_HOURS = 24.0


def _recency_decay(published_at: str, now: datetime) -> float:
    try:
        pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    age_hours = max(0.0, (now - pub).total_seconds() / 3600.0)
    return math.exp(-math.log(2) * age_hours / _HALFLIFE_HOURS)


def _cluster_breadth(cluster_size: int) -> float:
    """1.0 for solo, asymptotes toward 1.5 as more sources confirm.

    Capped so a 10-source cluster doesn't dominate a 2-source one wildly.
    """
    if cluster_size <= 1:
        return 1.0
    return min(1.5, 1.0 + 0.15 * math.log2(cluster_size))


def score_importance(
    item: NewsItem,
    *,
    cluster_size: int = 1,
    now: datetime | None = None,
) -> float:
    """Compute 0..1 importance for one news item.

    `cluster_size` is how many distinct sources reported this same story
    (derived from clusters in src.analysis.news_dedup). Default 1 = solo.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    authority = SOURCE_AUTHORITY.get(item.source, 0.4)
    decay = _recency_decay(item.published_at, now)
    breadth = _cluster_breadth(cluster_size)

    raw = authority * decay * breadth
    return max(0.0, min(1.0, raw))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_news_importance.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/news_importance.py tests/test_news_importance.py
git commit -m "feat(analysis): add news importance scoring"
```

---

## Task 9: News storage layer

**Files:**
- Create: `src/data/news_store.py`
- Test: append to `tests/test_news_store.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_news_store.py`:

```python
from datetime import datetime, timezone

from src.data.news_store import save_news_items, get_news_items_for_ticker
from src.models.news_item import NewsItem


def _make(url: str, title: str, *, tickers: list[str], source: str = "finnhub") -> NewsItem:
    return NewsItem(
        source=source,
        source_type="news",
        url=url,
        title=title,
        published_at="2026-01-15T10:00:00+00:00",
        fetched_at=datetime.now(timezone.utc).isoformat(),
        tickers=tickers,
        cluster_id="abc123",
        importance_score=0.7,
    )


def test_save_and_retrieve_news_items():
    init_db()
    a = _make("https://test.example.com/s1", "Synthetic headline 1", tickers=["SYN_A"])
    b = _make("https://test.example.com/s2", "Synthetic headline 2", tickers=["SYN_A", "SYN_B"])
    save_news_items([a, b])
    rows = get_news_items_for_ticker("SYN_A", limit=10)
    titles = [r.title for r in rows]
    assert "Synthetic headline 1" in titles
    assert "Synthetic headline 2" in titles


def test_save_news_items_is_idempotent_on_url():
    init_db()
    a = _make("https://test.example.com/dup", "First", tickers=["SYN_C"])
    save_news_items([a])
    a2 = _make("https://test.example.com/dup", "Second insert same url", tickers=["SYN_C"])
    save_news_items([a2])
    rows = get_news_items_for_ticker("SYN_C", limit=10)
    # Same URL must not duplicate; the first row wins.
    assert len(rows) == 1
    assert rows[0].title == "First"


def test_get_news_items_returns_only_requested_ticker():
    init_db()
    save_news_items([
        _make("https://test.example.com/x1", "About A", tickers=["SYN_D"]),
        _make("https://test.example.com/x2", "About B", tickers=["SYN_E"]),
    ])
    rows = get_news_items_for_ticker("SYN_D", limit=10)
    assert len(rows) == 1
    assert rows[0].title == "About A"


def test_get_news_items_orders_by_published_desc():
    init_db()
    older = NewsItem(
        source="finnhub", source_type="news",
        url="https://test.example.com/old", title="Older",
        published_at="2026-01-01T00:00:00+00:00",
        fetched_at="2026-01-15T00:00:00+00:00",
        tickers=["SYN_F"],
    )
    newer = NewsItem(
        source="finnhub", source_type="news",
        url="https://test.example.com/new", title="Newer",
        published_at="2026-01-10T00:00:00+00:00",
        fetched_at="2026-01-15T00:00:00+00:00",
        tickers=["SYN_F"],
    )
    save_news_items([older, newer])
    rows = get_news_items_for_ticker("SYN_F", limit=10)
    assert rows[0].title == "Newer"
    assert rows[1].title == "Older"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_news_store.py -v`
Expected: 4 new FAILs ("No module named 'src.data.news_store'").

- [ ] **Step 3: Implement the store**

Create `src/data/news_store.py`:

```python
"""SQLite read/write for unified news_items.

This is the ONLY module allowed to read/write news_items + news_ticker_tags
(other than ad-hoc scripts). Tests mutate via this module so the schema
contract stays in one place.
"""
from __future__ import annotations

from src.models.news_item import NewsItem
from src.utils.db import get_connection


def save_news_items(items: list[NewsItem]) -> int:
    """Insert items; rows whose `url` already exists are skipped.

    Returns the count of NEW rows actually written (ignoring duplicates).
    """
    if not items:
        return 0
    written = 0
    conn = get_connection()
    try:
        for item in items:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO news_items
                  (source, source_type, external_id, url, title, summary, body,
                   published_at, fetched_at, author, sentiment_score,
                   importance_score, volume_metric, cluster_id, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.source, item.source_type, item.external_id, item.url,
                    item.title, item.summary, item.body,
                    item.published_at, item.fetched_at, item.author,
                    item.sentiment_score, item.importance_score,
                    item.volume_metric, item.cluster_id, item.raw_json,
                ),
            )
            news_id = cur.lastrowid
            if cur.rowcount == 0:
                # URL already existed — fetch the existing id so we can still
                # ensure ticker tags are present (a later source might add
                # tickers the first source omitted).
                row = conn.execute(
                    "SELECT id FROM news_items WHERE url = ?", (item.url,)
                ).fetchone()
                if row is None:
                    continue
                news_id = row["id"]
            else:
                written += 1
            for ticker in item.tickers:
                conn.execute(
                    "INSERT OR IGNORE INTO news_ticker_tags (news_id, ticker) VALUES (?, ?)",
                    (news_id, ticker.upper()),
                )
        conn.commit()
    finally:
        conn.close()
    return written


def get_news_items_for_ticker(ticker: str, *, limit: int = 25) -> list[NewsItem]:
    """Return the most recent news_items tagged with `ticker`, newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT n.*
            FROM news_items n
            JOIN news_ticker_tags t ON t.news_id = n.id
            WHERE t.ticker = ?
            ORDER BY n.published_at DESC
            LIMIT ?
            """,
            (ticker.upper(), int(limit)),
        ).fetchall()
        items: list[NewsItem] = []
        for row in rows:
            tickers = [
                tr["ticker"]
                for tr in conn.execute(
                    "SELECT ticker FROM news_ticker_tags WHERE news_id = ?",
                    (row["id"],),
                ).fetchall()
            ]
            items.append(NewsItem(
                source=row["source"],
                source_type=row["source_type"],
                external_id=row["external_id"],
                url=row["url"],
                title=row["title"],
                summary=row["summary"],
                body=row["body"],
                published_at=row["published_at"],
                fetched_at=row["fetched_at"],
                author=row["author"],
                sentiment_score=row["sentiment_score"],
                importance_score=row["importance_score"],
                volume_metric=row["volume_metric"],
                cluster_id=row["cluster_id"],
                tickers=tickers,
                raw_json=row["raw_json"],
            ))
        return items
    finally:
        conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_news_store.py -v`
Expected: 7 PASS total.

- [ ] **Step 5: Commit**

```bash
git add src/data/news_store.py tests/test_news_store.py
git commit -m "feat(data): add SQLite store for unified news items"
```

---

## Task 10: Quota tracker — cooldown for Tavily / Exa

Tavily and Exa have monthly quotas (free / low-volume paid tiers). When exhausted, both return HTTP 429 (rate limit) or 402/403 (quota exceeded). Without handling, every per-ticker request keeps hammering both APIs, adding latency and burning what little budget remains.

This task adds a small cache-backed cooldown: once a 429/402/403 is observed, the source is marked exhausted for 4 hours. The orchestrator (Task 11) checks this flag before calling and skips the source if it's on cooldown.

**Files:**
- Create: `src/data/quota_tracker.py`
- Modify: `src/data/news.py` — make `_tavily_search` and `_exa_search` call `mark_exhausted()` on quota signals
- Test: `tests/test_quota_tracker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_quota_tracker.py`:

```python
"""Tests for the source-quota cooldown tracker."""
from __future__ import annotations

import pytest

from src.data.quota_tracker import (
    clear_exhausted,
    is_exhausted,
    mark_exhausted,
)
from src.utils.db import init_db


@pytest.fixture(autouse=True)
def _fresh_quota_state():
    init_db()
    for src in ("tavily", "exa", "test_src"):
        clear_exhausted(src)
    yield
    for src in ("tavily", "exa", "test_src"):
        clear_exhausted(src)


def test_source_starts_not_exhausted():
    assert is_exhausted("test_src") is False


def test_mark_then_is_exhausted_true():
    mark_exhausted("test_src", cooldown_minutes=240)
    assert is_exhausted("test_src") is True


def test_clear_resets_state():
    mark_exhausted("test_src", cooldown_minutes=240)
    clear_exhausted("test_src")
    assert is_exhausted("test_src") is False


def test_cooldown_expires_after_ttl(monkeypatch):
    from datetime import datetime, timedelta
    import src.data.quota_tracker as qt

    real_now = datetime.utcnow()
    mark_exhausted("test_src", cooldown_minutes=1)

    # Fast-forward 2 minutes: cooldown should have expired.
    future = real_now + timedelta(minutes=2)
    monkeypatch.setattr(qt, "_utcnow", lambda: future)
    assert is_exhausted("test_src") is False


def test_different_sources_isolated():
    mark_exhausted("tavily", cooldown_minutes=240)
    assert is_exhausted("tavily") is True
    assert is_exhausted("exa") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_quota_tracker.py -v`
Expected: 5 FAILs ("No module named 'src.data.quota_tracker'").

- [ ] **Step 3: Implement the quota tracker**

Create `src/data/quota_tracker.py`:

```python
"""Source-level quota cooldown.

When a quota-bound API (Tavily, Exa, others later) returns 429/402/403,
the caller invokes `mark_exhausted(source)`. Subsequent `is_exhausted(source)`
returns True until the cooldown elapses. State is held in the `cache` table
so it survives process restarts.

The orchestrator consults this before making a request — saves latency and
the remaining budget while the source is over its limit.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from src.utils.db import cache_delete, cache_get, cache_set


_PREFIX = "quota_exhausted:"
_DEFAULT_COOLDOWN_MINUTES = 240  # 4h — long enough to avoid retry storms,
                                  # short enough to recover when quota resets.


def _utcnow() -> datetime:
    """Indirection seam — patched in tests to simulate elapsed time."""
    return datetime.utcnow()


def mark_exhausted(source: str, *, cooldown_minutes: int = _DEFAULT_COOLDOWN_MINUTES) -> None:
    """Mark `source` as quota-exhausted for `cooldown_minutes`."""
    key = f"{_PREFIX}{source}"
    expires_at = (_utcnow() + timedelta(minutes=cooldown_minutes)).isoformat()
    cache_set(key, {"marked_at": _utcnow().isoformat(), "expires_at": expires_at},
              ttl_minutes=cooldown_minutes)


def is_exhausted(source: str) -> bool:
    """True if `source` was recently marked exhausted and cooldown still applies."""
    key = f"{_PREFIX}{source}"
    payload = cache_get(key)
    if payload is None:
        return False
    expires_at_str = payload.get("expires_at")
    if not expires_at_str:
        return False
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
    except ValueError:
        cache_delete(key)
        return False
    if _utcnow() >= expires_at:
        cache_delete(key)
        return False
    return True


def clear_exhausted(source: str) -> None:
    """Force-clear cooldown — used by tests and manual recovery."""
    cache_delete(f"{_PREFIX}{source}")
```

- [ ] **Step 4: Run the quota-tracker tests**

Run: `pytest tests/test_quota_tracker.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Wire quota detection into NewsProvider**

Modify `src/data/news.py`. At the top of the file, add the import next to the existing imports:

```python
from src.data.quota_tracker import mark_exhausted
```

Then replace the body of `_tavily_search` so the `except` block inspects the HTTP status:

```python
    def _tavily_search(self, query: str, max_results: int = 5) -> list[dict]:
        if not TAVILY_API_KEY:
            return []

        try:
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={"query": query, "api_key": TAVILY_API_KEY, "max_results": max_results},
                timeout=30,
            )
            if resp.status_code in (402, 403, 429):
                mark_exhausted("tavily")
                log_api_call("tavily", f"search/{query[:50]}", "quota_exhausted",
                             f"status={resp.status_code}")
                return []
            resp.raise_for_status()
            raw = resp.json()
            log_api_call("tavily", f"search/{query[:50]}", "success")
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (402, 403, 429):
                mark_exhausted("tavily")
                log_api_call("tavily", f"search/{query[:50]}", "quota_exhausted", str(e))
            else:
                log_api_call("tavily", f"search/{query[:50]}", "error", str(e))
            return []
        except Exception as e:
            log_api_call("tavily", f"search/{query[:50]}", "error", str(e))
            return []

        results: list[dict] = []
        for r in raw.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "source": r.get("url", "").split("/")[2] if r.get("url") else "",
                "published": r.get("published_date", ""),
                "content_snippet": r.get("content", "")[:500],
            })
        return results
```

Apply the same pattern to `_exa_search` — wrap the existing `except Exception as e:` with an explicit `httpx.HTTPStatusError` check and call `mark_exhausted("exa")` on 402/403/429:

```python
    def _exa_search(self, query: str, num_results: int = 5) -> list[dict]:
        if not EXA_API_KEY:
            return []

        try:
            resp = httpx.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": EXA_API_KEY},
                json={
                    "query": query,
                    "type": "auto",
                    "num_results": num_results,
                    "contents": {"highlights": {"max_characters": 4000}},
                },
                timeout=30,
            )
            if resp.status_code in (402, 403, 429):
                mark_exhausted("exa")
                log_api_call("exa", f"search/{query[:50]}", "quota_exhausted",
                             f"status={resp.status_code}")
                return []
            resp.raise_for_status()
            raw = resp.json()
            log_api_call("exa", f"search/{query[:50]}", "success")
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (402, 403, 429):
                mark_exhausted("exa")
                log_api_call("exa", f"search/{query[:50]}", "quota_exhausted", str(e))
            else:
                log_api_call("exa", f"search/{query[:50]}", "error", str(e))
            return []
        except Exception as e:
            log_api_call("exa", f"search/{query[:50]}", "error", str(e))
            return []

        results: list[dict] = []
        for r in raw.get("results", []):
            highlights = r.get("highlights", [])
            snippet = highlights[0] if highlights else r.get("text", "")[:500]
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "source": r.get("url", "").split("/")[2] if r.get("url") else "",
                "published": r.get("publishedDate", ""),
                "content_snippet": snippet[:500] if isinstance(snippet, str) else "",
            })
        return results
```

- [ ] **Step 6: Add an integration test for NewsProvider quota detection**

Append to `tests/test_quota_tracker.py`:

```python
def test_tavily_429_marks_exhausted(monkeypatch):
    """When httpx returns 429, NewsProvider must mark Tavily exhausted."""
    from src.data import news as news_mod

    class FakeResp:
        status_code = 429
        text = "rate limited"
        def json(self): return {}
        def raise_for_status(self): pass

    monkeypatch.setattr(news_mod, "TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(news_mod.httpx, "post", lambda *a, **kw: FakeResp())

    out = news_mod.NewsProvider()._tavily_search("AAPL", max_results=3)
    assert out == []
    assert is_exhausted("tavily") is True


def test_exa_402_marks_exhausted(monkeypatch):
    from src.data import news as news_mod

    class FakeResp:
        status_code = 402
        text = "quota exceeded"
        def json(self): return {}
        def raise_for_status(self): pass

    monkeypatch.setattr(news_mod, "EXA_API_KEY", "fake-key")
    monkeypatch.setattr(news_mod.httpx, "post", lambda *a, **kw: FakeResp())

    out = news_mod.NewsProvider()._exa_search("AAPL", num_results=3)
    assert out == []
    assert is_exhausted("exa") is True


def test_tavily_500_does_not_mark_exhausted(monkeypatch):
    """A non-quota error (500 / connection error) must NOT trigger cooldown."""
    from src.data import news as news_mod

    class FakeResp:
        status_code = 500
        text = "server error"
        def json(self): return {}
        def raise_for_status(self): pass

    monkeypatch.setattr(news_mod, "TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(news_mod.httpx, "post", lambda *a, **kw: FakeResp())
    clear_exhausted("tavily")

    news_mod.NewsProvider()._tavily_search("AAPL", max_results=3)
    assert is_exhausted("tavily") is False
```

- [ ] **Step 7: Run the full quota-tracker suite**

Run: `pytest tests/test_quota_tracker.py -v`
Expected: 8 PASS.

- [ ] **Step 8: Commit**

```bash
git add src/data/quota_tracker.py src/data/news.py tests/test_quota_tracker.py
git commit -m "feat(data): add quota cooldown tracker; wire into Tavily/Exa fetchers"
```

---

## Task 11: Yahoo Finance RSS source + adapter

Yahoo Finance publishes a per-ticker RSS feed at `https://feeds.finance.yahoo.com/rss/2.0/headline?s=<SYMBOL>&region=US&lang=en-US`. No key, no quota, ticker-tagged at the URL level. Free zero-cost primary source.

**Files:**
- Create: `src/data/yahoo_finance_rss.py`
- Create: `src/data/news_adapters/yahoo_finance_adapter.py`
- Test: `tests/test_yahoo_finance_rss.py`

- [ ] **Step 1: Write the failing fetcher + adapter tests**

Create `tests/test_yahoo_finance_rss.py`:

```python
"""Tests for the Yahoo Finance RSS fetcher and its NewsItem adapter."""
from __future__ import annotations

import pytest

from src.data.news_adapters.yahoo_finance_adapter import yahoo_to_news_item


_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Yahoo Finance</title>
<item>
  <title>Apple beats Q4 estimates</title>
  <link>https://finance.yahoo.com/news/apple-beats-q4-2026</link>
  <pubDate>Tue, 14 Jan 2026 10:15:00 +0000</pubDate>
  <description>Apple reported strong iPhone sales...</description>
</item>
<item>
  <title>iPhone supply chain notes</title>
  <link>https://finance.yahoo.com/news/iphone-supply-chain</link>
  <pubDate>Tue, 14 Jan 2026 09:00:00 +0000</pubDate>
  <description>Suppliers ramp production...</description>
</item>
</channel>
</rss>"""


def test_yahoo_fetcher_parses_items(monkeypatch):
    from src.data import yahoo_finance_rss as mod

    class FakeResp:
        text = _SAMPLE_RSS
        status_code = 200
        def raise_for_status(self): pass

    monkeypatch.setattr(mod.httpx, "get", lambda *a, **kw: FakeResp())
    rows = mod.get_yahoo_news("AAPL")
    assert rows is not None and len(rows) == 2
    assert rows[0]["title"] == "Apple beats Q4 estimates"
    assert rows[0]["url"] == "https://finance.yahoo.com/news/apple-beats-q4-2026"
    assert "2026" in rows[0]["pub_date"]


def test_yahoo_fetcher_returns_none_on_http_error(monkeypatch):
    from src.data import yahoo_finance_rss as mod
    import httpx as real_httpx

    def boom(*a, **kw):
        raise real_httpx.ConnectError("nope")

    monkeypatch.setattr(mod.httpx, "get", boom)
    assert mod.get_yahoo_news("AAPL") is None


def test_yahoo_adapter_basic():
    row = {
        "title": "Apple beats Q4 estimates",
        "url": "https://finance.yahoo.com/news/apple-beats-q4-2026",
        "pub_date": "Tue, 14 Jan 2026 10:15:00 +0000",
        "description": "Apple reported strong iPhone sales...",
    }
    item = yahoo_to_news_item(row, symbol="AAPL")
    assert item is not None
    assert item.source == "yahoo_finance_rss"
    assert "AAPL" in item.tickers
    assert item.title == "Apple beats Q4 estimates"
    assert item.published_at.startswith("2026-01-14T10:15")


def test_yahoo_adapter_skips_when_no_url():
    row = {"title": "x", "url": "", "pub_date": "Tue, 14 Jan 2026 10:15:00 +0000"}
    assert yahoo_to_news_item(row, symbol="AAPL") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_yahoo_finance_rss.py -v`
Expected: 4 FAILs (no such modules).

- [ ] **Step 3: Implement the fetcher**

Create `src/data/yahoo_finance_rss.py`:

```python
"""Yahoo Finance per-ticker RSS feed (no key, no quota).

Endpoint: https://feeds.finance.yahoo.com/rss/2.0/headline?s=<SYMBOL>
Returns RSS XML with <item> elements: title, link, pubDate, description.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from src.utils.db import cache_get, cache_set, log_api_call


_BASE_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline"
_CACHE_TTL_MINUTES = 30


def get_yahoo_news(symbol: str, *, limit: int = 25) -> list[dict] | None:
    """Fetch Yahoo Finance RSS for `symbol`. Returns raw rows or None on failure.

    Each row: {title, url, pub_date, description}.
    """
    sym = symbol.upper()
    key = f"yahoo_rss:{sym}:{limit}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")

    params = {"s": sym, "region": "US", "lang": "en-US"}
    try:
        resp = httpx.get(_BASE_URL, params=params, timeout=15, follow_redirects=True,
                         headers={"User-Agent": "TradingApp/1.0"})
        resp.raise_for_status()
        log_api_call("yahoo_finance_rss", f"headline/{sym}", "success")
    except Exception as e:
        log_api_call("yahoo_finance_rss", f"headline/{sym}", "error", str(e))
        return None

    rows: list[dict] = []
    try:
        root = ET.fromstring(resp.text)
        for item in root.findall(".//item")[:limit]:
            rows.append({
                "title": (item.findtext("title") or "").strip(),
                "url": (item.findtext("link") or "").strip(),
                "pub_date": (item.findtext("pubDate") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
            })
    except ET.ParseError as e:
        log_api_call("yahoo_finance_rss", f"headline/{sym}", "parse_error", str(e))
        return None

    cache_set(key, {"rows": rows}, ttl_minutes=_CACHE_TTL_MINUTES)
    return rows
```

- [ ] **Step 4: Implement the adapter**

Create `src/data/news_adapters/yahoo_finance_adapter.py`:

```python
"""Yahoo Finance RSS row → NewsItem.

Source row shape (from src.data.yahoo_finance_rss.get_yahoo_news):
    {"title": str, "url": str,
     "pub_date": str (RFC 822, e.g. 'Tue, 14 Jan 2026 10:15:00 +0000'),
     "description": str}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from src.models.news_item import NewsItem


def _parse_rfc822(s: str) -> str | None:
    """Convert RFC 822 datetime ('Tue, 14 Jan 2026 10:15:00 +0000') to ISO 8601 UTC."""
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def yahoo_to_news_item(row: dict, *, symbol: str) -> NewsItem | None:
    url = (row.get("url") or "").strip()
    title = (row.get("title") or "").strip()
    if not url or not title:
        return None

    published = _parse_rfc822(row.get("pub_date") or "")
    if published is None:
        return None

    return NewsItem(
        source="yahoo_finance_rss",
        source_type="news",
        url=url,
        title=title,
        summary=(row.get("description") or "").strip() or None,
        published_at=published,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        author="Yahoo Finance",
        tickers=[symbol.upper()],
        raw_json=json.dumps(row, default=str),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_yahoo_finance_rss.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/data/yahoo_finance_rss.py src/data/news_adapters/yahoo_finance_adapter.py tests/test_yahoo_finance_rss.py
git commit -m "feat(data): add Yahoo Finance RSS fetcher + adapter (no-key primary source)"
```

---

## Task 12: Google News RSS source + adapter

Google News exposes a search RSS at `https://news.google.com/rss/search?q=<QUERY>&hl=en-US&gl=US&ceid=US:en`. Broadest aggregator; closest free replacement for Tavily's general-web search.

**Files:**
- Create: `src/data/google_news_rss.py`
- Create: `src/data/news_adapters/google_news_adapter.py`
- Test: `tests/test_google_news_rss.py`

- [ ] **Step 1: Write the failing fetcher + adapter tests**

Create `tests/test_google_news_rss.py`:

```python
"""Tests for the Google News RSS fetcher and its NewsItem adapter."""
from __future__ import annotations

import pytest

from src.data.news_adapters.google_news_adapter import google_to_news_item


_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
<item>
  <title>Apple beats Q4 estimates - Reuters</title>
  <link>https://news.google.com/articles/redirect-url-apple-q4</link>
  <pubDate>Tue, 14 Jan 2026 10:15:00 GMT</pubDate>
  <source url="https://reuters.com">Reuters</source>
  <description>Apple reported strong iPhone sales</description>
</item>
<item>
  <title>iPhone supply chain ramps - Bloomberg</title>
  <link>https://news.google.com/articles/redirect-supply</link>
  <pubDate>Tue, 14 Jan 2026 09:00:00 GMT</pubDate>
  <source url="https://bloomberg.com">Bloomberg</source>
  <description>Suppliers note demand</description>
</item>
</channel>
</rss>"""


def test_google_fetcher_parses_items(monkeypatch):
    from src.data import google_news_rss as mod

    class FakeResp:
        text = _SAMPLE_RSS
        status_code = 200
        def raise_for_status(self): pass

    monkeypatch.setattr(mod.httpx, "get", lambda *a, **kw: FakeResp())
    rows = mod.get_google_news("AAPL stock")
    assert rows is not None and len(rows) == 2
    assert rows[0]["title"].startswith("Apple beats")
    assert rows[0]["source"] == "Reuters"
    assert "GMT" in rows[0]["pub_date"]


def test_google_fetcher_returns_none_on_failure(monkeypatch):
    from src.data import google_news_rss as mod
    import httpx as real_httpx

    def boom(*a, **kw):
        raise real_httpx.ConnectError("nope")

    monkeypatch.setattr(mod.httpx, "get", boom)
    assert mod.get_google_news("AAPL") is None


def test_google_adapter_basic():
    row = {
        "title": "Apple beats Q4 estimates - Reuters",
        "url": "https://news.google.com/articles/redirect-url-apple-q4",
        "pub_date": "Tue, 14 Jan 2026 10:15:00 GMT",
        "source": "Reuters",
        "description": "Apple reported strong iPhone sales",
    }
    item = google_to_news_item(row, symbol="AAPL")
    assert item is not None
    assert item.source == "google_news_rss"
    assert "AAPL" in item.tickers
    assert item.author == "Reuters"
    assert item.published_at.startswith("2026-01-14T10:15")


def test_google_adapter_skips_when_no_url():
    row = {"title": "x", "url": "", "pub_date": "Tue, 14 Jan 2026 10:15:00 GMT", "source": "X"}
    assert google_to_news_item(row, symbol="AAPL") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_google_news_rss.py -v`
Expected: 4 FAILs.

- [ ] **Step 3: Implement the fetcher**

Create `src/data/google_news_rss.py`:

```python
"""Google News RSS search (no key, no quota).

Endpoint: https://news.google.com/rss/search?q=<QUERY>&hl=en-US&gl=US&ceid=US:en
Returns RSS XML; each <item> has title, link, pubDate, source, description.

Used as a broad-aggregator primary source — closest free replacement for Tavily's
general-web search.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from src.utils.db import cache_get, cache_set, log_api_call


_BASE_URL = "https://news.google.com/rss/search"
_CACHE_TTL_MINUTES = 30


def get_google_news(query: str, *, limit: int = 25) -> list[dict] | None:
    """Fetch Google News RSS for `query`. Returns raw rows or None on failure.

    Each row: {title, url, pub_date, source, description}.
    """
    key = f"google_news_rss:{query}:{limit}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")

    params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    try:
        resp = httpx.get(_BASE_URL, params=params, timeout=15, follow_redirects=True,
                         headers={"User-Agent": "TradingApp/1.0"})
        resp.raise_for_status()
        log_api_call("google_news_rss", f"search/{query[:50]}", "success")
    except Exception as e:
        log_api_call("google_news_rss", f"search/{query[:50]}", "error", str(e))
        return None

    rows: list[dict] = []
    try:
        root = ET.fromstring(resp.text)
        for item in root.findall(".//item")[:limit]:
            rows.append({
                "title": (item.findtext("title") or "").strip(),
                "url": (item.findtext("link") or "").strip(),
                "pub_date": (item.findtext("pubDate") or "").strip(),
                "source": (item.findtext("source") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
            })
    except ET.ParseError as e:
        log_api_call("google_news_rss", f"search/{query[:50]}", "parse_error", str(e))
        return None

    cache_set(key, {"rows": rows}, ttl_minutes=_CACHE_TTL_MINUTES)
    return rows
```

- [ ] **Step 4: Implement the adapter**

Create `src/data/news_adapters/google_news_adapter.py`:

```python
"""Google News RSS row → NewsItem.

Source row shape (from src.data.google_news_rss.get_google_news):
    {"title": str, "url": str,
     "pub_date": str (RFC 822),
     "source": str (publisher name),
     "description": str}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from src.models.news_item import NewsItem


def _parse_rfc822(s: str) -> str | None:
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def google_to_news_item(row: dict, *, symbol: str) -> NewsItem | None:
    url = (row.get("url") or "").strip()
    title = (row.get("title") or "").strip()
    if not url or not title:
        return None

    published = _parse_rfc822(row.get("pub_date") or "")
    if published is None:
        return None

    return NewsItem(
        source="google_news_rss",
        source_type="news",
        url=url,
        title=title,
        summary=(row.get("description") or "").strip() or None,
        published_at=published,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        author=(row.get("source") or "").strip() or None,
        tickers=[symbol.upper()],
        raw_json=json.dumps(row, default=str),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_google_news_rss.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/data/google_news_rss.py src/data/news_adapters/google_news_adapter.py tests/test_google_news_rss.py
git commit -m "feat(data): add Google News RSS fetcher + adapter (no-key primary source)"
```

---

## Task 13: GDELT DOC 2.0 source + adapter

GDELT indexes global news every 15 minutes. The DOC 2.0 API returns JSON: free, no key, generous limits. Endpoint: `https://api.gdeltproject.org/api/v2/doc/doc?query=<QUERY>&mode=ArtList&format=json&maxrecords=50&sort=DateDesc`.

**Files:**
- Create: `src/data/gdelt_doc.py`
- Create: `src/data/news_adapters/gdelt_adapter.py`
- Test: `tests/test_gdelt_doc.py`

- [ ] **Step 1: Write the failing fetcher + adapter tests**

Create `tests/test_gdelt_doc.py`:

```python
"""Tests for the GDELT DOC 2.0 fetcher and its NewsItem adapter."""
from __future__ import annotations

import pytest

from src.data.news_adapters.gdelt_adapter import gdelt_to_news_item


_SAMPLE_JSON = {
    "articles": [
        {
            "url": "https://reuters.example.com/apple-q4-2026",
            "url_mobile": "",
            "title": "Apple beats Q4 estimates",
            "seendate": "20260114T101500Z",
            "socialimage": "",
            "domain": "reuters.example.com",
            "language": "English",
            "sourcecountry": "United States",
        },
        {
            "url": "https://bloomberg.example.com/iphone-supply",
            "title": "iPhone supply chain ramps",
            "seendate": "20260114T090000Z",
            "domain": "bloomberg.example.com",
            "language": "English",
            "sourcecountry": "United States",
        },
    ]
}


def test_gdelt_fetcher_parses_articles(monkeypatch):
    from src.data import gdelt_doc as mod

    class FakeResp:
        status_code = 200
        def json(self): return _SAMPLE_JSON
        def raise_for_status(self): pass
        @property
        def text(self): return "ok"

    monkeypatch.setattr(mod.httpx, "get", lambda *a, **kw: FakeResp())
    rows = mod.get_gdelt_articles("AAPL")
    assert rows is not None and len(rows) == 2
    assert rows[0]["url"].startswith("https://reuters")
    assert rows[0]["title"] == "Apple beats Q4 estimates"
    assert rows[0]["seendate"] == "20260114T101500Z"


def test_gdelt_fetcher_returns_none_on_failure(monkeypatch):
    from src.data import gdelt_doc as mod
    import httpx as real_httpx

    def boom(*a, **kw):
        raise real_httpx.ConnectError("nope")

    monkeypatch.setattr(mod.httpx, "get", boom)
    assert mod.get_gdelt_articles("AAPL") is None


def test_gdelt_fetcher_handles_empty_articles(monkeypatch):
    from src.data import gdelt_doc as mod

    class FakeResp:
        status_code = 200
        def json(self): return {"articles": []}
        def raise_for_status(self): pass
        text = ""

    monkeypatch.setattr(mod.httpx, "get", lambda *a, **kw: FakeResp())
    rows = mod.get_gdelt_articles("XYZNOMATCH")
    assert rows == []


def test_gdelt_adapter_basic():
    row = {
        "url": "https://reuters.example.com/apple-q4-2026",
        "title": "Apple beats Q4 estimates",
        "seendate": "20260114T101500Z",
        "domain": "reuters.example.com",
        "sourcecountry": "United States",
    }
    item = gdelt_to_news_item(row, symbol="AAPL")
    assert item is not None
    assert item.source == "gdelt"
    assert "AAPL" in item.tickers
    assert item.author == "reuters.example.com"
    assert item.published_at.startswith("2026-01-14T10:15")


def test_gdelt_adapter_skips_when_no_url():
    row = {"title": "x", "url": "", "seendate": "20260114T101500Z"}
    assert gdelt_to_news_item(row, symbol="AAPL") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gdelt_doc.py -v`
Expected: 5 FAILs.

- [ ] **Step 3: Implement the fetcher**

Create `src/data/gdelt_doc.py`:

```python
"""GDELT DOC 2.0 article search (no key, no quota).

Endpoint: https://api.gdeltproject.org/api/v2/doc/doc
Params: query=<str>&mode=ArtList&format=json&maxrecords=N&sort=DateDesc

Returns {"articles": [{url, title, seendate, domain, language, sourcecountry}, ...]}.
seendate format is GDELT's compact form: 'YYYYMMDDTHHMMSSZ'.
"""
from __future__ import annotations

import httpx

from src.utils.db import cache_get, cache_set, log_api_call


_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_CACHE_TTL_MINUTES = 30


def get_gdelt_articles(query: str, *, limit: int = 50) -> list[dict] | None:
    """Fetch GDELT DOC articles for `query`. Returns raw rows or None on failure.

    Returns [] if the query has no hits (distinguishable from None / error).
    """
    key = f"gdelt_doc:{query}:{limit}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")

    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(limit),
        "sort": "DateDesc",
    }
    try:
        resp = httpx.get(_BASE_URL, params=params, timeout=15, follow_redirects=True,
                         headers={"User-Agent": "TradingApp/1.0"})
        resp.raise_for_status()
        data = resp.json()
        log_api_call("gdelt", f"doc/{query[:50]}", "success")
    except Exception as e:
        log_api_call("gdelt", f"doc/{query[:50]}", "error", str(e))
        return None

    if not isinstance(data, dict):
        return None
    rows = data.get("articles") or []
    if not isinstance(rows, list):
        return None
    cache_set(key, {"rows": rows}, ttl_minutes=_CACHE_TTL_MINUTES)
    return rows
```

- [ ] **Step 4: Implement the adapter**

Create `src/data/news_adapters/gdelt_adapter.py`:

```python
"""GDELT DOC 2.0 article row → NewsItem.

Source row shape:
    {"url": str, "title": str,
     "seendate": str (compact, e.g. '20260114T101500Z'),
     "domain": str, "language": str, "sourcecountry": str}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.models.news_item import NewsItem


def _parse_gdelt_date(s: str) -> str | None:
    """'20260114T101500Z' → ISO 8601 UTC string."""
    if not s or len(s) < 15:
        return None
    try:
        dt = datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return None


def gdelt_to_news_item(row: dict, *, symbol: str) -> NewsItem | None:
    url = (row.get("url") or "").strip()
    title = (row.get("title") or "").strip()
    if not url or not title:
        return None

    published = _parse_gdelt_date(row.get("seendate") or "")
    if published is None:
        return None

    return NewsItem(
        source="gdelt",
        source_type="news",
        url=url,
        title=title,
        published_at=published,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        author=(row.get("domain") or "").strip() or None,
        tickers=[symbol.upper()],
        topics=[t for t in [row.get("sourcecountry")] if t],
        raw_json=json.dumps(row, default=str),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_gdelt_doc.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/data/gdelt_doc.py src/data/news_adapters/gdelt_adapter.py tests/test_gdelt_doc.py
git commit -m "feat(data): add GDELT DOC 2.0 fetcher + adapter (no-key primary source)"
```

---

## Task 14: Reddit search source + adapter

Reddit's public JSON endpoints (`.json` suffix on any URL) return search results without OAuth — only a `User-Agent` header is required. We query three financial subreddits (`wallstreetbets`, `stocks`, `investing`) per ticker, tagging results with `source_type="social"` and storing upvote counts in `volume_metric` so social signal is distinguishable from financial news downstream.

**Files:**
- Create: `src/data/reddit_search.py`
- Create: `src/data/news_adapters/reddit_adapter.py`
- Test: `tests/test_reddit_search.py`

- [ ] **Step 1: Write the failing fetcher + adapter tests**

Create `tests/test_reddit_search.py`:

```python
"""Tests for the Reddit ticker-search fetcher and its NewsItem adapter."""
from __future__ import annotations

import pytest

from src.data.news_adapters.reddit_adapter import reddit_to_news_item


_SAMPLE_JSON = {
    "data": {
        "children": [
            {"data": {
                "id": "abc123",
                "title": "AAPL DD - long thesis Q4",
                "selftext": "Apple is positioned for...",
                "permalink": "/r/wallstreetbets/comments/abc123/aapl_dd/",
                "url": "https://www.reddit.com/r/wallstreetbets/comments/abc123/aapl_dd/",
                "created_utc": 1736899200,  # 2025-01-15T00:00:00Z
                "author": "user1",
                "subreddit": "wallstreetbets",
                "ups": 412, "num_comments": 87, "score": 412,
            }},
            {"data": {
                "id": "def456",
                "title": "AAPL earnings preview",
                "selftext": "",
                "permalink": "/r/stocks/comments/def456/aapl_earnings/",
                "url": "https://www.reddit.com/r/stocks/comments/def456/aapl_earnings/",
                "created_utc": 1736902800,
                "author": "user2",
                "subreddit": "stocks",
                "ups": 88, "num_comments": 21, "score": 88,
            }},
        ]
    }
}


def test_reddit_fetcher_parses_posts(monkeypatch):
    from src.data import reddit_search as mod

    class FakeResp:
        status_code = 200
        def json(self): return _SAMPLE_JSON
        def raise_for_status(self): pass
        text = "ok"

    monkeypatch.setattr(mod.httpx, "get", lambda *a, **kw: FakeResp())
    rows = mod.get_reddit_posts("AAPL")
    assert rows is not None
    # 3 subreddits × 2 posts each (the stub returns the same payload for each)
    assert len(rows) == 6
    titles = {r["title"] for r in rows}
    assert "AAPL DD - long thesis Q4" in titles


def test_reddit_fetcher_returns_none_when_all_subreddits_fail(monkeypatch):
    from src.data import reddit_search as mod
    import httpx as real_httpx

    def boom(*a, **kw):
        raise real_httpx.ConnectError("nope")

    monkeypatch.setattr(mod.httpx, "get", boom)
    assert mod.get_reddit_posts("AAPL") is None


def test_reddit_fetcher_partial_success_when_one_sub_429(monkeypatch):
    """If one subreddit returns 429, others can still succeed.

    The fetcher must not raise and must return whatever it got.
    """
    from src.data import reddit_search as mod

    calls = {"n": 0}

    class FakeOk:
        status_code = 200
        def json(self): return _SAMPLE_JSON
        def raise_for_status(self): pass
        text = "ok"

    class Fake429:
        status_code = 429
        def json(self): return {}
        def raise_for_status(self): pass
        text = "rate limited"

    def maybe_429(*a, **kw):
        calls["n"] += 1
        return Fake429() if calls["n"] == 1 else FakeOk()

    monkeypatch.setattr(mod.httpx, "get", maybe_429)
    rows = mod.get_reddit_posts("AAPL")
    # 1 sub returned 429 (skipped), 2 subs returned _SAMPLE_JSON (2 posts each)
    assert rows is not None
    assert len(rows) == 4


def test_reddit_adapter_basic():
    row = {
        "id": "abc123",
        "title": "AAPL DD - long thesis Q4",
        "selftext": "Apple is positioned for...",
        "url": "https://www.reddit.com/r/wallstreetbets/comments/abc123/aapl_dd/",
        "created_utc": 1736899200,
        "author": "user1",
        "subreddit": "wallstreetbets",
        "ups": 412, "num_comments": 87, "score": 412,
    }
    item = reddit_to_news_item(row, symbol="AAPL")
    assert item is not None
    assert item.source == "reddit"
    assert item.source_type == "social"
    assert "AAPL" in item.tickers
    assert item.volume_metric == 412.0
    assert item.author == "user1"
    assert "r/wallstreetbets" in item.topics
    assert item.published_at.startswith("2025-01-15T")


def test_reddit_adapter_skips_when_no_url():
    row = {"id": "x", "title": "x", "url": "", "created_utc": 1736899200}
    assert reddit_to_news_item(row, symbol="AAPL") is None


def test_reddit_adapter_skips_when_no_created_utc():
    row = {"id": "x", "title": "x",
           "url": "https://reddit.com/r/x/comments/x/",
           "created_utc": None}
    assert reddit_to_news_item(row, symbol="AAPL") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_reddit_search.py -v`
Expected: 6 FAILs (no such modules).

- [ ] **Step 3: Implement the fetcher**

Create `src/data/reddit_search.py`:

```python
"""Reddit ticker-search across financial subreddits (no key, no OAuth).

Uses Reddit's public JSON endpoints (`.json` suffix on any URL). Reddit
mandates a unique User-Agent — calls without one return HTTP 429.

Returns posts from three subreddits: r/wallstreetbets, r/stocks, r/investing.
Each post has upvote score in `score`/`ups` which the adapter maps to
NewsItem.volume_metric so hype level is downstream-queryable.
"""
from __future__ import annotations

import httpx

from src.utils.db import cache_get, cache_set, log_api_call


_SUBREDDITS: tuple[str, ...] = ("wallstreetbets", "stocks", "investing")
_CACHE_TTL_MINUTES = 30
_USER_AGENT = "TradingApp/1.0 (research; per-stock ticker search)"


def get_reddit_posts(symbol: str, *, limit_per_sub: int = 15) -> list[dict] | None:
    """Search the financial subreddits for `symbol` mentions.

    Returns:
      - list of post dicts (possibly empty) when at least one subreddit succeeded
      - None when every subreddit call failed (network down, all 429s, etc.)
    """
    sym = symbol.upper()
    key = f"reddit:{sym}:{limit_per_sub}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")

    rows: list[dict] = []
    any_success = False
    for sub in _SUBREDDITS:
        url = f"https://www.reddit.com/r/{sub}/search.json"
        params = {
            "q": sym,
            "restrict_sr": "on",
            "sort": "new",
            "limit": str(limit_per_sub),
        }
        try:
            resp = httpx.get(
                url, params=params, timeout=15,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            )
            if resp.status_code == 429:
                log_api_call("reddit", f"search/{sub}/{sym}", "rate_limited",
                             "subreddit skipped this cycle")
                continue
            resp.raise_for_status()
            data = resp.json()
            any_success = True
            log_api_call("reddit", f"search/{sub}/{sym}", "success")
        except Exception as e:
            log_api_call("reddit", f"search/{sub}/{sym}", "error", str(e))
            continue

        children = (data.get("data") or {}).get("children") or []
        for child in children:
            d = child.get("data") or {}
            permalink = (d.get("permalink") or "").strip()
            post_url = (
                f"https://www.reddit.com{permalink}"
                if permalink and permalink.startswith("/")
                else (d.get("url") or "")
            )
            rows.append({
                "id": d.get("id"),
                "title": d.get("title", ""),
                "selftext": d.get("selftext", ""),
                "url": post_url,
                "created_utc": d.get("created_utc"),
                "author": d.get("author"),
                "subreddit": sub,
                "ups": d.get("ups"),
                "num_comments": d.get("num_comments"),
                "score": d.get("score"),
            })

    if not any_success:
        return None

    cache_set(key, {"rows": rows}, ttl_minutes=_CACHE_TTL_MINUTES)
    return rows
```

- [ ] **Step 4: Implement the adapter**

Create `src/data/news_adapters/reddit_adapter.py`:

```python
"""Reddit post → NewsItem.

Output items carry source_type="social" so downstream code can treat them
differently from news (e.g. the frontend can label them, the dedup keeps
them in their own clusters when titles diverge).

Upvote count goes into volume_metric — Phase 2 will use it for hype scoring.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.models.news_item import NewsItem


def reddit_to_news_item(row: dict, *, symbol: str) -> NewsItem | None:
    url = (row.get("url") or "").strip()
    title = (row.get("title") or "").strip()
    created = row.get("created_utc")
    if not url or not title or created is None:
        return None

    try:
        published = datetime.fromtimestamp(int(created), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None

    raw_score = row.get("score")
    if raw_score is None:
        raw_score = row.get("ups")
    try:
        volume = float(raw_score) if raw_score is not None else None
    except (TypeError, ValueError):
        volume = None

    subreddit = row.get("subreddit")
    topics = [f"r/{subreddit}"] if subreddit else []

    summary_text = (row.get("selftext") or "").strip()
    summary = summary_text[:500] or None

    return NewsItem(
        source="reddit",
        source_type="social",
        external_id=str(row["id"]) if row.get("id") else None,
        url=url,
        title=title,
        summary=summary,
        published_at=published,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        author=(row.get("author") or None),
        tickers=[symbol.upper()],
        topics=topics,
        volume_metric=volume,
        raw_json=json.dumps(row, default=str),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_reddit_search.py -v`
Expected: 6 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/data/reddit_search.py src/data/news_adapters/reddit_adapter.py tests/test_reddit_search.py
git commit -m "feat(data): add Reddit search fetcher + adapter (no-key social source)"
```

---

## Task 15: Orchestrator — fetch + normalize + dedup + score + save

**Files:**
- Create: `src/reports/news_feed.py`
- Test: `tests/test_news_feed_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_news_feed_orchestrator.py`:

```python
"""Orchestrator integration tests.

Stubs replace the four data fetchers; the orchestrator should fan out,
normalize via adapters, dedup, score, and persist to the temp DB.
"""
from __future__ import annotations

import pytest

from src.reports.news_feed import fetch_ticker_news
from src.utils.db import init_db


@pytest.fixture
def stub_sources(monkeypatch):
    """Replace all seven upstream fetchers with deterministic stubs."""
    init_db()

    def fake_finnhub(symbol: str, days: int = 30):
        return [{
            "id": 1, "datetime": 1736899200,  # 2025-01-15T00:00:00Z
            "headline": "SYN_X beats earnings",
            "summary": "Synthetic earnings beat",
            "url": "https://finnhub.example.com/syn_x-q4",
            "source": "Reuters", "category": "company", "related": symbol,
        }]

    def fake_tiingo(symbol=None, **kwargs):
        return [{
            "id": 2, "title": "SYN_X beats earnings",
            "description": "Same story, different URL",
            "url": "https://tiingo.example.com/syn_x-q4",
            "publishedDate": "2025-01-15T00:30:00Z",
            "source": "tiingo-bloomberg",
            "tickers": ["syn_x"], "tags": ["earnings"],
        }]

    def fake_yahoo(symbol: str, *, limit: int = 25):
        return [{
            "title": "SYN_X analyst raises target",
            "url": "https://yahoo.example.com/syn_x-target",
            "pub_date": "Tue, 14 Jan 2025 12:00:00 GMT",
            "description": "Yahoo says analyst raised target",
        }]

    def fake_google(query: str, *, limit: int = 25):
        return [{
            "title": "SYN_X factory expansion",
            "url": "https://google.example.com/syn_x-factory",
            "pub_date": "Tue, 14 Jan 2025 13:00:00 GMT",
            "source": "Bloomberg",
            "description": "Google News story",
        }]

    def fake_gdelt(query: str, *, limit: int = 50):
        return [{
            "title": "SYN_X global event coverage",
            "url": "https://gdelt.example.com/syn_x-event",
            "seendate": "20250114T140000Z",
            "domain": "gdelt-coverage.example.com",
            "sourcecountry": "United States",
        }]

    def fake_reddit(symbol: str, *, limit_per_sub: int = 15):
        return [{
            "id": "rdt1",
            "title": "SYN_X DD - bullish thesis",
            "selftext": "Loaded up...",
            "url": "https://www.reddit.com/r/wallstreetbets/comments/rdt1/syn_x_dd/",
            "created_utc": 1736899200,
            "author": "anon",
            "subreddit": "wallstreetbets",
            "ups": 250, "num_comments": 42, "score": 250,
        }]

    class FakeProvider:
        def search_stock_news(self, symbol, days=7):
            return [
                {"title": "SYN_X analyst raises target",
                 "url": "https://tavily.example.com/syn_x-target",
                 "source": "marketbeat.example.com",
                 "published": "2025-01-14T12:00:00Z",
                 "content_snippet": "Analyst raised target..."},
            ]

    monkeypatch.setattr("src.reports.news_feed._fetch_finnhub", fake_finnhub)
    monkeypatch.setattr("src.reports.news_feed._fetch_tiingo", fake_tiingo)
    monkeypatch.setattr("src.reports.news_feed._fetch_yahoo", fake_yahoo)
    monkeypatch.setattr("src.reports.news_feed._fetch_google", fake_google)
    monkeypatch.setattr("src.reports.news_feed._fetch_gdelt", fake_gdelt)
    monkeypatch.setattr("src.reports.news_feed._fetch_reddit", fake_reddit)
    monkeypatch.setattr("src.reports.news_feed.NewsProvider", lambda: FakeProvider())
    return None


def test_orchestrator_returns_items(stub_sources):
    items = fetch_ticker_news("SYN_X")
    assert len(items) >= 2
    # Every item must be tagged with SYN_X
    for it in items:
        assert "SYN_X" in it.tickers


def test_orchestrator_dedups_finnhub_and_tiingo_same_story(stub_sources):
    items = fetch_ticker_news("SYN_X")
    cluster_ids = {it.cluster_id for it in items if "beats earnings" in it.title.lower()}
    # Finnhub + Tiingo "beats earnings" stories share a cluster_id even
    # though their URLs differ — same title + same hour bucket.
    assert len(cluster_ids) == 1


def test_orchestrator_assigns_importance_score(stub_sources):
    items = fetch_ticker_news("SYN_X")
    for it in items:
        assert it.importance_score is not None
        assert 0.0 <= it.importance_score <= 1.0


def test_orchestrator_persists_to_db(stub_sources):
    from src.data.news_store import get_news_items_for_ticker
    fetch_ticker_news("SYN_X")
    stored = get_news_items_for_ticker("SYN_X", limit=10)
    assert len(stored) >= 2


def test_orchestrator_ranks_by_importance_then_recency(stub_sources):
    items = fetch_ticker_news("SYN_X")
    scores = [it.importance_score for it in items]
    assert scores == sorted(scores, reverse=True)


def test_orchestrator_skips_provider_when_both_quotas_exhausted(stub_sources, monkeypatch):
    """When Tavily AND Exa are on cooldown, NewsProvider must NOT be called.

    Finnhub + Tiingo continue to work; the feed shrinks but the request still succeeds.
    """
    from src.data.quota_tracker import mark_exhausted, clear_exhausted

    called = {"provider": 0}

    class TrackingProvider:
        def search_stock_news(self, symbol, days=7):
            called["provider"] += 1
            return [{"title": "should not appear", "url": "https://x/no",
                     "source": "x", "published": "2025-01-15T12:00:00Z",
                     "content_snippet": ""}]

    monkeypatch.setattr("src.reports.news_feed.NewsProvider", lambda: TrackingProvider())
    mark_exhausted("tavily", cooldown_minutes=240)
    mark_exhausted("exa", cooldown_minutes=240)
    try:
        items = fetch_ticker_news("SYN_X")
        assert called["provider"] == 0
        # Finnhub + Tiingo still populate the feed
        assert len(items) >= 2
        # No item from the (skipped) provider snuck in
        assert all(it.url != "https://x/no" for it in items)
    finally:
        clear_exhausted("tavily")
        clear_exhausted("exa")


def test_orchestrator_calls_provider_when_only_one_quota_exhausted(stub_sources, monkeypatch):
    """If Tavily is exhausted but Exa is fine (or vice versa), still call NewsProvider —
    its internal _tavily_search will short-circuit on the exhausted source."""
    from src.data.quota_tracker import mark_exhausted, clear_exhausted

    called = {"provider": 0}

    class TrackingProvider:
        def search_stock_news(self, symbol, days=7):
            called["provider"] += 1
            return []

    monkeypatch.setattr("src.reports.news_feed.NewsProvider", lambda: TrackingProvider())
    mark_exhausted("tavily", cooldown_minutes=240)
    clear_exhausted("exa")
    try:
        fetch_ticker_news("SYN_X")
        assert called["provider"] == 1
    finally:
        clear_exhausted("tavily")


def test_orchestrator_includes_reddit_with_social_source_type(stub_sources):
    """Reddit posts must be tagged source_type='social' and carry volume_metric."""
    items = fetch_ticker_news("SYN_X")
    reddit_items = [it for it in items if it.source == "reddit"]
    assert len(reddit_items) >= 1
    for it in reddit_items:
        assert it.source_type == "social"
        assert it.volume_metric is not None
        assert it.volume_metric > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_news_feed_orchestrator.py -v`
Expected: 8 FAILs ("No module named 'src.reports.news_feed'").

- [ ] **Step 3: Implement the orchestrator**

Create `src/reports/news_feed.py`:

```python
"""Per-ticker news orchestrator (Phase 1 unified pipeline).

Flow:
  1. Fan out: fetch from eight sources.
     Always-on (free / no quota): Finnhub, Tiingo, Yahoo Finance RSS,
       Google News RSS, GDELT, Reddit.
     Quota-bound: Tavily, Exa — skipped when both are on cooldown.
  2. Normalize: each source's adapter converts dicts → NewsItem.
  3. Dedup: cluster across sources (URL or title+hour bucket).
  4. Score: assign importance based on source authority, recency, cluster breadth.
  5. Persist: write to news_items.
  6. Return: ranked list, newest+most-important first.

A source that returns None (paid-tier 403, missing key, transient failure)
is silently skipped — the feed degrades gracefully but the request still succeeds.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from src.analysis.news_dedup import cluster_news_items
from src.analysis.news_importance import score_importance
from src.data.finnhub import get_company_news as _fetch_finnhub
from src.data.gdelt_doc import get_gdelt_articles as _fetch_gdelt
from src.data.google_news_rss import get_google_news as _fetch_google
from src.data.news import NewsProvider
from src.data.news_adapters.exa_adapter import exa_to_news_item
from src.data.news_adapters.finnhub_adapter import finnhub_to_news_item
from src.data.news_adapters.gdelt_adapter import gdelt_to_news_item
from src.data.news_adapters.google_news_adapter import google_to_news_item
from src.data.news_adapters.reddit_adapter import reddit_to_news_item
from src.data.news_adapters.tavily_adapter import tavily_to_news_item
from src.data.news_adapters.tiingo_adapter import tiingo_to_news_item
from src.data.news_adapters.yahoo_finance_adapter import yahoo_to_news_item
from src.data.news_store import save_news_items
from src.data.quota_tracker import is_exhausted
from src.data.reddit_search import get_reddit_posts as _fetch_reddit
from src.data.tiingo import get_news as _fetch_tiingo
from src.data.yahoo_finance_rss import get_yahoo_news as _fetch_yahoo
from src.models.news_item import NewsItem


def fetch_ticker_news(symbol: str, *, days: int = 14, limit: int = 25) -> list[NewsItem]:
    """Build the unified per-ticker news feed.

    Returns NewsItems sorted by importance_score (desc). Persists every
    item to news_items; subsequent calls with the same URL skip the insert.
    """
    symbol = symbol.upper()
    items: list[NewsItem] = []

    # 1a. Finnhub (structured, ticker-tagged)
    raw_finnhub = _fetch_finnhub(symbol, days=days) or []
    for row in raw_finnhub:
        item = finnhub_to_news_item(row, symbol=symbol)
        if item is not None:
            items.append(item)

    # 1b. Tiingo (silently None on free tier — that's fine)
    raw_tiingo = _fetch_tiingo(symbol=symbol, limit=50, days=days) or []
    for row in raw_tiingo:
        item = tiingo_to_news_item(row)
        if item is None or symbol not in item.tickers:
            continue
        items.append(item)

    # 1c. Yahoo Finance RSS (no key, ticker-tagged, free)
    raw_yahoo = _fetch_yahoo(symbol) or []
    for row in raw_yahoo:
        item = yahoo_to_news_item(row, symbol=symbol)
        if item is not None:
            items.append(item)

    # 1d. Google News RSS (no key, broad aggregator, free)
    raw_google = _fetch_google(f"{symbol} stock") or []
    for row in raw_google:
        item = google_to_news_item(row, symbol=symbol)
        if item is not None:
            items.append(item)

    # 1e. GDELT DOC 2.0 (no key, global news index, free)
    raw_gdelt = _fetch_gdelt(symbol) or []
    for row in raw_gdelt:
        item = gdelt_to_news_item(row, symbol=symbol)
        if item is not None:
            items.append(item)

    # 1f. Reddit (no key, social signal — source_type="social", upvotes in volume_metric)
    raw_reddit = _fetch_reddit(symbol) or []
    for row in raw_reddit:
        item = reddit_to_news_item(row, symbol=symbol)
        if item is not None:
            items.append(item)

    # 1g + 1h: Tavily + Exa via NewsProvider.search_stock_news (quota-bound).
    # Skip the network call entirely if BOTH are on quota cooldown — NewsProvider
    # would just return [] from each internal search and we'd burn the latency.
    # If only one is exhausted, still call: NewsProvider will skip the exhausted
    # one internally (its fetcher short-circuits when the quota cache key is set).
    if is_exhausted("tavily") and is_exhausted("exa"):
        provider_results: list[dict] = []
    else:
        try:
            provider_results = NewsProvider().search_stock_news(symbol, days=days) or []
        except Exception:
            provider_results = []
    for row in provider_results:
        # NewsProvider normalizes both Tavily and Exa to the same dict shape
        # but doesn't tag which provider produced each result. Phase 1 attributes
        # everything to 'tavily' — importance scores are identical for both.
        item = tavily_to_news_item(row, symbol=symbol)
        if item is not None:
            items.append(item)

    if not items:
        return []

    # 2. Dedup
    clusters = cluster_news_items(items)
    cluster_sizes: Counter[str] = Counter()
    for cid, group in clusters.items():
        cluster_sizes[cid] = len({i.source for i in group})

    # 3. Score
    now = datetime.now(timezone.utc)
    for item in items:
        item.importance_score = score_importance(
            item,
            cluster_size=cluster_sizes.get(item.cluster_id or "", 1),
            now=now,
        )

    # 4. Persist
    save_news_items(items)

    # 5. Rank + cap
    items.sort(key=lambda i: (i.importance_score or 0.0), reverse=True)
    return items[:limit]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_news_feed_orchestrator.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/reports/news_feed.py tests/test_news_feed_orchestrator.py
git commit -m "feat(reports): add unified per-ticker news orchestrator (8 sources, quota-aware)"
```

---

## Task 16: API route exposing the unified feed

**Files:**
- Create: `api/routes/news_unified.py`
- Modify: `api/main.py` (register the router)
- Test: `tests/test_news_unified_route.py`

- [ ] **Step 1: Inspect main.py to find router registration pattern**

Run: `grep -n "include_router" /home/shafkat/project/Trading/api/main.py | head -5`
Expected: a list of `app.include_router(...)` lines — note one to use as a template.

- [ ] **Step 2: Write the failing test**

Create `tests/test_news_unified_route.py`:

```python
"""Integration test for GET /api/news/unified/{symbol}."""
from __future__ import annotations

from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(monkeypatch):
    # Stub the orchestrator so the route test doesn't hit external APIs.
    from src.models.news_item import NewsItem

    def fake_fetch(symbol, days=14, limit=25):
        return [
            NewsItem(
                source="finnhub", source_type="news",
                url="https://test.example.com/route",
                title=f"{symbol} earnings beat",
                published_at="2026-01-15T10:00:00+00:00",
                fetched_at="2026-01-15T10:00:00+00:00",
                tickers=[symbol],
                importance_score=0.82,
                cluster_id="abc",
            )
        ]
    monkeypatch.setattr("api.routes.news_unified.fetch_ticker_news", fake_fetch)

    from api.main import app
    return TestClient(app)


def test_unified_route_returns_items(client):
    r = client.get("/api/news/unified/SYN_X")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert body["symbol"] == "SYN_X"
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "SYN_X earnings beat"
    assert body["items"][0]["importance_score"] == 0.82


def test_unified_route_uppercases_symbol(client):
    r = client.get("/api/news/unified/syn_x")
    assert r.json()["symbol"] == "SYN_X"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_news_unified_route.py -v`
Expected: FAIL (404 — route not registered).

- [ ] **Step 4: Implement the route**

Create `api/routes/news_unified.py`:

```python
"""GET /api/news/unified/{symbol} — Phase 1 unified per-ticker feed.

Returns NewsItems from Finnhub + Tiingo + Tavily + Exa, deduplicated and
ranked by importance.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from src.reports.news_feed import fetch_ticker_news


router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("/unified/{symbol}")
def get_unified_feed(
    symbol: str,
    days: int = Query(14, ge=1, le=90),
    limit: int = Query(25, ge=1, le=100),
) -> dict:
    sym = symbol.upper()
    items = fetch_ticker_news(sym, days=days, limit=limit)
    return {
        "symbol": sym,
        "count": len(items),
        "items": [item.model_dump() for item in items],
    }
```

- [ ] **Step 5: Register the router in `api/main.py`**

Add the import near the other route imports:

```python
from api.routes import news_unified
```

And register it alongside the other `app.include_router(...)` calls:

```python
app.include_router(news_unified.router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_news_unified_route.py -v`
Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add api/routes/news_unified.py api/main.py tests/test_news_unified_route.py
git commit -m "feat(api): expose GET /api/news/unified/{symbol}"
```

---

## Task 17: Migrate news_feed_service to use the unified orchestrator

**Files:**
- Modify: `api/services/news_feed_service.py`
- Test: `tests/test_news_feed_service_migrated.py`

- [ ] **Step 1: Read the current service to understand its public interface**

Run: `pytest tests/test_api.py -k news_feed -v 2>&1 | head -40` (note any existing contract tests).
Then `grep -rn "from api.services.news_feed_service\|from api.services import news_feed_service" /home/shafkat/project/Trading --include="*.py"` to find every caller.

- [ ] **Step 2: Write the failing test**

Create `tests/test_news_feed_service_migrated.py`:

```python
"""Verify news_feed_service now sources from the unified orchestrator
while preserving its public response shape for existing callers.
"""
from __future__ import annotations

import pytest

from src.models.news_item import NewsItem


@pytest.fixture
def stubbed_orchestrator(monkeypatch):
    def fake_fetch(symbol, days=14, limit=25):
        return [
            NewsItem(
                source="finnhub", source_type="news",
                url="https://test.example.com/1",
                title="SYN_X reports record quarter",
                summary="Synthetic record",
                published_at="2026-01-15T10:00:00+00:00",
                fetched_at="2026-01-15T10:00:00+00:00",
                author="Reuters",
                tickers=[symbol],
                importance_score=0.81,
                cluster_id="c1",
            ),
            NewsItem(
                source="tavily", source_type="news",
                url="https://test.example.com/2",
                title="SYN_X faces antitrust probe",
                summary="Regulators probe SYN_X",
                published_at="2026-01-15T08:00:00+00:00",
                fetched_at="2026-01-15T10:00:00+00:00",
                author="bloomberg.example.com",
                tickers=[symbol],
                importance_score=0.55,
                cluster_id="c2",
            ),
        ]
    monkeypatch.setattr("api.services.news_feed_service.fetch_ticker_news", fake_fetch)


def test_service_returns_unified_items(stubbed_orchestrator):
    from api.services.news_feed_service import get_news_feed
    feed = get_news_feed("SYN_X", force=True)
    assert feed["symbol"] == "SYN_X"
    assert len(feed["items"]) == 2
    titles = [i["headline"] for i in feed["items"]]
    assert "SYN_X reports record quarter" in titles


def test_service_preserves_response_shape(stubbed_orchestrator):
    """Existing frontend expects: items[].headline, items[].sentiment.label, items[].url"""
    from api.services.news_feed_service import get_news_feed
    feed = get_news_feed("SYN_X", force=True)
    item = feed["items"][0]
    assert set(item.keys()) >= {"headline", "url", "source", "published", "sentiment"}
    assert set(item["sentiment"].keys()) >= {"label", "score"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_news_feed_service_migrated.py -v`
Expected: FAIL (current service uses NewsProvider directly, not `fetch_ticker_news`).

- [ ] **Step 4: Rewrite the service to call the orchestrator**

Replace the body of `api/services/news_feed_service.py` (preserving the keyword-sentiment helper for items without an importance/sentiment score):

```python
"""News feed for a stock — backed by the unified Phase 1 orchestrator.

The public response shape is unchanged so existing callers (frontend
StockDetail page, alerts pipeline) keep working:

  {
    "symbol": str,
    "items": [
      {
        "headline": str,
        "url": str,
        "source": str,
        "published": str (ISO),
        "sentiment": {"label": "bullish"|"bearish"|"neutral", "score": float},
        "importance": float | None,
      },
      ...
    ],
    "from_cache": bool,
  }

Behind the scenes we now pull from Finnhub + Tiingo + Tavily + Exa,
deduplicated and importance-ranked.
"""
from __future__ import annotations

from src.reports.news_feed import fetch_ticker_news
from src.utils.db import cache_get, cache_set


_CACHE_TTL_MINUTES = 30
_MAX_ITEMS = 10

_BULL_WORDS = {
    "beat", "beats", "surge", "surges", "rally", "rallies", "upgrade", "upgraded",
    "outperform", "buy", "raises", "boost", "boosts", "record", "all-time", "high",
    "expansion", "growth", "growing", "rising", "jumps", "jumped", "soars", "soared",
    "breakout", "breaks out", "bullish", "strong", "stronger", "exceeded", "exceed",
    "guidance raised", "raised guidance", "tops", "topped", "blowout", "stellar",
    "approval", "approved", "wins", "won", "deal", "acquisition", "milestone",
    "launches", "launched", "demand", "tailwind",
}
_BEAR_WORDS = {
    "miss", "misses", "drop", "drops", "fall", "falls", "fell", "downgrade", "downgraded",
    "underperform", "sell", "cuts", "cut", "lawsuit", "fraud", "investigation", "probe",
    "decline", "declines", "warning", "warned", "weak", "weaker", "shortfall",
    "guidance cut", "cut guidance", "guides lower", "tumbles", "tumbled",
    "plunges", "plunged", "loss", "losses", "fired", "ousted", "scandal",
    "recall", "delisted", "bankruptcy", "default", "headwind",
    "below estimates", "missed estimates", "disappointed", "disappointing",
}


def _score_sentiment(text: str) -> dict:
    if not text:
        return {"label": "neutral", "score": 0.0}
    t = text.lower()
    bull = sum(1 for w in _BULL_WORDS if w in t)
    bear = sum(1 for w in _BEAR_WORDS if w in t)
    total = bull + bear
    if total == 0:
        return {"label": "neutral", "score": 0.0}
    score = (bull - bear) / max(total, 1)
    if score >= 0.3:
        label = "bullish"
    elif score <= -0.3:
        label = "bearish"
    else:
        label = "neutral"
    return {"label": label, "score": round(score, 2)}


def get_news_feed(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"news_feed:v2:{symbol}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    items = fetch_ticker_news(symbol, days=14, limit=_MAX_ITEMS)
    out_items: list[dict] = []
    for it in items:
        title = it.title.strip()
        summary = (it.summary or "").strip()
        sentiment = _score_sentiment(f"{title}. {summary}")
        out_items.append({
            "headline": title,
            "url": it.url,
            "source": it.author or it.source,
            "published": it.published_at,
            "sentiment": sentiment,
            "importance": it.importance_score,
        })

    payload = {
        "symbol": symbol,
        "items": out_items,
        "from_cache": False,
    }
    cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    return payload
```

- [ ] **Step 5: Run the new test**

Run: `pytest tests/test_news_feed_service_migrated.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Run the full news test suite to confirm nothing else broke**

Run: `pytest tests/test_news_item_model.py tests/test_news_adapters.py tests/test_news_dedup.py tests/test_news_importance.py tests/test_news_store.py tests/test_news_feed_orchestrator.py tests/test_news_unified_route.py tests/test_news_feed_service_migrated.py -v`
Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
git add api/services/news_feed_service.py tests/test_news_feed_service_migrated.py
git commit -m "feat(api): migrate news_feed_service to unified orchestrator"
```

---

## Task 18: Geopolitical fallback chain — GDELT + Google News when Tavily/Exa are out

`api/services/events_service.py` fetches geopolitical events by topical keyword query (`"US tariffs trade war impact industries sectors"`, etc.) — not by ticker. Today it tries Tavily then Exa, and silently returns `[]` when both are out of quota, which the UI then renders as a false "All Clear." This task makes that path resilient by:

1. Skipping Tavily/Exa entirely when they're on cooldown (using `quota_tracker` from Task 10).
2. Marking them exhausted on 402/403/429 (same as `NewsProvider` does in Task 10).
3. Falling back to GDELT (Task 13) then Google News RSS (Task 12) — both no-key, no-quota, both take generic queries.
4. Setting `data_available=True` whenever ANY source returns, and using a short 5-min cache TTL when EVERY source fails so the next request retries instead of being stuck for an hour.

Reuses `get_gdelt_articles` and `get_google_news` as-is — they were built generic on purpose. No new adapters needed for the geopolitical path because `events_service` doesn't build `NewsItem`s, it builds its own event-card dicts; we just normalize the few fields it needs (`title`, `content`, `url`).

> **Depends on:** Task 10 (`quota_tracker`), Task 12 (`google_news_rss`), Task 13 (`gdelt_doc`). Do those first.

**Files:**
- Modify: `api/services/events_service.py` (whole-file rewrite — current file is ~125 lines)
- Test: `tests/test_events_service_fallback.py`

- [ ] **Step 1: Write the failing test file**

Create `tests/test_events_service_fallback.py`:

```python
"""Tests for the geopolitical fallback chain in events_service."""
from __future__ import annotations

import pytest

from src.data.quota_tracker import clear_exhausted, mark_exhausted
from src.utils.db import cache_delete, init_db


@pytest.fixture(autouse=True)
def _fresh_state():
    init_db()
    cache_delete("geo_events_v1")
    clear_exhausted("tavily")
    clear_exhausted("exa")
    yield
    cache_delete("geo_events_v1")
    clear_exhausted("tavily")
    clear_exhausted("exa")


def _stub_all(monkeypatch, *, tavily=([], False), exa=([], False),
              gdelt=None, google=None):
    """Patch all four upstreams. gdelt/google are raw row lists (or None)."""
    from api.services import events_service as svc

    monkeypatch.setattr(svc, "_search_tavily", lambda q: tavily)
    monkeypatch.setattr(svc, "_search_exa", lambda q: exa)
    monkeypatch.setattr(svc, "get_gdelt_articles", lambda q, limit=5: gdelt)
    monkeypatch.setattr(svc, "get_google_news", lambda q, limit=5: google)


def test_uses_tavily_when_available(monkeypatch):
    from api.services import events_service as svc

    tavily_rows = [{"title": "Tariff news", "content": "details about tariff", "url": "https://x"}]
    _stub_all(monkeypatch, tavily=(tavily_rows, True))

    out = svc.get_geopolitical_events()
    assert out["data_available"] is True
    assert len(out["events"]) >= 1
    assert out["events"][0]["title"] == "Tariff news"


def test_falls_back_to_exa_when_tavily_fails(monkeypatch):
    from api.services import events_service as svc

    exa_rows = [{"title": "Exa news", "content": "details", "url": "https://y"}]
    _stub_all(monkeypatch, tavily=([], False), exa=(exa_rows, True))

    out = svc.get_geopolitical_events()
    assert out["data_available"] is True
    assert out["events"][0]["title"] == "Exa news"


def test_falls_back_to_gdelt_when_tavily_exa_fail(monkeypatch):
    from api.services import events_service as svc

    gdelt_rows = [{"title": "GDELT headline", "url": "https://g/1",
                   "seendate": "20260523T120000Z", "domain": "reuters.com"}]
    _stub_all(monkeypatch, tavily=([], False), exa=([], False),
              gdelt=gdelt_rows)

    out = svc.get_geopolitical_events()
    assert out["data_available"] is True
    assert out["events"][0]["title"] == "GDELT headline"
    assert out["events"][0]["url"] == "https://g/1"


def test_falls_back_to_google_when_gdelt_fails(monkeypatch):
    from api.services import events_service as svc

    google_rows = [{"title": "Google headline", "url": "https://goog/1",
                    "pub_date": "Sat, 23 May 2026 12:00:00 GMT",
                    "source": "Bloomberg", "description": "Google snippet"}]
    _stub_all(monkeypatch, tavily=([], False), exa=([], False),
              gdelt=None, google=google_rows)

    out = svc.get_geopolitical_events()
    assert out["data_available"] is True
    assert out["events"][0]["title"] == "Google headline"
    assert out["events"][0]["snippet"] == "Google snippet"


def test_all_fail_sets_data_unavailable_short_ttl(monkeypatch):
    from api.services import events_service as svc
    from src.utils.db import get_connection
    from datetime import datetime

    _stub_all(monkeypatch, gdelt=None, google=None)

    out = svc.get_geopolitical_events()
    assert out["events"] == []
    assert out["data_available"] is False

    # Confirm short TTL — cache entry must expire in <= 6 min.
    # Uses get_connection() so the test honors the temp-DB fixture in conftest.py.
    conn = get_connection()
    row = conn.execute(
        "SELECT expires_at FROM cache WHERE key=?", ("geo_events_v1",)
    ).fetchone()
    conn.close()
    assert row is not None
    expires = datetime.fromisoformat(row["expires_at"])
    delta_min = (expires - datetime.utcnow()).total_seconds() / 60
    assert delta_min <= 6, f"expected short TTL on failure, got {delta_min} min"


def test_tavily_skipped_when_on_cooldown(monkeypatch):
    """If Tavily is marked exhausted, _search_tavily must NOT be invoked."""
    from api.services import events_service as svc

    call_log = []
    def spy_tavily(q):
        call_log.append(q)
        return [{"title": "should not appear", "content": "", "url": ""}], True

    gdelt_rows = [{"title": "GDELT win", "url": "https://g",
                   "seendate": "20260523T120000Z", "domain": "x"}]
    monkeypatch.setattr(svc, "_search_tavily", spy_tavily)
    monkeypatch.setattr(svc, "_search_exa", lambda q: ([], False))
    monkeypatch.setattr(svc, "get_gdelt_articles", lambda q, limit=5: gdelt_rows)
    monkeypatch.setattr(svc, "get_google_news", lambda q, limit=5: None)

    mark_exhausted("tavily")
    out = svc.get_geopolitical_events()

    assert call_log == [], "Tavily should be skipped while on cooldown"
    assert out["data_available"] is True
    assert out["events"][0]["title"] == "GDELT win"


def test_tavily_429_marks_exhausted(monkeypatch):
    """A 429 response from Tavily inside events_service must trigger cooldown."""
    from api.services import events_service as svc
    from src.data.quota_tracker import is_exhausted

    class FakeResp:
        status_code = 429
        text = "rate limited"
        def json(self): return {}

    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(svc.httpx, "post", lambda *a, **kw: FakeResp())
    clear_exhausted("tavily")

    rows, ok = svc._search_tavily("anything")
    assert rows == [] and ok is False
    assert is_exhausted("tavily") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_events_service_fallback.py -v`
Expected: 7 FAILs — most will fail with `AttributeError: module 'api.services.events_service' has no attribute 'get_gdelt_articles'` (or similar), confirming the fallback chain isn't wired yet.

- [ ] **Step 3: Rewrite `events_service.py` with the fallback chain**

Replace the entire contents of `api/services/events_service.py`:

```python
"""Geopolitical events: tariffs, war, natural disaster, supply chain.

Fallback chain per topical query:
    Tavily → Exa → GDELT DOC 2.0 → Google News RSS

Tavily/Exa are paid, quota-bound. Once a 402/403/429 is observed,
`quota_tracker` marks the source exhausted for 4 hours; subsequent calls
skip it. GDELT and Google News are no-key / no-quota and act as durable
fallbacks so the geopolitical view never goes dark just because the paid
APIs are out of credits.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx

from src.data.gdelt_doc import get_gdelt_articles
from src.data.google_news_rss import get_google_news
from src.data.quota_tracker import is_exhausted, mark_exhausted
from src.utils.db import cache_get, cache_set

logger = logging.getLogger(__name__)


# Sector impact mapping per event category.
IMPACT = {
    "tariff": {
        "icon": "🏷",
        "negative": ["Technology", "Consumer Discretionary", "Industrials", "Materials"],
        "positive": ["Domestic Manufacturing", "Utilities", "Healthcare (domestic)"],
        "explanation": "Tariffs raise input costs for importers and manufacturers. Tech and consumer goods face higher component costs. Domestic producers may benefit.",
    },
    "war": {
        "icon": "⚔",
        "negative": ["Airlines", "Tourism", "Consumer Discretionary", "Global Banks"],
        "positive": ["Defense & Aerospace", "Energy (oil/gas)", "Cybersecurity", "Gold miners"],
        "explanation": "Conflicts drive defense spending, spike oil prices, create risk-off sentiment. Defense surges while travel and consumer spending pull back.",
    },
    "natural_disaster": {
        "icon": "🌊",
        "negative": ["Insurance", "Real Estate", "Agriculture", "Regional banks"],
        "positive": ["Construction", "Home improvement", "Infrastructure", "Utilities rebuild"],
        "explanation": "Disasters destroy assets but create rebuilding demand. Insurance faces claims; construction and materials companies see revenue spikes.",
    },
    "supply_chain": {
        "icon": "🚢",
        "negative": ["Automotive", "Electronics", "Retail", "Restaurants"],
        "positive": ["Shipping & Logistics", "Warehousing", "Domestic alternatives"],
        "explanation": "Disruptions cause shortages and cost inflation. Companies with domestic supply chains or inventory buffers outperform.",
    },
}

CATEGORIES = [
    {"type": "tariff", "query": "US tariffs trade war impact industries sectors", "severity": ["200%", "new tariff", "trade war escalat", "retaliat"]},
    {"type": "war", "query": "war conflict military impact US stock market", "severity": ["escalat", "invasion", "missile", "nuclear", "sanction"]},
    {"type": "natural_disaster", "query": "flood hurricane earthquake wildfire disaster US economic impact", "severity": ["billion damage", "emergency", "catastroph", "devastat"]},
    {"type": "supply_chain", "query": "supply chain disruption shortage US industry impact", "severity": ["shortage", "disruption", "backlog", "shut down"]},
]


# ── Per-source fetchers ──────────────────────────────────────────────

def _search_tavily(query: str) -> tuple[list[dict], bool]:
    """Returns (results, upstream_ok). Marks Tavily exhausted on 402/403/429."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return [], False
    try:
        r = httpx.post(
            "https://api.tavily.com/search",
            json={"query": query, "api_key": api_key, "max_results": 3, "search_depth": "basic"},
            timeout=12,
        )
        if r.status_code in (402, 403, 429):
            mark_exhausted("tavily")
            logger.warning("Tavily quota exhausted (HTTP %s); cooldown applied", r.status_code)
            return [], False
        if r.status_code != 200:
            logger.warning("Tavily search failed: HTTP %s body=%s", r.status_code, r.text[:200])
            return [], False
        return r.json().get("results", []) or [], True
    except Exception as e:
        logger.warning("Tavily search exception: %r", e)
        return [], False


def _search_exa(query: str) -> tuple[list[dict], bool]:
    """Returns (results, upstream_ok). Marks Exa exhausted on 402/403/429."""
    api_key = os.environ.get("EXA_API_KEY", "")
    if not api_key:
        return [], False
    try:
        r = httpx.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": api_key},
            json={"query": query, "type": "auto", "num_results": 3,
                  "contents": {"highlights": {"max_characters": 200}}},
            timeout=12,
        )
        if r.status_code in (402, 403, 429):
            mark_exhausted("exa")
            logger.warning("Exa quota exhausted (HTTP %s); cooldown applied", r.status_code)
            return [], False
        if r.status_code != 200:
            logger.warning("Exa search failed: HTTP %s body=%s", r.status_code, r.text[:200])
            return [], False
        results = r.json().get("results", []) or []
        return [
            {
                "title": x.get("title", ""),
                "content": " ".join(x.get("highlights", []))[:200],
                "url": x.get("url", ""),
            }
            for x in results
        ], True
    except Exception as e:
        logger.warning("Exa search exception: %r", e)
        return [], False


# ── Normalizers (GDELT / Google rows → {title, content, url}) ────────

def _normalize_gdelt(rows: list[dict]) -> list[dict]:
    """GDELT articles have no snippet; use the title as content."""
    out: list[dict] = []
    for r in rows:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "title": title,
            "content": title,
            "url": (r.get("url") or "").strip(),
        })
    return out


def _normalize_google(rows: list[dict]) -> list[dict]:
    """Google News rows: use `description` as content, fall back to title."""
    out: list[dict] = []
    for r in rows:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "title": title,
            "content": (r.get("description") or title).strip(),
            "url": (r.get("url") or "").strip(),
        })
    return out


# ── Fallback chain ───────────────────────────────────────────────────

def _fetch_category(query: str) -> tuple[list[dict], bool]:
    """Try sources in order until one succeeds. Returns (rows, upstream_ok).

    Order: Tavily (if not on cooldown) → Exa (if not on cooldown) → GDELT → Google News.
    upstream_ok=True if ANY source returned (even with zero rows).
    """
    if not is_exhausted("tavily"):
        rows, ok = _search_tavily(query)
        if ok:
            return rows, True

    if not is_exhausted("exa"):
        rows, ok = _search_exa(query)
        if ok:
            return rows, True

    # GDELT — no quota, no key. Returns None on transport failure, [] on no hits.
    gdelt_rows = get_gdelt_articles(query, limit=5)
    if gdelt_rows is not None:
        return _normalize_gdelt(gdelt_rows[:3]), True

    # Google News RSS — no quota, no key. Last resort.
    google_rows = get_google_news(query, limit=5)
    if google_rows is not None:
        return _normalize_google(google_rows[:3]), True

    return [], False


# ── Public entry point ──────────────────────────────────────────────

def get_geopolitical_events() -> dict:
    """Fetch + categorize geopolitical events. Cached 1 hour on success,
    5 min when every upstream failed so we retry as soon as cooldowns expire.
    """
    cached = cache_get("geo_events_v1")
    if cached:
        return cached

    events: list[dict] = []
    any_upstream_ok = False
    for cat in CATEGORIES:
        results, ok = _fetch_category(cat["query"])
        if ok:
            any_upstream_ok = True
        impact = IMPACT.get(cat["type"], {})
        for r in results[:2]:
            title = (r.get("title") or "")[:120]
            content = (r.get("content") or "")[:200]
            url = r.get("url") or ""
            combined = (title + " " + content).lower()
            severity = "high" if any(kw in combined for kw in cat["severity"]) else "moderate"
            events.append({
                "type": cat["type"],
                "icon": impact.get("icon", "⚠"),
                "title": title,
                "snippet": content,
                "url": url,
                "severity": severity,
                "negative_sectors": impact.get("negative", []),
                "positive_sectors": impact.get("positive", []),
                "explanation": impact.get("explanation", ""),
            })

    payload = {
        "events": events,
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "data_available": any_upstream_ok,
    }
    try:
        ttl = 60 if any_upstream_ok else 5
        cache_set("geo_events_v1", payload, ttl_minutes=ttl)
    except Exception:
        pass
    return payload
```

- [ ] **Step 4: Run the fallback tests**

Run: `pytest tests/test_events_service_fallback.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Smoke-test against the live endpoint**

Restart uvicorn (or trust auto-reload) and hit:

```bash
curl -s "http://127.0.0.1:8000/market/geopolitical" | python -m json.tool | head -20
```

Expected: response includes `"data_available": true` and one or more `events` entries — because even with Tavily/Exa out of quota, GDELT and/or Google News will return real headlines for queries like "US tariffs trade war".

If `data_available` is still `false` here, GDELT and Google News both failed too — inspect uvicorn logs for the `gdelt`/`google_news_rss` `error` lines logged by the fetchers.

- [ ] **Step 6: Commit**

```bash
git add api/services/events_service.py tests/test_events_service_fallback.py
git commit -m "feat(api): geopolitical fallback chain Tavily→Exa→GDELT→Google News"
```

---

## Self-Review Notes (post-write)

**Spec coverage check:**
- Unified `NewsItem` schema → Task 2.
- SQLite tables (news_items, news_ticker_tags, news_clusters) → Task 1.
- Adapters for Finnhub / Tiingo / Tavily / Exa → Tasks 3–6.
- Dedup (URL + title-hour) → Task 7.
- Importance scoring → Task 8.
- Storage layer → Task 9.
- Quota cooldown for Tavily / Exa → Task 10.
- No-key primary sources (Yahoo Finance RSS, Google News RSS, GDELT, Reddit) → Tasks 11–14.
- Orchestrator (eight sources, quota-aware) → Task 15.
- API endpoint → Task 16.
- Migration of existing service → Task 17.
- Geopolitical-view fallback chain (Tavily → Exa → GDELT → Google News) → Task 18.

**Type-consistency check:** All adapters return `NewsItem | None`. `fetch_ticker_news` returns `list[NewsItem]`. `save_news_items` returns `int`. `get_news_items_for_ticker` returns `list[NewsItem]`. Names match across tasks.

**Layer-rule check (CLAUDE.md):**
- `src/data/news_adapters/` and `src/data/news_store.py` only import from `src/models` + `src/utils/db` — OK.
- `src/analysis/news_dedup.py` + `src/analysis/news_importance.py` only import from `src/models` — OK (no data, no DB).
- `src/reports/news_feed.py` is the ONLY module that imports from both `src/data/*` and `src/analysis/*` — OK (orchestration layer).
- `api/services/news_feed_service.py` calls `src/reports/news_feed.py`, not data/analysis directly — OK.

**Test isolation:** All tests use synthetic symbols (`SYN_X`, `SYN_A`..`SYN_F`) and rely on `tests/conftest.py`'s session-scoped temp DB. No production DB risk.

---

## Out of Scope (deferred to later phases)

- Adding NEW sources: StockTwits, Google Trends, Alpha Vantage NEWS_SENTIMENT, SEC EDGAR full-text, earnings transcripts.
- Market-pulse view (aggregate sentiment dashboard).
- Geopolitical view (event timeline + sector-impact mapping).
- LLM-based sentiment scoring on the full body (currently keyword-based; orchestrator just sets `importance_score`).
- Polygon news fetcher and AV NEWS_SENTIMENT fetcher (need new `src/data/polygon.py` + `src/data/alpha_vantage.py` functions before they can be adapted).
- Frontend changes consuming `importance_score` or the new endpoint — backend-only in Phase 1.
