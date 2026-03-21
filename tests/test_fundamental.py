"""Tests for fundamental analysis scoring."""

from decimal import Decimal

from src.analysis.fundamental import analyze, FundamentalScore
from src.models.stock import StockFundamentals


def _make_fundamentals(**overrides) -> StockFundamentals:
    defaults = {
        "symbol": "TEST",
        "market_cap": Decimal("1000000000"),
        "pe_ratio": Decimal("20"),
        "peg_ratio": Decimal("1.5"),
        "eps": Decimal("5"),
        "eps_growth": Decimal("10"),
        "revenue": Decimal("500000000"),
        "revenue_growth": Decimal("8"),
        "profit_margin": Decimal("15"),
        "roe": Decimal("12"),
        "debt_to_equity": Decimal("0.8"),
        "free_cash_flow": Decimal("50000000"),
        "dividend_yield": Decimal("2"),
        "beta": Decimal("1.1"),
        "week_52_high": Decimal("150"),
        "week_52_low": Decimal("100"),
    }
    defaults.update(overrides)
    return StockFundamentals(**defaults)


def test_strong_fundamentals():
    f = _make_fundamentals(
        pe_ratio=Decimal("12"),
        peg_ratio=Decimal("0.8"),
        eps_growth=Decimal("20"),
        revenue_growth=Decimal("15"),
        profit_margin=Decimal("25"),
        roe=Decimal("20"),
        debt_to_equity=Decimal("0.3"),
        free_cash_flow=Decimal("100000000"),
    )
    score = analyze(f)
    assert score.overall_score >= 4
    assert len(score.strengths) > 0


def test_weak_fundamentals():
    f = _make_fundamentals(
        pe_ratio=Decimal("40"),
        peg_ratio=Decimal("3"),
        eps_growth=Decimal("-5"),
        revenue_growth=Decimal("-3"),
        profit_margin=Decimal("2"),
        roe=Decimal("3"),
        debt_to_equity=Decimal("3"),
        free_cash_flow=Decimal("-10000000"),
    )
    score = analyze(f)
    assert score.overall_score <= 2
    assert len(score.weaknesses) > 0


def test_neutral_fundamentals():
    f = _make_fundamentals()
    score = analyze(f)
    assert 2 <= score.overall_score <= 4
