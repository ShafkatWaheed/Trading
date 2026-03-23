"""Tests for congressional trade signal analysis module."""

from decimal import Decimal

from src.analysis.congress_signal import CongressSignalScore, analyze
from src.models.data_types import CongressTradesSummary


def test_bullish_congress() -> None:
    """More buys than sells should produce a positive bullish signal."""
    summary = CongressTradesSummary(
        symbol="NVDA",
        total_trades=10,
        total_buys=8,
        total_sells=2,
        unique_politicians=5,
        net_sentiment="bullish",
        party_breakdown={"Democrat": {"buy": 5, "sell": 1}},
    )

    result = analyze(summary)

    assert isinstance(result, CongressSignalScore)
    assert result.score > 0
    assert result.signal == "bullish"
    assert any("bullish" in f.lower() for f in result.factors)


def test_bearish_congress() -> None:
    """More sells than buys should produce a negative bearish signal."""
    summary = CongressTradesSummary(
        symbol="META",
        total_trades=7,
        total_buys=1,
        total_sells=6,
        unique_politicians=4,
        net_sentiment="bearish",
        party_breakdown={"Republican": {"buy": 1, "sell": 4}},
    )

    result = analyze(summary)

    assert result.score < 0
    assert result.signal == "bearish"
    assert any("bearish" in f.lower() for f in result.factors)


def test_bipartisan_buy() -> None:
    """Both parties buying should set bipartisan=True for a stronger signal."""
    summary = CongressTradesSummary(
        symbol="GOOGL",
        total_trades=12,
        total_buys=10,
        total_sells=2,
        unique_politicians=8,
        net_sentiment="bullish",
        party_breakdown={
            "Democrat": {"buy": 5, "sell": 1},
            "Republican": {"buy": 5, "sell": 1},
        },
    )

    result = analyze(summary)

    assert result.score > 0
    assert result.signal == "bullish"
    assert result.bipartisan is True
    assert any("Bipartisan" in f for f in result.factors)


def test_no_trades() -> None:
    """Empty summary with zero trades should return no_data signal."""
    summary = CongressTradesSummary(
        symbol="XYZ",
        total_trades=0,
        total_buys=0,
        total_sells=0,
        unique_politicians=0,
        net_sentiment="neutral",
    )

    result = analyze(summary)

    assert result.score == 0
    assert result.signal == "no_data"
    assert any("No congressional trades" in f for f in result.factors)
