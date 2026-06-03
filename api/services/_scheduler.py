"""Tiny in-process scheduler for daily cron-style jobs.

No persistence — jobs run on the uvicorn process. If uvicorn restarts, the
next firing is at the next configured time. That's the right semantics for
prewarm-style jobs that just need to "happen daily, roughly at this time."

Why not apscheduler? The dependency is heavy and we have one job. A daemon
thread that sleeps until the next firing is sufficient.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_started: set[str] = set()
_lock = threading.Lock()


def schedule_daily_at(hour_et: int, minute_et: int, fn: Callable, *, name: str) -> bool:
    """Start a daemon thread that runs `fn()` every day at `hour_et:minute_et`
    in America/New_York time.

    Idempotent — calling twice with the same `name` only starts one thread.
    Returns True if a new thread was started, False if one already exists.

    On uvicorn restart, the thread dies; call this again on startup. The next
    firing will be at the next scheduled time, not immediately — if you need
    catch-up behavior, run `fn()` once at startup separately.
    """
    with _lock:
        if name in _started:
            return False
        _started.add(name)

    def _loop():
        while True:
            try:
                now = datetime.now(_ET)
                target = now.replace(hour=hour_et, minute=minute_et,
                                      second=0, microsecond=0)
                if target <= now:
                    target += timedelta(days=1)
                sleep_seconds = (target - now).total_seconds()
                logger.info(
                    "scheduler[%s]: sleeping %.0fs until next run at %s ET",
                    name, sleep_seconds, target.strftime("%Y-%m-%d %H:%M"),
                )
                time.sleep(sleep_seconds)
                logger.info("scheduler[%s]: running", name)
                fn()
                logger.info("scheduler[%s]: done", name)
            except Exception as e:
                logger.warning("scheduler[%s]: iteration failed %r — retrying in 60s", name, e)
                time.sleep(60)

    t = threading.Thread(target=_loop, name=f"sched:{name}", daemon=True)
    t.start()
    return True
