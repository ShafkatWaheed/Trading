"""Tests for src/data/fred.py — HTTP mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.data import fred
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clear_fred_cache():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM cache WHERE key LIKE 'fred:%'")
        conn.commit()
    finally:
        conn.close()
    yield
    conn = get_connection()
    try:
        conn.execute("DELETE FROM cache WHERE key LIKE 'fred:%'")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def with_api_key(monkeypatch):
    monkeypatch.setattr(fred, "FRED_API_KEY", "test-key")


def _mock_response(payload, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    if status >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return resp


def test_no_key_short_circuits():
    with patch.object(fred.httpx, "get") as mock_get:
        assert fred.get_series("FEDFUNDS") is None
        assert fred.get_latest("FEDFUNDS") is None
        assert fred.get_macro_snapshot() is None
        mock_get.assert_not_called()


def test_get_series_parses_observations(with_api_key):
    payload = {"observations": [
        {"date": "2026-01-01", "value": "5.25"},
        {"date": "2026-02-01", "value": "5.00"},
        {"date": "2026-03-01", "value": "."},  # FRED's null sentinel
    ]}
    with patch.object(fred.httpx, "get", return_value=_mock_response(payload)):
        rows = fred.get_series("FEDFUNDS")
    assert rows[0]["value"] == 5.25
    assert rows[1]["value"] == 5.00
    assert rows[2]["value"] is None  # "." → None


def test_get_latest_returns_most_recent_non_null(with_api_key):
    payload = {"observations": [
        {"date": "2026-01-01", "value": "5.25"},
        {"date": "2026-02-01", "value": "5.00"},
        {"date": "2026-03-01", "value": "."},  # null skipped
    ]}
    with patch.object(fred.httpx, "get", return_value=_mock_response(payload)):
        out = fred.get_latest("FEDFUNDS")
    assert out["date"] == "2026-02-01"
    assert out["value"] == 5.00


def test_get_latest_returns_none_on_all_null(with_api_key):
    payload = {"observations": [{"date": "2026-01-01", "value": "."}]}
    with patch.object(fred.httpx, "get", return_value=_mock_response(payload)):
        assert fred.get_latest("FEDFUNDS") is None


def test_macro_snapshot_returns_dict_per_series(with_api_key):
    """Snapshot iterates MACRO_SERIES; mock returns same payload for all."""
    payload = {"observations": [{"date": "2026-05-01", "value": "4.5"}]}
    with patch.object(fred.httpx, "get", return_value=_mock_response(payload)):
        snap = fred.get_macro_snapshot()
    assert snap is not None
    assert "fed_funds" in snap
    assert snap["fed_funds"]["value"] == 4.5
    assert snap["fed_funds"]["series_id"] == "FEDFUNDS"
    assert snap["fed_funds"]["label"]


def test_http_error_returns_none(with_api_key):
    with patch.object(fred.httpx, "get", return_value=_mock_response({}, status=500)):
        assert fred.get_series("FEDFUNDS") is None


def test_caching_avoids_duplicate_request(with_api_key):
    payload = {"observations": [{"date": "2026-01-01", "value": "5.25"}]}
    with patch.object(fred.httpx, "get", return_value=_mock_response(payload)) as mock_get:
        fred.get_series("FEDFUNDS")
        fred.get_series("FEDFUNDS")
        assert mock_get.call_count == 1
