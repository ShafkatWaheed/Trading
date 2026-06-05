"""Durable background-job tracker.

Replaces the previous in-memory _in_flight set. Job state persists in
SQLite so that:
  - Stuck jobs (Claude CLI hangs) get reaped by a watchdog after 5min
    of no heartbeat
  - Uvicorn restart doesn't drop in-flight tracking — restarted process
    sees stale 'running' rows and reaps them
  - The API stub can read live progress from the job row

Public API:
  - kick(key, fn, *args, **kwargs) -> bool
      Start a job if not already running. Reaps stale jobs first.
      Returns True if started, False if already running.
  - is_in_flight(key) -> bool
      Same semantics as before.
  - heartbeat(key, *, phase=None, progress_pct=None) -> None
      Called by the job body between phases to signal aliveness +
      surface progress.
  - get_job_status(key) -> dict | None
      Returns {status, current_phase, progress_pct, started_at,
      last_heartbeat, elapsed_s, error} or None if no row.
  - reap_stale_jobs(*, stale_after_minutes=5) -> int
      Mark any 'running' job whose last_heartbeat is older than the
      threshold as 'failed' with error='watchdog timeout'.
      Returns count reaped. Idempotent.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

from src.utils.db import get_connection, init_db

logger = logging.getLogger(__name__)

_STALE_AFTER_MIN = 5


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def reap_stale_jobs(*, stale_after_minutes: int = _STALE_AFTER_MIN) -> int:
    """Mark stuck 'running' jobs as 'failed'. Call before kicking new work."""
    init_db()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(minutes=stale_after_minutes)).isoformat()
    now = _now_iso()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            UPDATE background_jobs
               SET status = 'failed',
                   finished_at = ?,
                   error = COALESCE(error, '') || '; watchdog reaped (no heartbeat ' || ? || ')'
             WHERE status = 'running' AND last_heartbeat < ?
            """,
            (now, str(stale_after_minutes) + 'min', cutoff),
        )
        n = cur.rowcount
        conn.commit()
        if n:
            logger.warning("background watchdog reaped %d stale jobs", n)
        return n
    finally:
        conn.close()


def is_in_flight(key: str) -> bool:
    """True if there is a running, non-stale job for this key.

    Reaps stale jobs as a side effect so callers always see fresh status.
    """
    reap_stale_jobs()
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status FROM background_jobs WHERE key = ?", (key,)
        ).fetchone()
    finally:
        conn.close()
    return row is not None and row[0] == "running"


def get_job_status(key: str) -> dict | None:
    """Return live job status including elapsed time."""
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT status, current_phase, progress_pct, started_at,
                   last_heartbeat, error, finished_at
              FROM background_jobs WHERE key = ?
            """,
            (key,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    started = row["started_at"]
    try:
        started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        elapsed_s = int((datetime.now(tz=timezone.utc) - started_dt).total_seconds())
    except Exception:
        elapsed_s = 0
    return {
        "status":         row["status"],
        "current_phase":  row["current_phase"],
        "progress_pct":   row["progress_pct"] or 0,
        "started_at":     row["started_at"],
        "last_heartbeat": row["last_heartbeat"],
        "elapsed_s":      elapsed_s,
        "error":          row["error"],
        "finished_at":    row["finished_at"],
    }


def heartbeat(
    key: str, *, phase: str | None = None, progress_pct: int | None = None
) -> None:
    """Update last_heartbeat (+ optional phase/progress) for an in-flight job.

    Called by the job body to signal liveness and surface progress.
    No-op if the row doesn't exist (e.g. job was reaped or never started).
    """
    init_db()
    now = _now_iso()
    sets = ["last_heartbeat = ?"]
    args: list = [now]
    if phase is not None:
        sets.append("current_phase = ?")
        args.append(phase)
    if progress_pct is not None:
        sets.append("progress_pct = ?")
        args.append(max(0, min(100, int(progress_pct))))
    args.append(key)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE background_jobs SET {', '.join(sets)} WHERE key = ? AND status = 'running'",
            tuple(args),
        )
        conn.commit()
    finally:
        conn.close()


def _start_job_row(key: str) -> bool:
    """Insert a fresh 'running' row. Returns False if one already exists.

    Atomic via INSERT OR IGNORE — if a concurrent caller raced, only one wins.
    """
    init_db()
    now = _now_iso()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO background_jobs
              (key, status, started_at, last_heartbeat, progress_pct)
            VALUES (?, 'running', ?, ?, 0)
            """,
            (key, now, now),
        )
        conn.commit()
        if cur.rowcount == 0:
            # Existing row — but it might be 'done' or 'failed' (stale completion).
            # Allow restart only if status != 'running'.
            row = conn.execute(
                "SELECT status FROM background_jobs WHERE key = ?", (key,)
            ).fetchone()
            if row and row[0] != "running":
                conn.execute(
                    """
                    UPDATE background_jobs
                       SET status='running', started_at=?, last_heartbeat=?,
                           current_phase=NULL, progress_pct=0,
                           error=NULL, finished_at=NULL
                     WHERE key = ?
                    """,
                    (now, now, key),
                )
                conn.commit()
                return True
            return False
        return True
    finally:
        conn.close()


def _finish_job_row(key: str, *, status: str, error: str | None = None) -> None:
    init_db()
    now = _now_iso()
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE background_jobs
               SET status=?, finished_at=?, last_heartbeat=?,
                   error = COALESCE(?, error),
                   progress_pct = CASE WHEN ? = 'done' THEN 100 ELSE progress_pct END
             WHERE key = ?
            """,
            (status, now, now, error, status, key),
        )
        conn.commit()
    finally:
        conn.close()


def kick(key: str, fn: Callable, *args, **kwargs) -> bool:
    """Start `fn(*args, **kwargs)` in a background thread iff not already running.

    Reaps stale jobs first, then atomically claims the key. Returns True if
    a new thread was started, False if the job was already in flight.
    """
    reap_stale_jobs()
    if not _start_job_row(key):
        return False

    def _runner():
        try:
            fn(*args, **kwargs)
            _finish_job_row(key, status="done")
        except Exception as e:
            logger.warning("background job %s failed: %r", key, e)
            _finish_job_row(key, status="failed", error=f"{type(e).__name__}: {e}"[:500])

    threading.Thread(target=_runner, name=f"bgjob:{key}", daemon=True).start()
    return True


def force_restart(key: str) -> None:
    """Wipe the existing row so the next kick() will start fresh.

    Use sparingly — only when the user explicitly asks to cancel.
    Does NOT kill the underlying subprocess (Python threads can't).
    """
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM background_jobs WHERE key = ?", (key,))
        conn.commit()
    finally:
        conn.close()
