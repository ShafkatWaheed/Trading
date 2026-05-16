"""Tests for the manual-refresh service."""

from __future__ import annotations

import time

import pytest

from api.services import refresh_service
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _setup_db():
    init_db()
    yield
    # Clean up test-only refresh rows
    conn = get_connection()
    try:
        conn.execute("DELETE FROM refresh_jobs WHERE kind LIKE 'test_%'")
        conn.commit()
    finally:
        conn.close()


def test_list_kinds_returns_all_registered():
    out = refresh_service.list_kinds()
    kinds = {row["kind"] for row in out}
    assert "universe" in kinds
    assert "industries" in kinds
    assert "peers" in kinds
    assert "causal" in kinds
    assert "tenk_mining" in kinds
    assert "13f_overlap" in kinds
    assert "freshness" in kinds


def test_unknown_kind_raises():
    with pytest.raises(KeyError):
        refresh_service.start_job("not_a_real_kind")


def test_start_job_creates_row_and_returns_id(monkeypatch):
    # Replace the actual runner with a fast no-op
    sentinel_called = []

    def fake_runner() -> dict:
        sentinel_called.append(True)
        return {"ok": True}

    def fake_prog() -> tuple[int, int]:
        return 5, 10

    monkeypatch.setitem(
        refresh_service.KIND_REGISTRY,
        "test_kind",
        (fake_runner, fake_prog, "test description"),
    )

    job = refresh_service.start_job("test_kind")
    assert job["id"] > 0
    assert job["kind"] == "test_kind"
    assert job["status"] in ("queued", "running", "done")

    # Wait for worker to finish (fast)
    for _ in range(40):
        time.sleep(0.1)
        latest = refresh_service.get_job(job["id"])
        if latest["status"] in ("done", "failed"):
            break

    final = refresh_service.get_job(job["id"])
    assert final["status"] == "done"
    assert sentinel_called == [True]


def test_kind_already_running_rejects_second_start(monkeypatch):
    block = []

    def slow_runner() -> dict:
        # Block long enough for the second call to land
        while not block:
            time.sleep(0.05)
        return {"ok": True}

    monkeypatch.setitem(
        refresh_service.KIND_REGISTRY,
        "test_block",
        (slow_runner, lambda: (0, 0), ""),
    )

    job1 = refresh_service.start_job("test_block")
    # Briefly wait for the worker to flip the row to 'running'
    for _ in range(20):
        if refresh_service.get_job(job1["id"])["status"] == "running":
            break
        time.sleep(0.05)

    with pytest.raises(refresh_service.KindAlreadyRunning):
        refresh_service.start_job("test_block")

    # Unblock and let the first one finish
    block.append(1)
    for _ in range(40):
        if refresh_service.get_job(job1["id"])["status"] == "done":
            break
        time.sleep(0.1)


def test_failed_runner_marks_status_failed(monkeypatch):
    def boom() -> dict:
        raise RuntimeError("synthetic failure")

    monkeypatch.setitem(
        refresh_service.KIND_REGISTRY,
        "test_fail",
        (boom, lambda: (0, 0), ""),
    )

    job = refresh_service.start_job("test_fail")
    for _ in range(40):
        time.sleep(0.1)
        if refresh_service.get_job(job["id"])["status"] in ("done", "failed"):
            break

    final = refresh_service.get_job(job["id"])
    assert final["status"] == "failed"
    assert "synthetic failure" in (final["error"] or "")


def test_progress_updates_during_run(monkeypatch):
    progress_state = {"i": 0}

    def slow_runner() -> dict:
        for _ in range(6):
            time.sleep(0.05)
            progress_state["i"] += 1
        return {"ok": True}

    def prog() -> tuple[int, int]:
        return progress_state["i"], 6

    monkeypatch.setitem(
        refresh_service.KIND_REGISTRY,
        "test_prog",
        (slow_runner, prog, ""),
    )

    job = refresh_service.start_job("test_prog")
    # Wait for completion
    for _ in range(60):
        time.sleep(0.1)
        if refresh_service.get_job(job["id"])["status"] == "done":
            break

    final = refresh_service.get_job(job["id"])
    assert final["status"] == "done"
    assert final["processed"] == 6
    assert final["total"] == 6


def test_quality_snapshot_returns_expected_keys():
    snap = refresh_service.quality_snapshot()
    assert "universe" in snap
    assert "industries" in snap
    assert "peers" in snap
    assert "relations" in snap
    assert "commodity_exposures" in snap
    assert "institutional" in snap
    assert "freshness" in snap
    assert "latest_jobs" in snap
    assert "total" in snap["universe"]
    assert "by_tier" in snap["universe"]
