"""Tests for sector-influence shared dataclasses (Wave 1)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.analysis.sector_signals._shared import (
    Fact,
    SignalReading,
    StockInformation,
)


def test_fact_is_frozen():
    f = Fact(
        text="filed 1247 patents in last 12mo",
        as_of="2026-05-15T00:00:00Z",
        source="uspto",
        source_url="https://patentsview.org/...",
        confidence=1.0,
    )
    with pytest.raises(Exception):
        f.text = "changed"


def test_stock_information_required_fields():
    si = StockInformation(
        ticker="AAPL",
        topic="innovation",
        headline="R&D weighted toward on-device AI",
        facts=[],
        narrative=None,
        implications=["heavy R&D in AI"],
        related_catalysts=[],
        confidence="high",
        as_of="2026-05-15T00:00:00Z",
        sources_used=["uspto"],
        severity="low",
    )
    assert si.ticker == "AAPL"
    assert si.topic == "innovation"
    assert si.severity == "low"


def test_stock_information_severity_must_be_valid():
    with pytest.raises(ValueError):
        StockInformation(
            ticker="AAPL",
            topic="innovation",
            headline="x",
            facts=[],
            narrative=None,
            implications=[],
            related_catalysts=[],
            confidence="high",
            as_of="2026-05-15T00:00:00Z",
            sources_used=[],
            severity="extreme",  # not allowed
        )


def test_signal_reading_uses_decimal_for_value():
    sr = SignalReading(
        ticker="LMT",
        sector=None,
        signal_name="gov_contract_award",
        value=Decimal("4200000000"),
        z_score=Decimal("1.5"),
        direction="bullish",
        confidence="high",
        as_of="2026-05-14T00:00:00Z",
        available_at="2026-05-17T00:00:00Z",
        point_in_time_lag_days=3,
        source="usaspending",
    )
    assert isinstance(sr.value, Decimal)
    assert sr.available_at >= sr.as_of


def test_signal_reading_rejects_float_value():
    with pytest.raises(TypeError):
        SignalReading(
            ticker="X",
            sector=None,
            signal_name="test",
            value=4.2,  # float not allowed for monetary/numeric value
            z_score=None,
            direction="neutral",
            confidence="low",
            as_of="2026-05-15T00:00:00Z",
            available_at="2026-05-15T00:00:00Z",
            point_in_time_lag_days=0,
            source="test",
        )


def test_signal_reading_available_at_must_be_ge_as_of():
    with pytest.raises(ValueError):
        SignalReading(
            ticker="X",
            sector=None,
            signal_name="test",
            value=Decimal("1"),
            z_score=None,
            direction="neutral",
            confidence="low",
            as_of="2026-05-15T00:00:00Z",
            available_at="2026-05-14T00:00:00Z",  # before as_of -> lookahead!
            point_in_time_lag_days=0,
            source="test",
        )


def test_signal_reading_either_ticker_or_sector_required():
    with pytest.raises(ValueError):
        SignalReading(
            ticker=None,
            sector=None,
            signal_name="test",
            value=Decimal("1"),
            z_score=None,
            direction="neutral",
            confidence="low",
            as_of="2026-05-15T00:00:00Z",
            available_at="2026-05-15T00:00:00Z",
            point_in_time_lag_days=0,
            source="test",
        )
