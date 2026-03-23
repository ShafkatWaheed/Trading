"""Options flow analysis: score market sentiment from options data."""

from dataclasses import dataclass, field
from decimal import Decimal

from src.models.data_types import OptionsSummary


@dataclass
class OptionsFlowScore:
    signal: str  # bullish / bearish / neutral
    score: int  # -2 to +2
    put_call_interpretation: str = ""
    iv_interpretation: str = ""
    unusual_activity_note: str = ""
    factors: list[str] = field(default_factory=list)


def analyze(summary: OptionsSummary) -> OptionsFlowScore:
    score = 0
    factors: list[str] = []

    # Put/Call ratio
    pcr = summary.put_call_ratio
    if pcr < Decimal("0.5"):
        score += 2
        pc_interp = f"Very bullish P/C ratio ({pcr})"
        factors.append(pc_interp)
    elif pcr < Decimal("0.7"):
        score += 1
        pc_interp = f"Bullish P/C ratio ({pcr})"
        factors.append(pc_interp)
    elif pcr > Decimal("1.3"):
        score -= 2
        pc_interp = f"Very bearish P/C ratio ({pcr})"
        factors.append(pc_interp)
    elif pcr > Decimal("1.0"):
        score -= 1
        pc_interp = f"Bearish P/C ratio ({pcr})"
        factors.append(pc_interp)
    else:
        pc_interp = f"Neutral P/C ratio ({pcr})"

    # IV rank
    iv_interp = ""
    if summary.iv_rank is not None:
        if summary.iv_rank > Decimal("80"):
            iv_interp = f"IV rank elevated at {summary.iv_rank}% — options expensive, high fear"
            factors.append(iv_interp)
        elif summary.iv_rank < Decimal("20"):
            iv_interp = f"IV rank low at {summary.iv_rank}% — options cheap, complacency"
            factors.append(iv_interp)

    # Unusual activity
    ua_note = ""
    if summary.unusual_activity:
        bullish = sum(1 for u in summary.unusual_activity if u.sentiment == "bullish")
        bearish = sum(1 for u in summary.unusual_activity if u.sentiment == "bearish")
        total = bullish + bearish

        if total > 0:
            if bullish > bearish * 2:
                score += 1
                ua_note = f"Unusual activity skews bullish ({bullish} bullish vs {bearish} bearish)"
                factors.append(ua_note)
            elif bearish > bullish * 2:
                score -= 1
                ua_note = f"Unusual activity skews bearish ({bearish} bearish vs {bullish} bullish)"
                factors.append(ua_note)
            else:
                ua_note = f"Mixed unusual activity ({bullish} bullish, {bearish} bearish)"

    score = max(-2, min(2, score))

    if score >= 1:
        signal = "bullish"
    elif score <= -1:
        signal = "bearish"
    else:
        signal = "neutral"

    return OptionsFlowScore(
        signal=signal,
        score=score,
        put_call_interpretation=pc_interp,
        iv_interpretation=iv_interp,
        unusual_activity_note=ua_note,
        factors=factors,
    )
