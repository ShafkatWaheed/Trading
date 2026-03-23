"""Opportunity scoring: 4-factor composite score (0-100).

Factors (25% each):
1. Volume Score — recent volume vs average
2. Price Score — momentum + trend signals
3. Flow Score — options sentiment + insider activity
4. Risk/Reward — distance to support vs resistance
"""

from dataclasses import dataclass
from decimal import Decimal

from src.models.indicator import TechnicalIndicators, SignalType


@dataclass
class OpportunityScore:
    symbol: str
    total_score: int  # 0-100
    volume_score: int  # 0-25
    price_score: int  # 0-25
    flow_score: int  # 0-25
    risk_reward_score: int  # 0-25
    risk_reward_ratio: str  # e.g. "4.0:1"
    strategy: str  # e.g. "Volume Spike", "Momentum", "Breakout"
    label: str  # "Excellent", "Good", "Fair", "Poor"


def compute_opportunity(
    symbol: str,
    technicals: TechnicalIndicators | None = None,
    options_pcr: Decimal | None = None,
    insider_net_buy: bool | None = None,
) -> OpportunityScore:
    """Compute 4-factor opportunity score."""

    vol_score = _volume_score(technicals)
    price_score = _price_score(technicals)
    flow_score = _flow_score(options_pcr, insider_net_buy)
    rr_score, rr_ratio = _risk_reward_score(technicals)

    total = vol_score + price_score + flow_score + rr_score
    label = _score_label(total)
    strategy = _detect_strategy(technicals, vol_score, price_score)

    return OpportunityScore(
        symbol=symbol,
        total_score=total,
        volume_score=vol_score,
        price_score=price_score,
        flow_score=flow_score,
        risk_reward_score=rr_score,
        risk_reward_ratio=rr_ratio,
        strategy=strategy,
        label=label,
    )


def _volume_score(tech: TechnicalIndicators | None) -> int:
    if not tech or not tech.avg_volume_20:
        return 13  # neutral
    vt = tech.volume_trend
    if vt == "increasing":
        return 22
    if vt == "decreasing":
        return 5
    return 13


def _price_score(tech: TechnicalIndicators | None) -> int:
    if not tech:
        return 13
    score = 13  # baseline
    # RSI momentum
    if tech.rsi_14:
        rsi = float(tech.rsi_14)
        if 50 < rsi < 70:
            score += 5  # bullish momentum
        elif 30 < rsi < 50:
            score -= 3
        elif rsi <= 30:
            score += 3  # oversold bounce potential
        elif rsi >= 70:
            score -= 5  # overbought risk

    # Trend
    if tech.trend == "uptrend":
        score += 4
    elif tech.trend == "downtrend":
        score -= 4

    # MACD
    if tech.macd_histogram and tech.macd_histogram > 0:
        score += 3
    elif tech.macd_histogram and tech.macd_histogram < 0:
        score -= 3

    return max(0, min(25, score))


def _flow_score(options_pcr: Decimal | None, insider_net_buy: bool | None) -> int:
    score = 13
    # Options flow
    if options_pcr is not None:
        pcr = float(options_pcr)
        if pcr < 0.5:
            score += 8  # very bullish
        elif pcr < 0.7:
            score += 4  # bullish
        elif pcr > 1.5:
            score -= 8  # very bearish
        elif pcr > 1.0:
            score -= 4  # bearish

    # Insider activity
    if insider_net_buy is True:
        score += 4
    elif insider_net_buy is False:
        score -= 2

    return max(0, min(25, score))


def _risk_reward_score(tech: TechnicalIndicators | None) -> tuple[int, str]:
    if not tech or not tech.current_price or not tech.support or not tech.resistance:
        return 13, "—"

    price = float(tech.current_price)
    support = float(tech.support)
    resistance = float(tech.resistance)

    if support >= price or resistance <= price:
        return 13, "—"

    downside = price - support
    upside = resistance - price

    if downside == 0:
        return 25, "inf:1"

    ratio = upside / downside
    ratio_str = f"{ratio:.1f}:1"

    if ratio >= 4.0:
        return 25, ratio_str
    if ratio >= 3.0:
        return 21, ratio_str
    if ratio >= 2.0:
        return 17, ratio_str
    if ratio >= 1.0:
        return 13, ratio_str
    return 5, ratio_str


def _score_label(total: int) -> str:
    if total >= 80:
        return "Excellent"
    if total >= 60:
        return "Good"
    if total >= 40:
        return "Fair"
    return "Poor"


def _detect_strategy(tech: TechnicalIndicators | None, vol: int, price: int) -> str:
    if vol >= 20:
        return "Volume Spike"
    if tech and tech.trend == "uptrend" and price >= 18:
        return "Momentum"
    if tech and tech.current_price and tech.resistance:
        if float(tech.current_price) > float(tech.resistance) * 0.97:
            return "Breakout"
    if tech and tech.rsi_14 and float(tech.rsi_14) < 35:
        return "Oversold Bounce"
    if tech and tech.trend == "downtrend":
        return "Mean Reversion"
    return "Neutral"
