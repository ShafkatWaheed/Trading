"""Smart money analysis: insider + institutional behavior signals."""

from dataclasses import dataclass, field

from src.models.data_types import InsiderSummary, InstitutionalSummary


@dataclass
class SmartMoneyScore:
    score: int  # -2 to +2
    insider_signal: str  # buying / selling / neutral
    institutional_signal: str  # accumulating / distributing / neutral
    cluster_buy_detected: bool = False
    factors: list[str] = field(default_factory=list)


def analyze(
    insider: InsiderSummary | None = None,
    institutional: InstitutionalSummary | None = None,
) -> SmartMoneyScore:
    score = 0
    factors: list[str] = []
    insider_signal = "neutral"
    institutional_signal = "neutral"
    cluster_buy = False

    # Insider analysis (Form 4)
    if insider is not None:
        if insider.cluster_buy:
            score += 2
            cluster_buy = True
            factors.append(f"Cluster buy detected — {insider.unique_insiders} insiders buying within 7 days")

        if insider.signal == "strong buy":
            score += 2
            insider_signal = "buying"
            factors.append(f"Strong insider buying ({insider.total_buys} buys vs {insider.total_sells} sells)")
        elif insider.signal == "buy":
            score += 1
            insider_signal = "buying"
            factors.append(f"Net insider buying ({insider.total_buys} buys vs {insider.total_sells} sells)")
        elif insider.signal == "sell":
            score -= 1
            insider_signal = "selling"
            factors.append(f"Net insider selling ({insider.total_sells} sells vs {insider.total_buys} buys)")
        elif insider.signal == "strong sell":
            score -= 2
            insider_signal = "selling"
            factors.append(f"Heavy insider selling ({insider.total_sells} sells)")

    # Institutional analysis (Form 13F)
    if institutional is not None:
        net = institutional.net_change_shares
        new_vs_closed = institutional.new_positions - institutional.closed_positions

        if net > 0 and new_vs_closed > 0:
            score += 1
            institutional_signal = "accumulating"
            factors.append(
                f"Institutional accumulation — {institutional.increased} funds increased, "
                f"{institutional.new_positions} new positions"
            )
        elif net < 0 and new_vs_closed < 0:
            score -= 1
            institutional_signal = "distributing"
            factors.append(
                f"Institutional distribution — {institutional.decreased} funds decreased, "
                f"{institutional.closed_positions} closed positions"
            )

    score = max(-2, min(2, score))

    return SmartMoneyScore(
        score=score,
        insider_signal=insider_signal,
        institutional_signal=institutional_signal,
        cluster_buy_detected=cluster_buy,
        factors=factors,
    )
