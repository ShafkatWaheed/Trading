"""Tests for src/data/finnhub.py — HTTP mocked, no network."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.data import finnhub
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clear_finnhub_cache():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM cache WHERE key LIKE 'finnhub:%'")
        conn.commit()
    finally:
        conn.close()
    yield
    conn = get_connection()
    try:
        conn.execute("DELETE FROM cache WHERE key LIKE 'finnhub:%'")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def with_api_key(monkeypatch):
    monkeypatch.setattr(finnhub, "FINNHUB_API_KEY", "test-key")


def _mock_response(payload, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    if status >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return resp


def test_no_key_returns_none_without_request(monkeypatch):
    """Every getter must short-circuit when the API key is missing."""
    # Force module to behave as if env var was unset, even if .env supplied one.
    monkeypatch.setattr(finnhub, "FINNHUB_API_KEY", "")
    with patch.object(finnhub.httpx, "get") as mock_get:
        assert finnhub.get_eps_estimates("NVDA") is None
        assert finnhub.get_recommendation_trend("NVDA") is None
        assert finnhub.get_upgrades_downgrades("NVDA") is None
        assert finnhub.get_company_news("NVDA") is None
        assert finnhub.get_earnings_calendar() is None
        assert finnhub.get_ipo_calendar() is None
        mock_get.assert_not_called()


def test_eps_estimates_parses_data(with_api_key):
    payload = {"data": [
        {"period": "2026-06-30", "epsAvg": 1.50, "numberAnalysts": 25},
    ]}
    with patch.object(finnhub.httpx, "get", return_value=_mock_response(payload)):
        rows = finnhub.get_eps_estimates("NVDA")
    assert rows is not None
    assert rows[0]["epsAvg"] == 1.50


def test_recommendation_trend_returns_list(with_api_key):
    payload = [{"period": "2026-05-01", "strongBuy": 25, "buy": 10, "hold": 5, "sell": 1, "strongSell": 0}]
    with patch.object(finnhub.httpx, "get", return_value=_mock_response(payload)):
        rows = finnhub.get_recommendation_trend("NVDA")
    assert rows == payload


def test_upgrades_downgrades_returns_list(with_api_key):
    payload = [{"symbol": "NVDA", "fromGrade": "Buy", "toGrade": "Strong Buy",
                "company": "Goldman", "action": "up", "gradeTime": 1715000000}]
    with patch.object(finnhub.httpx, "get", return_value=_mock_response(payload)):
        rows = finnhub.get_upgrades_downgrades("NVDA")
    assert rows == payload


def test_company_news_returns_list(with_api_key):
    payload = [
        {"datetime": 1715000000, "headline": "NVDA beats", "source": "Reuters"},
    ]
    with patch.object(finnhub.httpx, "get", return_value=_mock_response(payload)):
        rows = finnhub.get_company_news("NVDA", days=7)
    assert len(rows) == 1


def test_earnings_calendar_handles_envelope(with_api_key):
    payload = {"earningsCalendar": [{"symbol": "NVDA", "date": "2026-05-22"}]}
    with patch.object(finnhub.httpx, "get", return_value=_mock_response(payload)):
        rows = finnhub.get_earnings_calendar(days_ahead=14)
    assert rows[0]["symbol"] == "NVDA"


def test_ipo_calendar_handles_envelope(with_api_key):
    payload = {"ipoCalendar": [{"symbol": "NEWCO", "date": "2026-06-01"}]}
    with patch.object(finnhub.httpx, "get", return_value=_mock_response(payload)):
        rows = finnhub.get_ipo_calendar()
    assert rows[0]["symbol"] == "NEWCO"


def test_http_error_returns_none_not_raise(with_api_key):
    with patch.object(finnhub.httpx, "get", return_value=_mock_response({}, status=500)):
        assert finnhub.get_eps_estimates("NVDA") is None


def test_uses_cache_on_second_call(with_api_key):
    payload = {"data": [{"period": "2026-06-30", "epsAvg": 1.50}]}
    with patch.object(finnhub.httpx, "get", return_value=_mock_response(payload)) as mock_get:
        finnhub.get_eps_estimates("NVDA")
        finnhub.get_eps_estimates("NVDA")
        assert mock_get.call_count == 1
