"""Integration: backtester must reject SignalReading with future availability."""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.analysis.edge_validator import LookaheadViolation
from src.analysis.backtester import check_readings_point_in_time
from src.analysis.sector_signals._shared import SignalReading


def _r(as_of: str, available_at: str) -> SignalReading:
    return SignalReading(
        ticker="X", sector=None, signal_name="dummy",
        value=Decimal("1"), z_score=None, direction="neutral",
        confidence="low", as_of=as_of, available_at=available_at,
        point_in_time_lag_days=0, source="test",
    )


def test_check_readings_point_in_time_passes_when_ok():
    rs = [_r("2026-05-10", "2026-05-10"), _r("2026-05-12", "2026-05-13")]
    check_readings_point_in_time(rs, decision_timestamp="2026-05-15")


def test_check_readings_point_in_time_raises_on_lookahead():
    rs = [_r("2026-05-20", "2026-05-20")]
    with pytest.raises(LookaheadViolation):
        check_readings_point_in_time(rs, decision_timestamp="2026-05-15")
