"""Tiny in-process background job dispatcher with dedup.

Used by endpoints that want a "cached-or-202" pattern: return the cached
payload instantly, or kick off generation in the background and return a
"computing" placeholder so the client can poll.

No persistence — process restart drops in-flight jobs. That's fine: the
underlying generation function is itself idempotent (writes to the shared
cache table). On next request from any client, the work will either be
done (cache hit) or restart cleanly.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)

_in_flight: set[str] = set()
_lock = threading.Lock()


def kick(key: str, fn: Callable, *args, **kwargs) -> bool:
    """Run `fn(*args, **kwargs)` in a background thread if not already
    running for the same key. Returns True if a new job was started, False
    if a job for this key is already in flight.

    Thread cleans up its entry from `_in_flight` on completion.
    """
    with _lock:
        if key in _in_flight:
            return False
        _in_flight.add(key)

    def _runner():
        try:
            fn(*args, **kwargs)
        except Exception as e:
            logger.warning("background job %s failed: %r", key, e)
        finally:
            with _lock:
                _in_flight.discard(key)

    t = threading.Thread(target=_runner, name=f"bgjob:{key}", daemon=True)
    t.start()
    return True


def is_in_flight(key: str) -> bool:
    with _lock:
        return key in _in_flight
