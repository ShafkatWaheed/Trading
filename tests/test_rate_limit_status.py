"""Tests for `get_rate_limit_status()` — the function powering the
Data Sources tab. Exercises the threshold logic by monkey-patching
`get_connection` to return a sqlite in-memory DB pre-populated with
api_log rows.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src.utils import db as db_module
from src.utils.rate_limit import get_rate_limit_status


def _build_log(rows: dict[str, int]) -> sqlite3.Connection:
    """Build an in-memory api_log populated with `rows[source] = count` recent calls."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE api_log (id INTEGER PRIMARY KEY, source TEXT, endpoint TEXT, "
        "status TEXT, error_message TEXT, timestamp TEXT)"
    )
    now = datetime.now(timezone.utc)
    for source, count in rows.items():
        for i in range(count):
            ts = (now - timedelta(milliseconds=i * 10)).isoformat()
            conn.execute(
                "INSERT INTO api_log (source, endpoint, status, timestamp) VALUES (?, ?, ?, ?)",
                (source, "/x", "success", ts),
            )
    conn.commit()
    return conn


def _by_key(statuses) -> dict[str, object]:
    return {s.key: s for s in statuses}


def test_all_sources_ok_when_log_is_empty(monkeypatch):
    monkeypatch.setattr(db_module, "get_connection", lambda: _build_log({}))
    by = _by_key(get_rate_limit_status())
    assert by["alphavantage"].status == "ok"
    assert by["polygon"].status == "ok"
    assert by["sec_edgar"].status == "ok"
    # Untracked sources stay "untracked" regardless of count.
    assert by["yahoo"].status == "untracked"
    assert by["tavily"].status == "untracked"
    assert by["exa"].status == "untracked"
    assert by["congress"].status == "untracked"


def test_at_capacity_is_limited(monkeypatch):
    # Alpha Vantage cap is 5 in 60s; insert exactly 5 -> limited.
    monkeypatch.setattr(db_module, "get_connection", lambda: _build_log({"alphavantage": 5}))
    by = _by_key(get_rate_limit_status())
    assert by["alphavantage"].status == "limited"
    assert by["alphavantage"].is_limited is True
    assert by["alphavantage"].used == 5


def test_over_capacity_is_limited(monkeypatch):
    monkeypatch.setattr(db_module, "get_connection", lambda: _build_log({"polygon": 99}))
    by = _by_key(get_rate_limit_status())
    assert by["polygon"].status == "limited"


def test_eighty_percent_is_warning(monkeypatch):
    # Cap 5 -> 80% threshold = 4. Insert 4 -> warning, not limited.
    monkeypatch.setattr(db_module, "get_connection", lambda: _build_log({"alphavantage": 4}))
    by = _by_key(get_rate_limit_status())
    assert by["alphavantage"].status == "warning"


def test_below_threshold_is_ok(monkeypatch):
    monkeypatch.setattr(db_module, "get_connection", lambda: _build_log({"alphavantage": 1}))
    by = _by_key(get_rate_limit_status())
    assert by["alphavantage"].status == "ok"


def test_untracked_sources_show_count_but_never_flag(monkeypatch):
    # Even with a huge call count, untracked stays untracked.
    monkeypatch.setattr(db_module, "get_connection", lambda: _build_log({"yahoo": 500}))
    by = _by_key(get_rate_limit_status())
    assert by["yahoo"].status == "untracked"
    assert by["yahoo"].used == 500
    assert by["yahoo"].capacity is None


def test_window_excludes_old_rows(monkeypatch):
    # SEC's window is 1 second. A row 10 seconds old must NOT be counted.
    def make_conn():
        conn = _build_log({})
        old_ts = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        conn.execute(
            "INSERT INTO api_log (source, endpoint, status, timestamp) VALUES (?, ?, ?, ?)",
            ("sec_edgar", "/x", "success", old_ts),
        )
        conn.commit()
        return conn

    monkeypatch.setattr(db_module, "get_connection", make_conn)
    by = _by_key(get_rate_limit_status())
    assert by["sec_edgar"].used == 0
    assert by["sec_edgar"].status == "ok"


def test_db_unavailable_returns_untracked_for_all(monkeypatch):
    def boom():
        raise RuntimeError("db gone")
    monkeypatch.setattr(db_module, "get_connection", boom)
    statuses = get_rate_limit_status()
    # One row per spec in _API_SPECS — derive from the source-of-truth so the
    # test doesn't drift every time we add a provider.
    from src.utils.rate_limit import _API_SPECS
    assert len(statuses) == len(_API_SPECS)
    assert all(s.status == "untracked" for s in statuses)
