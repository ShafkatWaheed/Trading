"""Opportunity scoring: 4-factor composite score (0-100).

Factors (25% each):
1. Volume Score — recent volume vs average
2. Price Score — momentum + trend signals
3. Flow Score — options sentiment + insider activity
4. Risk/Reward — distance to support vs resistance

Strategies detected (16):
- Volume Spike, Momentum, Breakout, Oversold Bounce, Mean Reversion
- Golden Cross, Death Cross, Insider Accumulation, Congress Buying
- Earnings Catalyst, Dividend Play, Bollinger Squeeze, Support Bounce
- Gap Fill, Sector Leader, Neutral
"""

from dataclasses import dataclass, field
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
    strategy: str  # primary detected strategy
    secondary_strategies: list[str] = field(default_factory=list)
    label: str = ""  # "Excellent", "Good", "Fair", "Poor"


def compute_opportunity(
    symbol: str,
    technicals: TechnicalIndicators | None = None,
    options_pcr: Decimal | None = None,
    insider_net_buy: bool | None = None,
    insider_cluster_buy: bool = False,
    congress_net_buy: bool = False,
    earnings_days_away: int | None = None,
    dividend_yield: float | None = None,
    sector_rank: int | None = None,
) -> OpportunityScore:
    """Compute 4-factor opportunity score with expanded strategy detection."""

    vol_score = _volume_score(technicals)
    price_score = _price_score(technicals)
    flow_score = _flow_score(options_pcr, insider_net_buy, insider_cluster_buy, congress_net_buy)
    rr_score, rr_ratio = _risk_reward_score(technicals)

    total = vol_score + price_score + flow_score + rr_score
    label = _score_label(total)
    strategy, secondaries = _detect_strategies(
        technicals, vol_score, price_score,
        insider_cluster_buy, congress_net_buy,
        earnings_days_away, dividend_yield, sector_rank,
    )

    return OpportunityScore(
        symbol=symbol,
        total_score=total,
        volume_score=vol_score,
        price_score=price_score,
        flow_score=flow_score,
        risk_reward_score=rr_score,
        risk_reward_ratio=rr_ratio,
        strategy=strategy,
        secondary_strategies=secondaries,
        label=label,
    )


def _volume_score(tech: TechnicalIndicators | None) -> int:
    if not tech or not tech.avg_volume_20:
        return 13
    vt = tech.volume_trend
    if vt == "increasing":
        return 22
    if vt == "decreasing":
        return 5
    return 13


def _price_score(tech: TechnicalIndicators | None) -> int:
    if not tech:
        return 13
    score = 13
    if tech.rsi_14:
        rsi = float(tech.rsi_14)
        if 50 < rsi < 70:
            score += 5
        elif 30 < rsi < 50:
            score -= 3
        elif rsi <= 30:
            score += 3
        elif rsi >= 70:
            score -= 5

    if tech.trend == "uptrend":
        score += 4
    elif tech.trend == "downtrend":
        score -= 4

    if tech.macd_histogram and tech.macd_histogram > 0:
        score += 3
    elif tech.macd_histogram and tech.macd_histogram < 0:
        score -= 3

    return max(0, min(25, score))


def _flow_score(
    options_pcr: Decimal | None,
    insider_net_buy: bool | None,
    insider_cluster: bool = False,
    congress_buy: bool = False,
) -> int:
    score = 13
    if options_pcr is not None:
        pcr = float(options_pcr)
        if pcr < 0.5:
            score += 8
        elif pcr < 0.7:
            score += 4
        elif pcr > 1.5:
            score -= 8
        elif pcr > 1.0:
            score -= 4

    if insider_cluster:
        score += 6
    elif insider_net_buy is True:
        score += 4
    elif insider_net_buy is False:
        score -= 2

    if congress_buy:
        score += 3

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


