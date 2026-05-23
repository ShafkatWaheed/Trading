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
