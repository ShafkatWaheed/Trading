"""Token bucket rate limiter + cross-process status read from the api_log table."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


class RateLimiter:

    def __init__(self, max_calls: int, period_seconds: int) -> None:
        self.max_calls = max_calls
        self.period = period_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._prune(now)
                if len(self._timestamps) < self.max_calls:
                    self._timestamps.append(now)
                    return
                wait = self._timestamps[0] + self.period - now
            if wait > 0:
                time.sleep(wait)

    def can_proceed(self) -> bool:
        with self._lock:
            self._prune(time.monotonic())
            return len(self._timestamps) < self.max_calls

    def _prune(self, now: float) -> None:
        cutoff = now - self.period
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()


# Pre-configured limiters for each provider
AV_LIMITER = RateLimiter(max_calls=1, period_seconds=15)
POLYGON_LIMITER = RateLimiter(max_calls=5, period_seconds=60)
SEC_LIMITER = RateLimiter(max_calls=10, period_seconds=1)
# Finnhub free tier: 60 calls/min — leave headroom at 50.
FINNHUB_LIMITER = RateLimiter(max_calls=50, period_seconds=60)
# Tiingo free tier: 1,000 calls/day — pace at ~40/min to spread the budget.
TIINGO_LIMITER = RateLimiter(max_calls=40, period_seconds=60)
# FRED has no published rate limit on the free tier, but be a good citizen.
FRED_LIMITER = RateLimiter(max_calls=120, period_seconds=60)


# --- Rate-limit status (read from api_log) -----------------------------------
#
# These are the *published* free-tier limits we count against, NOT the in-process
# limiter settings. Source keys match the strings passed to log_api_call() in
# each provider — see `grep log_api_call src/`.
#
# `max_calls=None` means we don't have a published limit to check against. We
# still show the call count (good for visibility) but never flag the source.

@dataclass(frozen=True)
class _ApiSpec:
    key: str             # source string in api_log
    display_name: str
    window_seconds: int  # window we count over (also for untracked, for visibility)
    max_calls: int | None  # None => untracked


_API_SPECS: tuple[_ApiSpec, ...] = (
    _ApiSpec("alphavantage", "Alpha Vantage",  60, 5),     # free tier: 5/min
    _ApiSpec("polygon",      "Polygon.io",     60, 5),     # free tier: 5/min
    _ApiSpec("sec_edgar",    "SEC EDGAR",       1, 10),    # 10/sec hard limit
    _ApiSpec("yahoo",        "Yahoo Finance",  60, None),  # no published limit
    _ApiSpec("tavily",       "Tavily",         60, None),  # plan-dependent
    _ApiSpec("exa",          "Exa",            60, None),  # plan-dependent
    _ApiSpec("congress",     "Capitol Trades", 60, None),  # scraper, no published limit
    _ApiSpec("finnhub",      "Finnhub",        60, 60),    # free tier: 60/min
    _ApiSpec("tiingo",       "Tiingo",      86_400, 1000), # free tier: 1k/day
    _ApiSpec("fred",         "FRED",           60, None),  # no published limit
)


@dataclass(frozen=True)
class RateLimitStatus:
    source: str          # display name
    key: str             # api_log source key
    used: int            # calls observed in the window
    capacity: int | None # published limit (None => untracked)
    window_seconds: int
    status: str          # "ok" | "warning" | "limited" | "untracked"

    @property
    def is_limited(self) -> bool:
        return self.status == "limited"


def get_rate_limit_status() -> list[RateLimitStatus]:
    """Return current rate-limit status for every known data source.

    Reads from the persistent api_log table (cross-process), not in-memory
    limiters. Status thresholds:
      * `used >= capacity`        -> "limited"
      * `used >= 0.8 * capacity`  -> "warning"
      * `capacity is None`        -> "untracked"
      * else                      -> "ok"
    """
    # Local import to keep the rate-limit module callable in contexts where
    # the DB hasn't been initialised yet (the helper short-circuits in that case).
    from src.utils.db import get_connection

    now = datetime.now(timezone.utc)
    out: list[RateLimitStatus] = []

    try:
        conn = get_connection()
    except Exception:
        # DB not available -> report all sources as untracked rather than crash.
        for spec in _API_SPECS:
            out.append(RateLimitStatus(
                source=spec.display_name, key=spec.key, used=0,
                capacity=spec.max_calls, window_seconds=spec.window_seconds,
                status="untracked",
            ))
        return out

    for spec in _API_SPECS:
        cutoff = (now - timedelta(seconds=spec.window_seconds)).isoformat()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM api_log WHERE source = ? AND timestamp >= ?",
                (spec.key, cutoff),
            ).fetchone()
            used = int(row[0]) if row else 0
        except Exception:
            used = 0

        if spec.max_calls is None:
            status = "untracked"
        elif used >= spec.max_calls:
            status = "limited"
        elif used >= max(1, int(spec.max_calls * 0.8)):
            status = "warning"
        else:
            status = "ok"

        out.append(RateLimitStatus(
            source=spec.display_name, key=spec.key, used=used,
            capacity=spec.max_calls, window_seconds=spec.window_seconds,
            status=status,
        ))

    return out
