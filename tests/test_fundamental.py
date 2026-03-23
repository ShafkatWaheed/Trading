"""Unit tests for fundamental analysis module."""

from decimal import Decimal

from src.analysis.fundamental import analyze, FundamentalScore
from src.models.stock import StockFundamentals


def _make_fundamentals(**overrides) -> StockFundamentals:
    """Build a StockFundamentals with sensible defaults, overridden as needed."""
    defaults = dict(
        symbol="TEST",
        market_cap=Decimal("50000000000"),
        pe_ratio=Decimal("20"),
        peg_ratio=Decimal("1.5"),
        eps=Decimal("5.00"),
        eps_growth=Decimal("10"),
        revenue=Decimal("10000000000"),
        revenue_growth=Decimal("5"),
        profit_margin=Decimal("12"),
        roe=Decimal("10"),
        debt_to_equity=Decimal("1.0"),
        free_cash_flow=Decimal("500000000"),
        dividend_yield=Decimal("1.5"),
        beta=Decimal("1.1"),
        sector="Technology",
        industry="Software",
    )
    defaults.update(overrides)
    return StockFundamentals(**defaults)


def test_strong_fundamentals() -> None:
    """Low PE, high growth, high margins, low debt -> overall score >= 4."""
    f = _make_fundamentals(
        pe_ratio=Decimal("10"),       # low PE -> +1 valuation
        peg_ratio=Decimal("0.8"),     # PEG < 1 -> +1 valuation  => valuation 5
        eps_growth=Decimal("25"),     # strong -> +1 growth
        revenue_growth=Decimal("15"), # solid -> +1 growth        => growth 5
        profit_margin=Decimal("25"),  # high -> +1 profitability
        roe=Decimal("20"),            # strong -> +1 profitability => profitability 5
        debt_to_equity=Decimal("0.3"),# low -> +1 health
        free_cash_flow=Decimal("1000000000"),  # positive -> +1   => health 5
    )
    result = analyze(f)

    assert result.overall_score >= 4, (
        f"Strong fundamentals should score >= 4, got {result.overall_score}"
    )
    assert result.valuation_score == 5, f"Valuation should be 5, got {result.valuation_score}"
    assert result.growth_score == 5, f"Growth should be 5, got {result.growth_score}"
    assert result.profitability_score == 5, f"Profitability should be 5, got {result.profitability_score}"
    assert result.health_score == 5, f"Health should be 5, got {result.health_score}"
    assert len(result.strengths) > 0, "Should report strengths"
    assert len(result.weaknesses) == 0, "Should have no weaknesses"


def test_weak_fundamentals() -> None:
    """High PE, negative growth, thin margins, heavy debt -> overall score <= 2."""
    f = _make_fundamentals(
        pe_ratio=Decimal("50"),        # high PE -> -1 valuation
        peg_ratio=Decimal("3.0"),      # high PEG -> -1 valuation  => valuation 1
        eps_growth=Decimal("-10"),      # negative -> -1 growth
        revenue_growth=Decimal("-5"),   # declining -> -1 growth    => growth 1
        profit_margin=Decimal("2"),     # thin -> -1 profitability
        roe=Decimal("3"),              # weak -> -1 profitability   => profitability 1
        debt_to_equity=Decimal("3.0"), # high -> -1 health
        free_cash_flow=Decimal("-500000000"),  # negative -> -1    => health 1
    )
    result = analyze(f)

    assert result.overall_score <= 2, (
        f"Weak fundamentals should score <= 2, got {result.overall_score}"
    )
    assert result.valuation_score == 1, f"Valuation should be 1, got {result.valuation_score}"
    assert result.growth_score == 1, f"Growth should be 1, got {result.growth_score}"
    assert result.profitability_score == 1, f"Profitability should be 1, got {result.profitability_score}"
    assert result.health_score == 1, f"Health should be 1, got {result.health_score}"
    assert len(result.weaknesses) > 0, "Should report weaknesses"
    assert len(result.strengths) == 0, "Should have no strengths"


def test_neutral_fundamentals() -> None:
    """Average metrics across the board -> score around 3."""
    f = _make_fundamentals(
        pe_ratio=Decimal("20"),        # mid-range, no adjustment
        peg_ratio=Decimal("1.5"),      # mid-range, no adjustment  => valuation 3
        eps_growth=Decimal("10"),       # moderate, no adjustment
        revenue_growth=Decimal("5"),    # moderate, no adjustment   => growth 3
        profit_margin=Decimal("12"),    # mid, no adjustment
        roe=Decimal("10"),             # mid, no adjustment         => profitability 3
        debt_to_equity=Decimal("1.0"), # mid, no adjustment
        free_cash_flow=Decimal("500000000"),  # positive -> +1     => health 4
    )
    result = analyze(f)

    assert 2 <= result.overall_score <= 4, (
        f"Neutral fundamentals should score ~3, got {result.overall_score}"
    )
    assert result.symbol == "TEST"


def test_missing_data() -> None:
    """None values for optional fields should be handled gracefully, defaulting to 3."""
    f = StockFundamentals(
        symbol="MISSING",
        market_cap=Decimal("10000000000"),
        pe_ratio=None,
        peg_ratio=None,
        eps_growth=None,
        revenue_growth=None,
        profit_margin=None,
        roe=None,
        debt_to_equity=None,
        free_cash_flow=None,
    )
    result = analyze(f)

    assert result.overall_score == 3, (
        f"All-None fundamentals should default to 3, got {result.overall_score}"
    )
    assert result.valuation_score == 3, "Valuation should default to 3"
    assert result.growth_score == 3, "Growth should default to 3"
    assert result.profitability_score == 3, "Profitability should default to 3"
    assert result.health_score == 3, "Health should default to 3"
    assert len(result.strengths) == 0, "No data -> no strengths"
    assert len(result.weaknesses) == 0, "No data -> no weaknesses"
