"""Macro regime analysis: score how macro environment affects stock investing."""

from dataclasses import dataclass, field
from decimal import Decimal

from src.models.data_types import MacroSnapshot


@dataclass
class MacroScore:
    regime: str
    score: int  # -2 (strong headwind) to +2 (strong tailwind)
    factors: list[str] = field(default_factory=list)


def analyze(snapshot: MacroSnapshot) -> MacroScore:
    score = 0
    factors: list[str] = []

    # Yield curve
    if snapshot.yield_curve_inverted:
        score -= 2
        factors.append("Inverted yield curve signals recession risk")

    # VIX
    if snapshot.vix is not None:
        if snapshot.vix > Decimal("35"):
            score -= 2
            factors.append(f"Extreme fear — VIX at {snapshot.vix}")
        elif snapshot.vix > Decimal("25"):
            score -= 1
            factors.append(f"Elevated volatility — VIX at {snapshot.vix}")
        elif snapshot.vix < Decimal("15"):
            score += 1
            factors.append(f"Low volatility, risk-on environment — VIX at {snapshot.vix}")

    # Fed funds rate
    if snapshot.fed_funds_rate is not None:
        if snapshot.fed_funds_rate > Decimal("5"):
            score -= 1
            factors.append(f"Restrictive monetary policy — Fed rate at {snapshot.fed_funds_rate}%")
        elif snapshot.fed_funds_rate < Decimal("2"):
            score += 1
            factors.append(f"Accommodative monetary policy — Fed rate at {snapshot.fed_funds_rate}%")

    # Unemployment
    if snapshot.unemployment_rate is not None:
        if snapshot.unemployment_rate > Decimal("6"):
            score -= 1
            factors.append(f"Weakening labor market — unemployment at {snapshot.unemployment_rate}%")
        elif snapshot.unemployment_rate < Decimal("4"):
            score += 1
            factors.append(f"Strong labor market — unemployment at {snapshot.unemployment_rate}%")

    # GDP growth
    if snapshot.gdp_growth is not None:
        if snapshot.gdp_growth > Decimal("3"):
            score += 1
            factors.append(f"Robust GDP growth at {snapshot.gdp_growth}%")
        elif snapshot.gdp_growth < Decimal("0"):
            score -= 1
            factors.append(f"GDP contraction at {snapshot.gdp_growth}%")

    score = max(-2, min(2, score))

    return MacroScore(
        regime=snapshot.regime,
        score=score,
        factors=factors,
    )
