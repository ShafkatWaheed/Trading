"""Tests for the brief partial-outputs scratch table.

The progressive-poll path writes phase outputs here as the brief generates,
and the GET /brief stub reads them back. These tests pin the round-trip,
per-job isolation, and serialization safety net.

All operations target the temp DB via the session-scoped `_isolated_test_db`
fixture in conftest.py — the production trading.db is untouched.
"""
from __future__ import annotations

from api.services import _partial_outputs
from src.utils.db import get_connection, init_db


_JOB_A = "test_bpo:job-A"
_JOB_B = "test_bpo:job-B"


def _clean() -> None:
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM brief_partial_outputs WHERE job_key LIKE 'test_bpo:%'")
    conn.commit()
    conn.close()


def test_get_returns_empty_on_miss():
    _clean()
    assert _partial_outputs.get_partials(_JOB_A) == {}


def test_set_then_get_round_trip():
    _clean()
    payload = {"query": "AI infra capex", "convergence": [{"sector": "Tech"}]}
    _partial_outputs.set_partial(_JOB_A, "lens", payload)

    got = _partial_outputs.get_partials(_JOB_A)
    assert "lens" in got
    assert got["lens"] == payload


def test_multiple_phases_round_trip():
    _clean()
    _partial_outputs.set_partial(_JOB_A, "lens", {"q": "x"})
    _partial_outputs.set_partial(_JOB_A, "picks_skeleton", {"picks": [{"symbol": "AAPL"}]})
    _partial_outputs.set_partial(_JOB_A, "narrate", {"closing": "see you tomorrow"})

    got = _partial_outputs.get_partials(_JOB_A)
    assert set(got.keys()) == {"lens", "picks_skeleton", "narrate"}
    assert got["picks_skeleton"]["picks"][0]["symbol"] == "AAPL"


def test_set_overwrites_existing_phase():
    _clean()
    _partial_outputs.set_partial(_JOB_A, "lens", {"v": "old"})
    _partial_outputs.set_partial(_JOB_A, "lens", {"v": "new"})

    got = _partial_outputs.get_partials(_JOB_A)
    assert got["lens"] == {"v": "new"}


def test_jobs_are_isolated():
    """Two concurrent brief jobs must not see each other's partials."""
    _clean()
    _partial_outputs.set_partial(_JOB_A, "lens", {"sym": "A"})
    _partial_outputs.set_partial(_JOB_B, "lens", {"sym": "B"})

    assert _partial_outputs.get_partials(_JOB_A)["lens"] == {"sym": "A"}
    assert _partial_outputs.get_partials(_JOB_B)["lens"] == {"sym": "B"}


def test_clear_only_wipes_named_job():
    _clean()
    _partial_outputs.set_partial(_JOB_A, "lens", {"x": 1})
    _partial_outputs.set_partial(_JOB_A, "narrate", {"x": 1})
    _partial_outputs.set_partial(_JOB_B, "lens", {"x": 2})

    n = _partial_outputs.clear(_JOB_A)
    assert n == 2

    assert _partial_outputs.get_partials(_JOB_A) == {}
    assert _partial_outputs.get_partials(_JOB_B) == {"lens": {"x": 2}}


def test_clear_no_match_returns_zero():
    _clean()
    assert _partial_outputs.clear("test_bpo:never-existed") == 0


def test_non_serializable_payload_does_not_raise():
    """set_partial must swallow serialization failures — the brief pipeline
    must never break because the partials cache choked on an exotic object."""
    _clean()

    class _NotSerializable:
        pass

    # No raise. Cache becomes a no-op for this entry.
    _partial_outputs.set_partial(_JOB_A, "weird", {"obj": _NotSerializable()})
    # No raise on read either.
    _partial_outputs.get_partials(_JOB_A)
