"""Unit tests for options flow analysis module."""

from decimal import Decimal

from src.analysis.options_flow import analyze, OptionsFlowScore
from src.models.data_types import OptionsSummary, UnusualActivity


def _make_summary(**overrides) -> OptionsSummary:
    """Build an OptionsSummary with neutral defaults."""
    defaults = dict(
        underlying="TEST",
        underlying_price=Decimal("150.00"),
        put_call_ratio=Decimal("0.85"),
        total_call_volume=10000,
        total_put_volume=8500,
        total_call_oi=50000,
        total_put_oi=42500,
        avg_iv=Decimal("0.30"),
        iv_rank=Decimal("50"),
        iv_percentile=Decimal("55"),
        max_pain=Decimal("148.00"),
        unusual_activity=[],
    )
    defaults.update(overrides)
    return OptionsSummary(**defaults)


def _make_unusual(sentiment: str = "bullish") -> UnusualActivity:
    """Build a single UnusualActivity entry."""
    return UnusualActivity(
        underlying="TEST",
        contract_type="call" if sentiment == "bullish" else "put",
        strike=Decimal("155.00"),
        expiration="2026-04-17",
        volume=5000,
        open_interest=200,
        volume_oi_ratio=Decimal("25.0"),
        implied_volatility=Decimal("0.45"),
        premium=Decimal("250000"),
        sentiment=sentiment,
        timestamp="2026-03-22T14:00:00Z",
    )


def test_bullish_options() -> None:
    """Low P/C ratio (< 0.7) should produce a bullish signal with positive score."""
    summary = _make_summary(put_call_ratio=Decimal("0.6"))
    result = analyze(summary)

    assert result.score > 0, (
        f"Low P/C ratio should give positive score, got {result.score}"
    )
    assert result.signal == "bullish", (
        f"Expected bullish signal, got {result.signal}"
    )
    assert "bullish" in result.put_call_interpretation.lower(), (
        "P/C interpretation should mention bullish"
    )


def test_very_bullish_options() -> None:
    """Very low P/C ratio (< 0.5) should give score +2."""
    summary = _make_summary(put_call_ratio=Decimal("0.4"))
    result = analyze(summary)

    assert result.score == 2, (
        f"Very low P/C should give +2, got {result.score}"
    )
    assert result.signal == "bullish"


def test_bearish_options() -> None:
    """High P/C ratio (> 1.0) should produce a bearish signal with negative score."""
    summary = _make_summary(put_call_ratio=Decimal("1.2"))
    result = analyze(summary)

    assert result.score < 0, (
        f"High P/C ratio should give negative score, got {result.score}"
    )
    assert result.signal == "bearish", (
        f"Expected bearish signal, got {result.signal}"
    )
    assert "bearish" in result.put_call_interpretation.lower(), (
        "P/C interpretation should mention bearish"
    )


def test_very_bearish_options() -> None:
    """Very high P/C ratio (> 1.3) should give score -2."""
    summary = _make_summary(put_call_ratio=Decimal("1.5"))
    result = analyze(summary)

    assert result.score == -2, (
        f"Very high P/C should give -2, got {result.score}"
    )
    assert result.signal == "bearish"


def test_high_iv() -> None:
    """IV rank > 75% should produce a cautionary interpretation."""
    summary = _make_summary(
        put_call_ratio=Decimal("0.85"),  # neutral P/C
        iv_rank=Decimal("85"),
    )
    result = analyze(summary)

    assert "elevated" in result.iv_interpretation.lower() or "expensive" in result.iv_interpretation.lower(), (
        f"High IV rank should produce cautionary note, got: {result.iv_interpretation}"
    )
    assert any("iv rank" in f.lower() for f in result.factors), (
        "High IV should appear in factors"
    )


def test_low_iv() -> None:
    """IV rank < 20% should note complacency."""
    summary = _make_summary(
        put_call_ratio=Decimal("0.85"),
        iv_rank=Decimal("15"),
    )
    result = analyze(summary)

    assert "low" in result.iv_interpretation.lower() or "cheap" in result.iv_interpretation.lower(), (
        f"Low IV rank should note complacency, got: {result.iv_interpretation}"
    )


def test_unusual_activity_bullish() -> None:
    """Bullish unusual activity (bullish >> bearish) should add positive score."""
    bullish_entries = [_make_unusual("bullish") for _ in range(5)]
    bearish_entries = [_make_unusual("bearish") for _ in range(1)]

    summary = _make_summary(
        put_call_ratio=Decimal("0.85"),  # neutral P/C -> score 0 from P/C
        unusual_activity=bullish_entries + bearish_entries,
    )
    result = analyze(summary)

    assert result.score > 0, (
        f"Bullish unusual activity should push score positive, got {result.score}"
    )
    assert "bullish" in result.unusual_activity_note.lower(), (
        f"Should note bullish unusual activity, got: {result.unusual_activity_note}"
    )


def test_unusual_activity_bearish() -> None:
    """Bearish unusual activity should add negative score."""
    bullish_entries = [_make_unusual("bullish") for _ in range(1)]
    bearish_entries = [_make_unusual("bearish") for _ in range(5)]

    summary = _make_summary(
        put_call_ratio=Decimal("0.85"),  # neutral P/C
        unusual_activity=bullish_entries + bearish_entries,
    )
    result = analyze(summary)

    assert result.score < 0, (
        f"Bearish unusual activity should push score negative, got {result.score}"
    )
    assert "bearish" in result.unusual_activity_note.lower(), (
        f"Should note bearish unusual activity, got: {result.unusual_activity_note}"
    )


def test_neutral_options() -> None:
    """Neutral P/C ratio with no unusual activity should be neutral."""
    summary = _make_summary(
        put_call_ratio=Decimal("0.85"),
        iv_rank=Decimal("50"),
        unusual_activity=[],
    )
    result = analyze(summary)

    assert result.signal == "neutral", (
        f"Expected neutral signal, got {result.signal}"
    )
    assert result.score == 0, (
        f"Expected score 0, got {result.score}"
    )
