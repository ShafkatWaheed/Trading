"""Tiingo data provider — clean prices and stock-tagged news.

Free tier: 1,000 calls/day, ~40/min sustained.
https://www.tiingo.com/account/api/token

Exposed shapes (None on failure / API key missing — never raises):

  * `get_daily_prices(symbol, start, end)` — clean adjusted OHLC history
  * `get_intraday(symbol)`                 — most recent IEX top-of-book quote
  * `get_news(symbol=None, limit=50, days=7)` — global or stock-tagged news
  * `get_metadata(symbol)`                 — ticker name, exchange, first/last date

Tiingo prices are generally cleaner than yfinance — fewer NaN gaps, properly
adjusted for splits/dividends, and consistent across the entire history.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx

from src.utils.config import TIINGO_API_KEY
from src.utils.db import cache_get, cache_set, log_api_call
from src.utils.rate_limit import TIINGO_LIMITER


BASE = "https://api.tiingo.com"
_TIMEOUT = 25


def _enabled() -> bool:
    return bool(TIINGO_API_KEY)


def _request(path: str, params: dict | None = None) -> Any:
    if not _enabled():
        return None
    TIINGO_LIMITER.acquire()
    headers = {"Authorization": f"Token {TIINGO_API_KEY}"}
    try:
        resp = httpx.get(f"{BASE}{path}", params=params or {}, headers=headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        log_api_call("tiingo", path, "success")
        return resp.json()
    except Exception as exc:
        log_api_call("tiingo", path, "error", str(exc))
        return None


# ── prices ───────────────────────────────────────────────────────────


def get_daily_prices(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
) -> list[dict] | None:
    """Daily OHLCV history. `start`/`end` are ISO dates (YYYY-MM-DD).

    Defaults to the past 2 years through today. Each row:
    {date, open, high, low, close, volume, adjOpen, adjHigh, adjLow,
     adjClose, adjVolume, divCash, splitFactor}.
    """
    sym = symbol.upper()
    if end is None:
        end = datetime.utcnow().date().isoformat()
    if start is None:
        start = (datetime.utcnow().date() - timedelta(days=2 * 365)).isoformat()
    key = f"tiingo:daily:{sym}:{start}:{end}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")
    rows = _request(f"/tiingo/daily/{sym}/prices", {
        "startDate": start, "endDate": end,
    })
    if not isinstance(rows, list):
        return None
    cache_set(key, {"rows": rows}, ttl_minutes=12 * 60)
    return rows


def get_intraday(symbol: str) -> dict | None:
    """Single most-recent IEX top-of-book quote.

    Returns: {ticker, timestamp, last, lastSize, bidPrice, askPrice,
              bidSize, askSize, prevClose, mid, ...}.
    """
    sym = symbol.upper()
    rows = _request(f"/iex/{sym}")
    if isinstance(rows, list) and rows:
        return rows[0]
    if isinstance(rows, dict):
        return rows
    return None


def get_metadata(symbol: str) -> dict | None:
    """Ticker metadata: name, exchange, history range, description."""
    sym = symbol.upper()
    key = f"tiingo:meta:{sym}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    row = _request(f"/tiingo/daily/{sym}")
    if not isinstance(row, dict):
        return None
    cache_set(key, row, ttl_minutes=7 * 24 * 60)
    return row


# ── news ─────────────────────────────────────────────────────────────


def get_news(
    symbol: str | None = None,
    *,
    limit: int = 50,
    days: int = 7,
) -> list[dict] | None:
    """News headlines, optionally filtered to a single ticker.

    **Note**: Tiingo's News API is a paid add-on as of 2025+ — on the free
    tier this returns None (the upstream 403 is silently logged). For news
    on the free tier, use `src.data.finnhub.get_company_news()` instead.

    Each row: {id, title, description, url, publishedDate, source,
               tickers: [str], tags: [str], crawlDate}.
    """
    cache_key = f"tiingo:news:{symbol or 'global'}:{limit}:{days}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached.get("rows")

    params: dict[str, str] = {"limit": str(limit), "sortBy": "publishedDate"}
    if symbol:
        params["tickers"] = symbol.upper()
    cutoff = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
    params["startDate"] = cutoff

    rows = _request("/tiingo/news", params)
    if not isinstance(rows, list):
        return None
    cache_set(cache_key, {"rows": rows}, ttl_minutes=30)
    return rows
