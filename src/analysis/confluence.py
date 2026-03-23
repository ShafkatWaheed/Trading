"""Signal confluence detection: identify agreement/divergence across all signals."""

from dataclasses import dataclass, field


@dataclass
class SignalInput:
    name: str
    score: int
    max_score: int
    label: str


@dataclass
class ConfluenceResult:
    alignment: str  # strong_agreement / moderate_agreement / mixed / divergent
    confidence_adjustment: int  # -1, 0, or +1
    agreements: list[str] = field(default_factory=list)
    divergences: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Notable divergence patterns to flag
_DIVERGENCE_PATTERNS = [
    ({"smart_money"}, {"technical"}, "Smart money diverges from price action — insiders see what charts don't"),
    ({"macro"}, {"fundamental"}, "Strong company in tough macro environment — may face headwinds"),
    ({"options"}, {"congress"}, "Options market and politicians disagree — proceed with caution"),
    ({"smart_money"}, {"sentiment"}, "Insiders and news sentiment conflict — insiders often lead"),
    ({"technical"}, {"fundamental"}, "Price trend diverges from fundamentals — potential mean reversion"),
]


def analyze(signals: list[SignalInput]) -> ConfluenceResult:
    if not signals:
        return ConfluenceResult(alignment="mixed", confidence_adjustment=0)

    # Classify each signal direction
    bullish: list[str] = []
    bearish: list[str] = []
    neutral: list[str] = []

    for s in signals:
        if s.score > 0:
            bullish.append(s.name)
        elif s.score < 0:
            bearish.append(s.name)
        else:
            neutral.append(s.name)

    total_directional = len(bullish) + len(bearish)
    if total_directional == 0:
        return ConfluenceResult(
            alignment="mixed",
            confidence_adjustment=0,
            agreements=["All signals neutral"],
        )

    # Determine alignment
    bullish_ratio = len(bullish) / total_directional
    agreements: list[str] = []
    divergences: list[str] = []
    warnings: list[str] = []

    if bullish_ratio >= 0.9 or bullish_ratio <= 0.1:
        # Near-unanimous agreement
        alignment = "strong_agreement"
        confidence_adj = 1
        direction = "bullish" if bullish_ratio >= 0.9 else "bearish"
        agreements.append(f"Near-unanimous {direction} signal across {total_directional} indicators")
    elif bullish_ratio >= 0.67 or bullish_ratio <= 0.33:
        # Majority agreement
        alignment = "moderate_agreement"
        confidence_adj = 0
        majority = bullish if bullish_ratio >= 0.67 else bearish
        minority = bearish if bullish_ratio >= 0.67 else bullish
        agreements.append(f"Majority agreement: {', '.join(majority)} align")
        if minority:
            divergences.append(f"Minority dissent: {', '.join(minority)}")
    else:
        # Split signals
        alignment = "mixed"
        confidence_adj = 0
        divergences.append(f"Bullish: {', '.join(bullish)}")
        divergences.append(f"Bearish: {', '.join(bearish)}")

    # Check for specific divergence patterns
    bullish_set = set(bullish)
    bearish_set = set(bearish)

    for positive_group, negative_group, warning_msg in _DIVERGENCE_PATTERNS:
        if (positive_group & bullish_set and negative_group & bearish_set) or \
           (positive_group & bearish_set and negative_group & bullish_set):
            warnings.append(warning_msg)

    # Strong contradictions downgrade confidence
    strong_signals = {s.name for s in signals if abs(s.score) == s.max_score}
    strong_bull = strong_signals & bullish_set
    strong_bear = strong_signals & bearish_set
    if strong_bull and strong_bear:
        alignment = "divergent"
        confidence_adj = -1
        warnings.append(
            f"Strong signals conflict: {', '.join(strong_bull)} strongly bullish "
            f"vs {', '.join(strong_bear)} strongly bearish"
        )

    return ConfluenceResult(
        alignment=alignment,
        confidence_adjustment=confidence_adj,
        agreements=agreements,
        divergences=divergences,
        warnings=warnings,
    )
