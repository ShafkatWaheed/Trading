"""Finnhub data provider — analyst revisions, calendars, structured news.

Free tier: 60 calls/min, no daily cap. https://finnhub.io/dashboard

Exposed shapes (all return `dict | list[dict] | None`; None means
not-available / API key missing / fetch error — never raises):

  * `get_eps_estimates(symbol)`           — quarterly EPS estimates with trend
  * `get_recommendation_trend(symbol)`    — analyst buy/hold/sell over time
  * `get_upgrades_downgrades(symbol)`     — rating actions with date + firm
  * `get_company_news(symbol, days=30)`   — stock-tagged news with sentiment
  * `get_earnings_calendar(days_ahead=7)` — upcoming earnings
  * `get_ipo_calendar(days_ahead=30)`     — upcoming IPOs

Cache TTL: 1h for news/calendars, 24h for estimates/recommendations.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx

from src.utils.config import FINNHUB_API_KEY
from src.utils.db import cache_get, cache_set, log_api_call
from src.utils.rate_limit import FINNHUB_LIMITER


BASE = "https://finnhub.io/api/v1"
_TIMEOUT = 20


def _enabled() -> bool:
    return bool(FINNHUB_API_KEY)


def _request(path: str, params: dict | None = None) -> Any:
    """GET request with rate limit, error logging, no exceptions."""
    if not _enabled():
        return None
    params = dict(params or {})
    params["token"] = FINNHUB_API_KEY
    FINNHUB_LIMITER.acquire()
    try:
        resp = httpx.get(f"{BASE}{path}", params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        log_api_call("finnhub", path, "success")
        return resp.json()
    except Exception as exc:
        log_api_call("finnhub", path, "error", str(exc))
        return None


# ── analyst signals ──────────────────────────────────────────────────


def get_eps_estimates(symbol: str) -> list[dict] | None:
    """Quarterly EPS estimates — high/low/avg/count of analysts.

    Each row: {period, epsAvg, epsHigh, epsLow, numberAnalysts, ...}.
    Return None if API disabled or fetch fails.
    """
    key = f"finnhub:eps_est:{symbol.upper()}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")
    data = _request("/stock/eps-estimate", {"symbol": symbol.upper(), "freq": "quarterly"})
    if not data or "data" not in data:
        return None
    rows = data.get("data") or []
    cache_set(key, {"rows": rows}, ttl_minutes=24 * 60)
    return rows


def get_recommendation_trend(symbol: str) -> list[dict] | None:
    """Analyst recommendation snapshots over time.

    Each row: {period, strongBuy, buy, hold, sell, strongSell}.
    """
    key = f"finnhub:rec_trend:{symbol.upper()}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")
    rows = _request("/stock/recommendation", {"symbol": symbol.upper()})
    if rows is None or not isinstance(rows, list):
        return None
    cache_set(key, {"rows": rows}, ttl_minutes=24 * 60)
    return rows


def get_upgrades_downgrades(symbol: str) -> list[dict] | None:
    """Recent rating actions (action: "up"/"down"/"main"/"init").

    Each row: {symbol, fromGrade, toGrade, company, action, gradeTime}.
    `gradeTime` is a unix timestamp.
    """
    key = f"finnhub:upgrades:{symbol.upper()}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")
    rows = _request("/stock/upgrade-downgrade", {"symbol": symbol.upper()})
    if rows is None or not isinstance(rows, list):
        return None
    cache_set(key, {"rows": rows}, ttl_minutes=24 * 60)
    return rows


# ── news & calendars ─────────────────────────────────────────────────


def get_company_news(symbol: str, days: int = 30) -> list[dict] | None:
    """Stock-tagged news headlines for the past `days`.

    Each row: {datetime, headline, summary, source, url, category, ...}.
    """
    symbol = symbol.upper()
    key = f"finnhub:news:{symbol}:{days}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")
    to_date = datetime.utcnow().date()
    from_date = to_date - timedelta(days=days)
    rows = _request("/company-news", {
        "symbol": symbol,
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
    })
    if rows is None or not isinstance(rows, list):
        return None
    cache_set(key, {"rows": rows}, ttl_minutes=60)
    return rows


def get_earnings_calendar(days_ahead: int = 7) -> list[dict] | None:
    """Upcoming earnings releases in the next `days_ahead` days.

    Each row: {symbol, date, hour ('amc'/'bmo'), epsEstimate, revenueEstimate, ...}.
    """
    key = f"finnhub:earn_cal:{days_ahead}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")
    today = datetime.utcnow().date()
    data = _request("/calendar/earnings", {
        "from": today.isoformat(),
        "to": (today + timedelta(days=days_ahead)).isoformat(),
    })
    if not data or "earningsCalendar" not in data:
        return None
    rows = data.get("earningsCalendar") or []
    cache_set(key, {"rows": rows}, ttl_minutes=60)
    return rows


def get_ipo_calendar(days_ahead: int = 30) -> list[dict] | None:
    """Upcoming IPOs in the window.

    Each row: {symbol, name, date, exchange, numberOfShares, totalSharesValue, price}.
    """
    key = f"finnhub:ipo_cal:{days_ahead}"
    cached = cache_get(key)
    if cached is not None:
        return cached.get("rows")
    today = datetime.utcnow().date()
    data = _request("/calendar/ipo", {
        "from": today.isoformat(),
        "to": (today + timedelta(days=days_ahead)).isoformat(),
    })
    if not data or "ipoCalendar" not in data:
        return None
    rows = data.get("ipoCalendar") or []
    cache_set(key, {"rows": rows}, ttl_minutes=60)
    return rows
