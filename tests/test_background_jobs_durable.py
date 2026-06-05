"""Tests for the SQLite-backed background-job tracker."""
from __future__ import annotations

import time

from api.services._background_jobs import (
    force_restart,
    get_job_status,
    heartbeat,
    is_in_flight,
    kick,
    reap_stale_jobs,
)
from src.utils.db import get_connection, init_db


def _clean(key: str) -> None:
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM background_jobs WHERE key = ?", (key,))
    conn.commit()
    conn.close()


def test_kick_starts_a_job():
    key = "test:kick:basic"
    _clean(key)

    ran = []
    def job():
        ran.append(1)

    started = kick(key, job)
    assert started is True
    # Daemon thread may need a moment to complete
    for _ in range(20):
        if get_job_status(key)["status"] == "done": break
        time.sleep(0.05)

    status = get_job_status(key)
    assert status["status"] == "done"
    assert status["progress_pct"] == 100
    assert ran == [1]


def test_kick_dedupes_concurrent_jobs():
    key = "test:kick:dedupe"
    _clean(key)

    def slow_job():
        time.sleep(0.5)

    first = kick(key, slow_job)
    second = kick(key, slow_job)
    assert first is True
    assert second is False    # already running, second kick rejected


def test_heartbeat_updates_phase_and_progress():
    key = "test:heartbeat"
    _clean(key)

    def job():
        heartbeat(key, phase="lens", progress_pct=20)
        heartbeat(key, phase="discovery", progress_pct=50)

    kick(key, job)
    time.sleep(0.2)
    status = get_job_status(key)
    assert status["progress_pct"] >= 50
    assert status["current_phase"] in {"discovery", None}    # may have finished


def test_failed_job_records_error():
    key = "test:failed"
    _clean(key)

    def boom():
        raise RuntimeError("synthetic failure")

    kick(key, boom)
    time.sleep(0.2)
    status = get_job_status(key)
    assert status["status"] == "failed"
    assert "RuntimeError" in (status["error"] or "")
    assert "synthetic failure" in (status["error"] or "")


def test_reap_stale_jobs_marks_old_running_jobs_failed():
    key = "test:reap"
    _clean(key)

    init_db()
    # Insert a row that looks like a stuck job (heartbeat from yesterday)
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO background_jobs (key, status, started_at, last_heartbeat, progress_pct)
        VALUES (?, 'running', '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00', 30)
        """,
        (key,),
    )
    conn.commit()
    conn.close()

    n = reap_stale_jobs(stale_after_minutes=5)
    assert n >= 1
    status = get_job_status(key)
    assert status["status"] == "failed"
    assert "watchdog" in (status["error"] or "").lower()


def test_after_reap_kick_can_restart():
    """Once a stale job is reaped, the next kick should succeed (status was 'failed', so a fresh start is allowed)."""
    key = "test:reap-restart"
    _clean(key)

    init_db()
    conn = get_connection()
    conn.execute(
        "INSERT INTO background_jobs (key, status, started_at, last_heartbeat, progress_pct) "
        "VALUES (?, 'running', '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00', 30)",
        (key,),
    )
    conn.commit()
    conn.close()

    ran = []
    def job():
        ran.append(1)

    # kick() should reap then restart
    started = kick(key, job)
    assert started is True
    time.sleep(0.2)
    assert ran == [1]


def test_force_restart_wipes_running_state():
    key = "test:force-restart"
    _clean(key)

    def slow():
        time.sleep(0.3)
    kick(key, slow)
    assert is_in_flight(key)

    force_restart(key)
    assert not is_in_flight(key)
    # New kick should be allowed
    assert kick(key, lambda: None) is True


def test_is_in_flight_false_for_nonexistent_key():
    assert is_in_flight("test:never-existed") is False
    assert get_job_status("test:never-existed") is None
