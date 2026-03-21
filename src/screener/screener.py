"""Stock screener: filter stocks by fundamental and technical criteria."""

from dataclasses import dataclass, field
from decimal import Decimal

from src.models.stock import StockFundamentals


@dataclass
class ScreenCriteria:
    pe_max: Decimal | None = None
    pe_min: Decimal | None = None
    market_cap_min: Decimal | None = None
    market_cap_max: Decimal | None = None
    dividend_yield_min: Decimal | None = None
    eps_growth_min: Decimal | None = None
    revenue_growth_min: Decimal | None = None
    debt_to_equity_max: Decimal | None = None
    roe_min: Decimal | None = None
    profit_margin_min: Decimal | None = None
    sector: str | None = None


@dataclass
class ScreenResult:
    symbol: str
    name: str
    matched_criteria: list[str] = field(default_factory=list)
    fundamentals: StockFundamentals | None = None


def matches_criteria(fundamentals: StockFundamentals, criteria: ScreenCriteria) -> tuple[bool, list[str]]:
    """Check if a stock matches all screening criteria. Returns (passed, matched_list)."""
    matched: list[str] = []

    checks = [
        (criteria.pe_max, fundamentals.pe_ratio, lambda c, v: v is not None and v <= c, "P/E"),
        (criteria.pe_min, fundamentals.pe_ratio, lambda c, v: v is not None and v >= c, "P/E"),
        (criteria.market_cap_min, fundamentals.market_cap, lambda c, v: v >= c, "Market Cap"),
        (criteria.market_cap_max, fundamentals.market_cap, lambda c, v: v <= c, "Market Cap"),
        (criteria.dividend_yield_min, fundamentals.dividend_yield, lambda c, v: v is not None and v >= c, "Dividend"),
        (criteria.eps_growth_min, fundamentals.eps_growth, lambda c, v: v is not None and v >= c, "EPS Growth"),
        (criteria.revenue_growth_min, fundamentals.revenue_growth, lambda c, v: v is not None and v >= c, "Revenue Growth"),
        (criteria.debt_to_equity_max, fundamentals.debt_to_equity, lambda c, v: v is not None and v <= c, "D/E Ratio"),
        (criteria.roe_min, fundamentals.roe, lambda c, v: v is not None and v >= c, "ROE"),
        (criteria.profit_margin_min, fundamentals.profit_margin, lambda c, v: v is not None and v >= c, "Margin"),
    ]

    for criterion_val, stock_val, check_fn, label in checks:
        if criterion_val is None:
            continue
        if not check_fn(criterion_val, stock_val):
            return False, []
        matched.append(label)

    if criteria.sector and fundamentals.sector.lower() != criteria.sector.lower():
        return False, []
    if criteria.sector:
        matched.append("Sector")

    return True, matched
