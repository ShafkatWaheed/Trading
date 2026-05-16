"""Process-wide yfinance memoization for the analysis layer.

The deep-dive walks ~14 signals, several of which each call `yf.Ticker(sym).info`
just to read `sector` (e.g. geopolitical, disruption). Without sharing, every
signal re-constructs a Ticker and hits Yahoo again — 5–10 extra HTTP roundtrips
on a cold deep-dive.

This module wraps yfinance calls with a short-TTL in-memory cache keyed by
symbol so all signal evaluators within a single request share one fetch.

TTL is short (60s) so subsequent requests get fresh data after the user has
moved off the page. The SQLite cache in `src.data.market` is the long-term
cache; this is purely the per-request hot path.
"""
from __future__ import annotations

import threading
import time
from typing import Any


_TTL_SECONDS = 60.0
_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}


def _get_or_compute(key: str, compute) -> Any:
    """Return cached value or call `compute()` and cache the result.

    Errors propagate to the caller; we only cache successful returns.
    """
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit and (now - hit[0]) < _TTL_SECONDS:
            return hit[1]
    # Compute outside the lock — yf calls can be slow and we don't want to
    # block other symbols' lookups while one resolves.
    val = compute()
    with _lock:
        _store[key] = (time.monotonic(), val)
    return val


def get_info(symbol: str) -> dict:
    """Memoized `yf.Ticker(symbol).info`. Returns {} on failure (never raises)."""
    def _compute() -> dict:
        try:
            import yfinance as yf
            info = yf.Ticker(symbol).info
            return info or {}
        except Exception:
            return {}
    return _get_or_compute(f"info:{symbol}", _compute)


def get_earnings_dates(symbol: str):
    """Memoized `yf.Ticker(symbol).earnings_dates`. Returns None on failure."""
    def _compute():
        try:
            import yfinance as yf
            return yf.Ticker(symbol).earnings_dates
        except Exception:
            return None
    return _get_or_compute(f"earnings_dates:{symbol}", _compute)


def get_recommendations(symbol: str):
    """Memoized `yf.Ticker(symbol).recommendations`. Returns None on failure."""
    def _compute():
        try:
            import yfinance as yf
            return yf.Ticker(symbol).recommendations
        except Exception:
            return None
    return _get_or_compute(f"recommendations:{symbol}", _compute)


def get_institutional_holders(symbol: str):
    """Memoized `yf.Ticker(symbol).institutional_holders`. Returns None on failure."""
    def _compute():
        try:
            import yfinance as yf
            return yf.Ticker(symbol).institutional_holders
        except Exception:
            return None
    return _get_or_compute(f"institutional_holders:{symbol}", _compute)


def get_insider_transactions(symbol: str):
    """Memoized `yf.Ticker(symbol).insider_transactions`. Returns None on failure."""
    def _compute():
        try:
            import yfinance as yf
            return yf.Ticker(symbol).insider_transactions
        except Exception:
            return None
    return _get_or_compute(f"insider_transactions:{symbol}", _compute)


def get_history(symbol: str, period: str = "2y"):
    """Memoized `yf.download(symbol, period=...)`. Returns None on failure."""
    def _compute():
        try:
            import yfinance as yf
            return yf.download(symbol, period=period, progress=False, auto_adjust=True)
        except Exception:
            return None
    return _get_or_compute(f"history:{symbol}:{period}", _compute)