def _detect_strategies(
    tech: TechnicalIndicators | None,
    vol: int,
    price: int,
    insider_cluster: bool = False,
    congress_buy: bool = False,
    earnings_days: int | None = None,
    dividend_yield: float | None = None,
    sector_rank: int | None = None,
) -> tuple[str, list[str]]:
    """Detect all matching strategies, return primary + secondaries."""
    matched: list[tuple[int, str]] = []  # (priority, name)

    # --- Original 5 ---
    if vol >= 20:
        matched.append((10, "Volume Spike"))

    if tech and tech.trend == "uptrend" and price >= 18:
        matched.append((15, "Momentum"))

    if tech and tech.current_price and tech.resistance:
        if float(tech.current_price) > float(tech.resistance) * 0.97:
            matched.append((12, "Breakout"))

    if tech and tech.rsi_14 and float(tech.rsi_14) < 35:
        matched.append((14, "Oversold Bounce"))

    if tech and tech.trend == "downtrend" and price <= 10:
        matched.append((5, "Mean Reversion"))

    # --- New 10 ---

    # Golden Cross: SMA50 > SMA200 and SMA50 recently crossed above
    if tech and tech.sma_50 and tech.sma_200:
        sma50 = float(tech.sma_50)
        sma200 = float(tech.sma_200)
        if sma50 > sma200 and (sma50 - sma200) / sma200 < 0.02:
            # Just crossed — within 2% of each other
            matched.append((20, "Golden Cross"))
        elif sma50 < sma200 and (sma200 - sma50) / sma200 < 0.02:
            matched.append((18, "Death Cross"))

    # Insider Accumulation
    if insider_cluster:
        matched.append((25, "Insider Accumulation"))

    # Congress Buying
    if congress_buy:
        matched.append((22, "Congress Buying"))

    # Earnings Catalyst
    if earnings_days is not None and 0 < earnings_days <= 14:
        if tech and tech.trend != "downtrend":
            matched.append((16, "Earnings Catalyst"))

    # Dividend Play
    if dividend_yield is not None and dividend_yield >= 3.0:
        matched.append((8, "Dividend Play"))

    # Bollinger Squeeze: bands narrowing (BB width < 5% of price)
    if tech and tech.bb_upper and tech.bb_lower and tech.current_price:
        bb_width = float(tech.bb_upper) - float(tech.bb_lower)
        price_val = float(tech.current_price)
        if price_val > 0 and (bb_width / price_val) < 0.05:
            matched.append((13, "Bollinger Squeeze"))

    # Support Bounce: price within 2% of support + not in downtrend
    if tech and tech.current_price and tech.support and tech.trend != "downtrend":
        price_val = float(tech.current_price)
        support_val = float(tech.support)
        if support_val > 0 and ((price_val - support_val) / support_val) < 0.02:
            matched.append((17, "Support Bounce"))

    # Gap Fill: price gapped (open vs prev close > 2%) — detected via signals
    if tech and tech.current_price and tech.sma_20:
        deviation = abs(float(tech.current_price) - float(tech.sma_20)) / float(tech.sma_20)
        if deviation > 0.05 and tech.trend == "downtrend":
            matched.append((6, "Gap Fill"))

    # Sector Leader
    if sector_rank is not None and sector_rank <= 3:
        matched.append((11, "Sector Leader"))

    if not matched:
        return "Neutral", []

    # Sort by priority descending — highest priority is primary
    matched.sort(key=lambda x: x[0], reverse=True)
    primary = matched[0][1]
    secondaries = [name for _, name in matched[1:]]

    return primary, secondaries


