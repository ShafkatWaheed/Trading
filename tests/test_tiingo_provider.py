"""Tests for src/data/tiingo.py — HTTP mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.data import tiingo
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clear_tiingo_cache():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM cache WHERE key LIKE 'tiingo:%'")
        conn.commit()
    finally:
        conn.close()
    yield
    conn = get_connection()
    try:
        conn.execute("DELETE FROM cache WHERE key LIKE 'tiingo:%'")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def with_api_key(monkeypatch):
    monkeypatch.setattr(tiingo, "TIINGO_API_KEY", "test-key")


def _mock_response(payload, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    if status >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return resp


def test_no_key_short_circuits():
    with patch.object(tiingo.httpx, "get") as mock_get:
        assert tiingo.get_daily_prices("NVDA") is None
        assert tiingo.get_intraday("NVDA") is None
        assert tiingo.get_news() is None
        assert tiingo.get_metadata("NVDA") is None
        mock_get.assert_not_called()


def test_daily_prices_returns_list(with_api_key):
    payload = [
        {"date": "2026-05-14T00:00:00.000Z", "open": 100.0, "close": 102.0,
         "high": 103.0, "low": 99.5, "volume": 1_000_000,
         "adjClose": 102.0, "splitFactor": 1.0, "divCash": 0.0},
    ]
    with patch.object(tiingo.httpx, "get", return_value=_mock_response(payload)):
        rows = tiingo.get_daily_prices("NVDA", start="2026-05-01", end="2026-05-14")
    assert rows[0]["close"] == 102.0


def test_intraday_returns_first_element_of_list(with_api_key):
    payload = [{"ticker": "NVDA", "last": 105.0, "bidPrice": 104.95, "askPrice": 105.05}]
    with patch.object(tiingo.httpx, "get", return_value=_mock_response(payload)):
        row = tiingo.get_intraday("NVDA")
    assert row["last"] == 105.0


def test_intraday_returns_dict_directly(with_api_key):
    payload = {"ticker": "NVDA", "last": 105.0}
    with patch.object(tiingo.httpx, "get", return_value=_mock_response(payload)):
        row = tiingo.get_intraday("NVDA")
    assert row["last"] == 105.0


def test_news_with_ticker_filter(with_api_key):
    payload = [{"title": "NVDA earnings", "tickers": ["NVDA"], "publishedDate": "2026-05-13"}]
    with patch.object(tiingo.httpx, "get", return_value=_mock_response(payload)) as mock_get:
        rows = tiingo.get_news(symbol="NVDA", limit=10)
        # Verify tickers param flowed through
        called_params = mock_get.call_args.kwargs["params"]
        assert called_params["tickers"] == "NVDA"
    assert rows[0]["title"] == "NVDA earnings"


def test_metadata_caches(with_api_key):
    payload = {"name": "NVIDIA Corp", "ticker": "NVDA", "exchangeCode": "NASDAQ"}
    with patch.object(tiingo.httpx, "get", return_value=_mock_response(payload)) as mock_get:
        first = tiingo.get_metadata("NVDA")
        second = tiingo.get_metadata("NVDA")
        assert mock_get.call_count == 1
    assert first["name"] == "NVIDIA Corp"
    assert second == first


def test_http_error_returns_none(with_api_key):
    with patch.object(tiingo.httpx, "get", return_value=_mock_response([], status=500)):
        assert tiingo.get_daily_prices("NVDA") is None
