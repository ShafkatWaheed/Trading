"""Relative valuation: compare stock metrics vs sector/industry peers."""

from dataclasses import dataclass, field
from decimal import Decimal

from src.models.stock import StockFundamentals


@dataclass
class RelativeValueScore:
    score: int  # -2 to +2
    valuation: str  # cheap / fair / expensive
    comparisons: list[str] = field(default_factory=list)
    factors: list[str] = field(default_factory=list)


def analyze(stock: StockFundamentals, sector_avg: StockFundamentals) -> RelativeValueScore:
    score = 0
    comparisons: list[str] = []
    factors: list[str] = []

    # P/E comparison
    score += _compare_lower_is_better(
        stock.pe_ratio, sector_avg.pe_ratio, "P/E",
        comparisons, factors,
    )

    # PEG comparison
    score += _compare_lower_is_better(
        stock.peg_ratio, sector_avg.peg_ratio, "PEG",
        comparisons, factors,
    )

    # Profit margin (higher is better)
    score += _compare_higher_is_better(
        stock.profit_margin, sector_avg.profit_margin, "Profit Margin",
        comparisons, factors,
    )

    # Revenue growth (higher is better)
    score += _compare_higher_is_better(
        stock.revenue_growth, sector_avg.revenue_growth, "Revenue Growth",
        comparisons, factors,
    )

    # ROE (higher is better)
    score += _compare_higher_is_better(
        stock.roe, sector_avg.roe, "ROE",
        comparisons, factors,
    )

    score = max(-2, min(2, score))

    if score >= 1:
        valuation = "cheap"
    elif score <= -1:
        valuation = "expensive"
    else:
        valuation = "fair"

    return RelativeValueScore(
        score=score,
        valuation=valuation,
        comparisons=comparisons,
        factors=factors,
    )


def _compare_lower_is_better(
    stock_val: Decimal | None,
    sector_val: Decimal | None,
    label: str,
    comparisons: list[str],
    factors: list[str],
) -> int:
    if stock_val is None or sector_val is None or sector_val == 0:
        return 0

    ratio = stock_val / sector_val
    comparisons.append(f"{label}: {stock_val} vs sector {sector_val}")

    if ratio < Decimal("0.7"):
        factors.append(f"{label} at 30%+ discount to sector")
        return 1
    elif ratio > Decimal("1.3"):
        factors.append(f"{label} at 30%+ premium to sector")
        return -1
    return 0


def _compare_higher_is_better(
    stock_val: Decimal | None,
    sector_val: Decimal | None,
    label: str,
    comparisons: list[str],
    factors: list[str],
) -> int:
    if stock_val is None or sector_val is None or sector_val == 0:
        return 0

    ratio = stock_val / sector_val
    comparisons.append(f"{label}: {stock_val} vs sector {sector_val}")

    if ratio > Decimal("1.3"):
        factors.append(f"{label} 30%+ above sector average")
        return 1
    elif ratio < Decimal("0.7"):
        factors.append(f"{label} 30%+ below sector average")
        return -1
    return 0
