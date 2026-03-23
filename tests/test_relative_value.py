"""Tests for relative value analysis module."""

from decimal import Decimal

from src.analysis.relative_value import RelativeValueScore, analyze
from src.models.stock import StockFundamentals


def test_undervalued() -> None:
    """PE much lower than sector should be scored as cheap."""
    stock = StockFundamentals(
        symbol="AAPL",
        market_cap=Decimal("2500000000000"),
        pe_ratio=Decimal("10"),
        peg_ratio=Decimal("0.8"),
        profit_margin=Decimal("0.30"),
        revenue_growth=Decimal("0.20"),
        roe=Decimal("0.40"),
    )
    sector_avg = StockFundamentals(
        symbol="SECTOR",
        market_cap=Decimal("500000000000"),
        pe_ratio=Decimal("25"),
        peg_ratio=Decimal("1.8"),
        profit_margin=Decimal("0.15"),
        revenue_growth=Decimal("0.10"),
        roe=Decimal("0.15"),
    )

    result = analyze(stock, sector_avg)

    assert isinstance(result, RelativeValueScore)
    assert result.score >= 1
    assert result.valuation == "cheap"
    assert len(result.factors) > 0


def test_overvalued() -> None:
    """PE much higher than sector should be scored as expensive."""
    stock = StockFundamentals(
        symbol="HYPE",
        market_cap=Decimal("100000000000"),
        pe_ratio=Decimal("80"),
        peg_ratio=Decimal("4.0"),
        profit_margin=Decimal("0.05"),
        revenue_growth=Decimal("0.03"),
        roe=Decimal("0.04"),
    )
    sector_avg = StockFundamentals(
        symbol="SECTOR",
        market_cap=Decimal("500000000000"),
        pe_ratio=Decimal("20"),
        peg_ratio=Decimal("1.2"),
        profit_margin=Decimal("0.15"),
        revenue_growth=Decimal("0.10"),
        roe=Decimal("0.15"),
    )

    result = analyze(stock, sector_avg)

    assert result.score <= -1
    assert result.valuation == "expensive"
    assert len(result.factors) > 0


def test_fair_value() -> None:
    """Metrics near sector average should be scored as fair."""
    stock = StockFundamentals(
        symbol="FAIR",
        market_cap=Decimal("200000000000"),
        pe_ratio=Decimal("20"),
        peg_ratio=Decimal("1.5"),
        profit_margin=Decimal("0.14"),
        revenue_growth=Decimal("0.09"),
        roe=Decimal("0.13"),
    )
    sector_avg = StockFundamentals(
        symbol="SECTOR",
        market_cap=Decimal("500000000000"),
        pe_ratio=Decimal("20"),
        peg_ratio=Decimal("1.5"),
        profit_margin=Decimal("0.15"),
        revenue_growth=Decimal("0.10"),
        roe=Decimal("0.14"),
    )

    result = analyze(stock, sector_avg)

    assert result.score == 0
    assert result.valuation == "fair"


def test_missing_sector_data() -> None:
    """No sector averages (all None) should produce neutral score."""
    stock = StockFundamentals(
        symbol="AAPL",
        market_cap=Decimal("2500000000000"),
        pe_ratio=Decimal("15"),
        peg_ratio=Decimal("1.2"),
        profit_margin=Decimal("0.25"),
        revenue_growth=Decimal("0.12"),
        roe=Decimal("0.30"),
    )
    sector_avg = StockFundamentals(
        symbol="SECTOR",
        market_cap=Decimal("0"),
        pe_ratio=None,
        peg_ratio=None,
        profit_margin=None,
        revenue_growth=None,
        roe=None,
    )

    result = analyze(stock, sector_avg)

    assert result.score == 0
    assert result.valuation == "fair"
    assert len(result.comparisons) == 0
    assert len(result.factors) == 0
