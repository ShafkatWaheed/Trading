"""Fundamental analysis: evaluate company financials and valuation."""

from dataclasses import dataclass
from decimal import Decimal

from src.models.stock import StockFundamentals


@dataclass
class FundamentalScore:
    symbol: str
    valuation_score: int  # 1-5 (1=expensive, 5=cheap)
    growth_score: int  # 1-5
    profitability_score: int  # 1-5
    health_score: int  # 1-5
    overall_score: int  # 1-5
    strengths: list[str]
    weaknesses: list[str]


def analyze(fundamentals: StockFundamentals) -> FundamentalScore:
    """Score a stock's fundamentals across key dimensions."""
    strengths: list[str] = []
    weaknesses: list[str] = []

    valuation = _score_valuation(fundamentals, strengths, weaknesses)
    growth = _score_growth(fundamentals, strengths, weaknesses)
    profitability = _score_profitability(fundamentals, strengths, weaknesses)
    health = _score_health(fundamentals, strengths, weaknesses)

    overall = round((valuation + growth + profitability + health) / 4)

    return FundamentalScore(
        symbol=fundamentals.symbol,
        valuation_score=valuation,
        growth_score=growth,
        profitability_score=profitability,
        health_score=health,
        overall_score=overall,
        strengths=strengths,
        weaknesses=weaknesses,
    )


def _score_valuation(f: StockFundamentals, s: list[str], w: list[str]) -> int:
    score = 3  # neutral default
    if f.pe_ratio is not None:
        if f.pe_ratio < 15:
            score += 1
            s.append(f"Low P/E ({f.pe_ratio})")
        elif f.pe_ratio > 35:
            score -= 1
            w.append(f"High P/E ({f.pe_ratio})")

    if f.peg_ratio is not None:
        if f.peg_ratio < Decimal("1"):
            score += 1
            s.append(f"PEG < 1 ({f.peg_ratio}) — undervalued relative to growth")
        elif f.peg_ratio > Decimal("2"):
            score -= 1
            w.append(f"High PEG ({f.peg_ratio})")

    return max(1, min(5, score))


def _score_growth(f: StockFundamentals, s: list[str], w: list[str]) -> int:
    score = 3
    if f.eps_growth is not None:
        if f.eps_growth > Decimal("15"):
            score += 1
            s.append(f"Strong EPS growth ({f.eps_growth}%)")
        elif f.eps_growth < 0:
            score -= 1
            w.append(f"Negative EPS growth ({f.eps_growth}%)")

    if f.revenue_growth is not None:
        if f.revenue_growth > Decimal("10"):
            score += 1
            s.append(f"Solid revenue growth ({f.revenue_growth}%)")
        elif f.revenue_growth < 0:
            score -= 1
            w.append(f"Revenue declining ({f.revenue_growth}%)")

    return max(1, min(5, score))


def _score_profitability(f: StockFundamentals, s: list[str], w: list[str]) -> int:
    score = 3
    if f.profit_margin is not None:
        if f.profit_margin > Decimal("20"):
            score += 1
            s.append(f"High profit margin ({f.profit_margin}%)")
        elif f.profit_margin < Decimal("5"):
            score -= 1
            w.append(f"Thin margins ({f.profit_margin}%)")

    if f.roe is not None:
        if f.roe > Decimal("15"):
            score += 1
            s.append(f"Strong ROE ({f.roe}%)")
        elif f.roe < Decimal("5"):
            score -= 1
            w.append(f"Weak ROE ({f.roe}%)")

    return max(1, min(5, score))


def _score_health(f: StockFundamentals, s: list[str], w: list[str]) -> int:
    score = 3
    if f.debt_to_equity is not None:
        if f.debt_to_equity < Decimal("0.5"):
            score += 1
            s.append(f"Low debt (D/E: {f.debt_to_equity})")
        elif f.debt_to_equity > Decimal("2"):
            score -= 1
            w.append(f"High debt (D/E: {f.debt_to_equity})")

    if f.free_cash_flow is not None:
        if f.free_cash_flow > 0:
            score += 1
            s.append("Positive free cash flow")
        else:
            score -= 1
            w.append("Negative free cash flow")

    return max(1, min(5, score))