def explain_strategy(score: OpportunityScore, tech: "TechnicalIndicators | None" = None) -> str:
    """Generate a 2-3 sentence explanation of why this strategy was detected, using actual indicator values."""
    sym = score.symbol
    strat = score.strategy

    # Gather indicator values for dynamic text
    rsi = f"{float(tech.rsi_14):.0f}" if tech and tech.rsi_14 else None
    macd_h = f"{float(tech.macd_histogram):.2f}" if tech and tech.macd_histogram else None
    sma50 = f"${float(tech.sma_50):.2f}" if tech and tech.sma_50 else None
    sma200 = f"${float(tech.sma_200):.2f}" if tech and tech.sma_200 else None
    support = f"${float(tech.support):.2f}" if tech and tech.support else None
    resistance = f"${float(tech.resistance):.2f}" if tech and tech.resistance else None
    trend = tech.trend if tech else "unknown"
    vol_trend = tech.volume_trend if tech else "normal"

    # Factor summary
    factors_aligned = sum(1 for s in [score.volume_score, score.price_score, score.flow_score, score.risk_reward_score] if s >= 16)

    if strat == "Momentum":
        parts = [f"{sym} is in a strong {trend}"]
        if rsi:
            parts.append(f"with RSI at {rsi} (healthy momentum zone)")
        if macd_h:
            parts.append(f"and MACD histogram positive at {macd_h}")
        if vol_trend == "increasing":
            parts.append("Volume is above average, confirming buying pressure.")
        else:
            parts.append(f"{factors_aligned} of 4 factors are aligned.")
        return ". ".join(parts[:2]) + ". " + parts[-1]

    if strat == "Volume Spike":
        base = f"{sym} shows unusual volume activity — significantly above the 20-day average."
        if trend == "uptrend":
            return base + " Combined with an uptrend, this suggests institutional accumulation. Watch for a breakout continuation."
        elif trend == "downtrend":
            return base + " In a downtrend, high volume may signal capitulation or distribution. Proceed with caution."
        return base + f" {factors_aligned} of 4 scoring factors are favorable. Monitor for directional confirmation."

    if strat == "Breakout":
        base = f"{sym} is trading near its resistance level"
        if resistance:
            base += f" at {resistance}"
        base += "."
        if vol_trend == "increasing":
            return base + " Volume is rising, which increases the probability of a successful breakout. A close above resistance confirms the move."
        return base + f" Risk/reward ratio is {score.risk_reward_ratio}. Watch for volume confirmation before entering."

    if strat == "Oversold Bounce":
        base = f"{sym}'s RSI dropped to {rsi} (oversold territory below 30)" if rsi else f"{sym} is in oversold territory"
        if support:
            base += f". Price is near the {support} support level with a {score.risk_reward_ratio} risk/reward ratio"
        base += "."
        return base + " Historically, extreme oversold readings tend to produce short-term bounces. Look for RSI turning up as confirmation."

    if strat == "Mean Reversion":
        return f"{sym} has pulled back significantly from its mean in a {trend}. Price is extended below the 20-day moving average, suggesting a potential reversion. This is a counter-trend play — use tight stops and smaller position sizes."

    if strat == "Golden Cross":
        base = f"{sym}'s 50-day moving average just crossed above the 200-day moving average"
        if sma50 and sma200:
            base += f" ({sma50} > {sma200})"
        return base + ". This is one of the most watched bullish signals — it historically precedes sustained uptrends. Long-term investors often use this as a buy signal."

    if strat == "Death Cross":
        base = f"{sym}'s 50-day MA just crossed below the 200-day MA"
        if sma50 and sma200:
            base += f" ({sma50} < {sma200})"
        return base + ". This bearish signal historically precedes extended downtrends. Consider reducing exposure or waiting for stabilization."

    if strat == "Insider Accumulation":
        return f"Multiple corporate insiders purchased {sym} stock within 7 days (cluster buy). This is one of the strongest bullish signals — insiders buying together often precedes positive catalysts. They know their company best."

    if strat == "Congress Buying":
        return f"Members of Congress from both parties have been buying {sym}. Bipartisan congressional buying can indicate upcoming favorable legislation or sector tailwinds. Note: trades are disclosed with up to 45-day delay."

    if strat == "Earnings Catalyst":
        return f"{sym} has earnings approaching within 14 days and the technical setup is favorable. Earnings can produce 5-15% moves in either direction. Consider options strategies to define risk around the event."

    if strat == "Dividend Play":
        return f"{sym} offers an attractive dividend yield above 3%. With stable fundamentals, this provides income while you wait. Check ex-dividend date timing — buy before ex-date to capture the next payment."

    if strat == "Bollinger Squeeze":
        return f"{sym}'s Bollinger Bands are narrowing (low volatility squeeze). Volatility contraction typically precedes a large directional move. The direction isn't known yet — wait for the breakout, then enter with the trend."

    if strat == "Support Bounce":
        base = f"{sym} is testing a key support level"
        if support:
            base += f" at {support}"
        return base + f". Risk/reward is {score.risk_reward_ratio} — defined risk below support with upside to resistance. This is a high-probability entry when support holds."

    if strat == "Gap Fill":
        return f"{sym} has a price gap that is filling back toward the pre-gap level. Gap fills are common — about 70% of gaps fill within a few weeks. This is a reversion trade with a clear target at the gap close."

    if strat == "Sector Leader":
        return f"{sym} is the top performer in its sector, which is currently seeing positive money inflows. Leading stocks in leading sectors tend to outperform. Ride the sector rotation momentum."

    # Neutral / fallback
    return f"{sym} shows no clear trading setup at this time. {factors_aligned} of 4 factors are favorable. Consider waiting for a stronger signal alignment before entering a position."
