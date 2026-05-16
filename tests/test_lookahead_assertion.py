"""Tests for the point-in-time lookahead assertion (Wave 1)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.analysis.edge_validator import LookaheadViolation, assert_no_lookahead
from src.analysis.sector_signals._shared import SignalReading


def _r(*, as_of: str, available_at: str) -> SignalReading:
    return SignalReading(
        ticker="X", sector=None, signal_name="test",
        value=Decimal("1"), z_score=None,
        direction="neutral", confidence="low",
        as_of=as_of, available_at=available_at,
        point_in_time_lag_days=0, source="test",
    )


def test_no_violation_when_all_available_at_le_decision():
    rs = [
        _r(as_of="2026-05-10T00:00:00Z", available_at="2026-05-10T00:00:00Z"),
        _r(as_of="2026-05-12T00:00:00Z", available_at="2026-05-13T00:00:00Z"),
    ]
    # Should not raise
    assert_no_lookahead(rs, decision_timestamp="2026-05-15T00:00:00Z")


def test_raises_when_a_reading_is_in_the_future():
    rs = [
        _r(as_of="2026-05-10T00:00:00Z", available_at="2026-05-10T00:00:00Z"),
        _r(as_of="2026-05-20T00:00:00Z", available_at="2026-05-20T00:00:00Z"),  # future!
    ]
    with pytest.raises(LookaheadViolation) as exc_info:
        assert_no_lookahead(rs, decision_timestamp="2026-05-15T00:00:00Z")
    msg = str(exc_info.value)
    assert "test" in msg                          # signal_name surfaced
    assert "2026-05-20" in msg                    # offending date surfaced


def test_raises_on_equal_only_when_strict():
    # By default, available_at == decision_timestamp is allowed (boundary).
    rs = [_r(as_of="2026-05-15T00:00:00Z", available_at="2026-05-15T00:00:00Z")]
    assert_no_lookahead(rs, decision_timestamp="2026-05-15T00:00:00Z")
    # When strict=True, equal is rejected.
    with pytest.raises(LookaheadViolation):
        assert_no_lookahead(rs, decision_timestamp="2026-05-15T00:00:00Z", strict=True)


def test_empty_list_is_a_noop():
    assert_no_lookahead([], decision_timestamp="2026-05-15T00:00:00Z")


def test_aggregates_multiple_violations_in_message():
    rs = [
        _r(as_of="2026-05-20T00:00:00Z", available_at="2026-05-21T00:00:00Z"),
        _r(as_of="2026-05-22T00:00:00Z", available_at="2026-05-23T00:00:00Z"),
    ]
    with pytest.raises(LookaheadViolation) as exc_info:
        assert_no_lookahead(rs, decision_timestamp="2026-05-15T00:00:00Z")
    msg = str(exc_info.value)
    assert "2 violation" in msg.lower() or "2 readings" in msg.lower()
