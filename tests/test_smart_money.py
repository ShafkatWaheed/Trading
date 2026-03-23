"""Tests for smart money analysis module."""

from decimal import Decimal

from src.analysis.smart_money import SmartMoneyScore, analyze
from src.models.data_types import InsiderSummary, InstitutionalSummary


def test_cluster_buy_signal() -> None:
    """Cluster buy detected should produce a strong positive score."""
    insider = InsiderSummary(
        symbol="AAPL",
        period_days=30,
        total_trades=5,
        total_buys=4,
        total_sells=1,
        net_shares=10000,
        buy_value=Decimal("500000"),
        sell_value=Decimal("50000"),
        unique_insiders=3,
        cluster_buy=True,
        signal="strong buy",
    )

    result = analyze(insider=insider)

    assert isinstance(result, SmartMoneyScore)
    assert result.score == 2  # clamped max
    assert result.cluster_buy_detected is True
    assert result.insider_signal == "buying"
    assert any("Cluster buy" in f for f in result.factors)


def test_net_selling() -> None:
    """More sells than buys should produce a negative score."""
    insider = InsiderSummary(
        symbol="TSLA",
        period_days=30,
        total_trades=8,
        total_buys=1,
        total_sells=7,
        net_shares=-50000,
        buy_value=Decimal("20000"),
        sell_value=Decimal("800000"),
        unique_insiders=4,
        cluster_buy=False,
        signal="strong sell",
    )

    result = analyze(insider=insider)

    assert result.score <= -1
    assert result.insider_signal == "selling"
    assert any("selling" in f.lower() for f in result.factors)


def test_institutional_accumulation() -> None:
    """Positive net_change_shares with new positions should be positive."""
    institutional = InstitutionalSummary(
        symbol="MSFT",
        total_institutions=50,
        total_shares_held=1000000,
        institutional_ownership_percent=Decimal("72.5"),
        net_change_shares=200000,
        new_positions=10,
        closed_positions=2,
        increased=30,
        decreased=10,
    )

    result = analyze(institutional=institutional)

    assert result.score >= 1
    assert result.institutional_signal == "accumulating"
    assert any("accumulation" in f.lower() for f in result.factors)


def test_no_data() -> None:
    """Empty summaries (both None) should produce a neutral score."""
    result = analyze(insider=None, institutional=None)

    assert result.score == 0
    assert result.insider_signal == "neutral"
    assert result.institutional_signal == "neutral"
    assert result.cluster_buy_detected is False
    assert result.factors == []
