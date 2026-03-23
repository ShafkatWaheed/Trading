"""Congressional trade analysis: politician buy/sell signals."""

from dataclasses import dataclass, field

from src.models.data_types import CongressTradesSummary


DISCLAIMER = (
    "Congressional trades have a 45-day disclosure delay "
    "and may not reflect current positions."
)


@dataclass
class CongressSignalScore:
    score: int  # -1 to +1
    signal: str  # bullish / bearish / mixed / no_data
    bipartisan: bool = False
    factors: list[str] = field(default_factory=list)
    disclaimer: str = DISCLAIMER


def analyze(summary: CongressTradesSummary) -> CongressSignalScore:
    if summary.total_trades == 0:
        return CongressSignalScore(score=0, signal="no_data", factors=["No congressional trades found"])

    score = 0
    factors: list[str] = []

    # Net sentiment from buy/sell ratio
    if summary.net_sentiment == "bullish":
        score += 1
        factors.append(
            f"Congress net bullish — {summary.total_buys} buys vs {summary.total_sells} sells "
            f"by {summary.unique_politicians} politicians"
        )
    elif summary.net_sentiment == "bearish":
        score -= 1
        factors.append(
            f"Congress net bearish — {summary.total_sells} sells vs {summary.total_buys} buys "
            f"by {summary.unique_politicians} politicians"
        )
    else:
        factors.append(
            f"Mixed congressional activity — {summary.total_buys} buys, {summary.total_sells} sells"
        )

    # Bipartisan check
    bipartisan = False
    pb = summary.party_breakdown
    if len(pb) >= 2:
        parties_buying = []
        for party, counts in pb.items():
            if counts.get("buy", 0) > counts.get("sell", 0):
                parties_buying.append(party)

        if len(parties_buying) >= 2:
            bipartisan = True
            factors.append(f"Bipartisan buying signal — both {' and '.join(parties_buying)} are net buyers")

    score = max(-1, min(1, score))

    if score > 0:
        signal = "bullish"
    elif score < 0:
        signal = "bearish"
    else:
        signal = "mixed"

    return CongressSignalScore(
        score=score,
        signal=signal,
        bipartisan=bipartisan,
        factors=factors,
    )
