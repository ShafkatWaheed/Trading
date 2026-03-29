"""Token bucket rate limiter."""

import threading
import time
from collections import deque


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
