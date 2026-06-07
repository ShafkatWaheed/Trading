"""Tests for the phase-timing profiler.

The profiler MUST be safe — its own failures should never propagate to the
pipeline it's measuring, and a Timer block that raises must still record
its duration. These tests pin both behaviours.

All operations target the temp DB via the session-scoped `_isolated_test_db`
fixture in conftest.py — the production trading.db is untouched.
"""
from __future__ import annotations

import time

import pytest

from api.services import _profiler
from src.utils.db import get_connection, init_db


def _clean(run_id_prefix: str) -> None:
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM phase_timings WHERE run_id LIKE ?", (f"{run_id_prefix}%",))
    conn.commit()
    conn.close()


def test_start_run_returns_unique_ids():
    a = _profiler.start_run("test")
    b = _profiler.start_run("test")
    assert a != b
    assert a.startswith("test-")
    assert b.startswith("test-")


def test_timer_records_duration():
    run_id = _profiler.start_run("test_record")
    with _profiler.Timer(run_id, "sleep_a"):
        time.sleep(0.05)

    runs = _profiler.get_recent_runs(limit=5, label_prefix="test_record")
    assert len(runs) >= 1
    run = runs[0]
    assert run["run_id"] == run_id
    assert run["phase_count"] == 1
    phase = run["phases"][0]
    assert phase["phase"] == "sleep_a"
    assert phase["duration_ms"] >= 50    # 50ms sleep should round up
    assert phase["success"] == 1


def test_timer_records_when_block_raises():
    """A failing phase must still be recorded — that's the whole point of
    profiling, otherwise we'd never know about failed slow phases."""
    run_id = _profiler.start_run("test_raise")

    with pytest.raises(RuntimeError):
        with _profiler.Timer(run_id, "boom"):
            raise RuntimeError("synthetic")

    runs = _profiler.get_recent_runs(limit=5, label_prefix="test_raise")
    assert len(runs) == 1
    phase = runs[0]["phases"][0]
    assert phase["phase"] == "boom"
    assert phase["success"] == 0


def test_get_recent_runs_aggregates_phases_per_run():
    run_id = _profiler.start_run("test_multi")
    with _profiler.Timer(run_id, "p1"):
        time.sleep(0.01)
    with _profiler.Timer(run_id, "p2"):
        time.sleep(0.01)
    with _profiler.Timer(run_id, "p3"):
        time.sleep(0.01)

    runs = _profiler.get_recent_runs(limit=5, label_prefix="test_multi")
    assert len(runs) == 1
    run = runs[0]
    assert run["phase_count"] == 3
    assert {p["phase"] for p in run["phases"]} == {"p1", "p2", "p3"}
    assert run["total_ms"] == sum(p["duration_ms"] for p in run["phases"])


def test_get_recent_runs_orders_newest_first():
    a = _profiler.start_run("test_order")
    with _profiler.Timer(a, "first"):
        pass
    # Ensure a measurable gap — the ISO timestamp is microsecond-resolution
    # but back-to-back inserts could still tie.
    time.sleep(0.005)
    b = _profiler.start_run("test_order")
    with _profiler.Timer(b, "second"):
        pass

    runs = _profiler.get_recent_runs(limit=5, label_prefix="test_order")
    assert [r["run_id"] for r in runs[:2]] == [b, a]


def test_get_recent_runs_label_prefix_filters():
    """Pin that prefix filter isolates labels — a "brief-" run should not
    pollute "daily-" run reports, which matters once multiple pipelines
    share the same table."""
    a_id = _profiler.start_run("test_brf")
    b_id = _profiler.start_run("test_dly")
    with _profiler.Timer(a_id, "one"):
        pass
    with _profiler.Timer(b_id, "one"):
        pass

    only_brf = _profiler.get_recent_runs(limit=10, label_prefix="test_brf")
    only_dly = _profiler.get_recent_runs(limit=10, label_prefix="test_dly")
    assert all(r["run_id"].startswith("test_brf-") for r in only_brf)
    assert all(r["run_id"].startswith("test_dly-") for r in only_dly)
    assert any(r["run_id"] == a_id for r in only_brf)
    assert any(r["run_id"] == b_id for r in only_dly)


def test_timer_note_round_trips():
    run_id = _profiler.start_run("test_note")
    with _profiler.Timer(run_id, "annotated", note="fallback path"):
        pass

    runs = _profiler.get_recent_runs(limit=5, label_prefix="test_note")
    phase = runs[0]["phases"][0]
    assert phase["note"] == "fallback path"
