"""Layer 4: peer-correlation drift detector.

Catches the PLTR-style identity shift: if a stock's 90-day rolling correlation
with its tagged peers drops sharply from a long-term baseline, its peer tags
are stale and should be re-extracted.

Pure function on supplied price-return series; the orchestrator plugs in real
data via the price layer or a backtest fixture.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.analysis.commodity_validator import pearson_correlation


# A drop of this magnitude in the rolling correlation triggers a "needs review"
# flag. Empirical threshold; tune in practice.
DEFAULT_DRIFT_THRESHOLD: float = 0.30


@dataclass(frozen=True)
class DriftResult:
    """Output of one symbol's drift check vs its tagged peers."""
    symbol: str
    baseline_correlation: float | None
    recent_correlation: float | None
    drift: float | None                      # baseline - recent
    drifted: bool
    sample_size_baseline: int
    sample_size_recent: int


def average_correlation(
    target_returns: Sequence[float],
    peer_returns: list[Sequence[float]],
) -> float | None:
    """Mean Pearson correlation between target and each peer.

    Returns None if peer_returns is empty.
    """
    if not peer_returns:
        return None
    corrs = []
    for series in peer_returns:
        c = pearson_correlation(target_returns, series)
        corrs.append(c)
    if not corrs:
        return None
    return sum(corrs) / len(corrs)


def detect_drift(
    symbol: str,
    *,
    baseline_target: Sequence[float],
    baseline_peers: list[Sequence[float]],
    recent_target: Sequence[float],
    recent_peers: list[Sequence[float]],
    threshold: float = DEFAULT_DRIFT_THRESHOLD,
) -> DriftResult:
    """Compare baseline-window vs recent-window peer correlation.

    Args:
        symbol: stock ticker
        baseline_target: target's daily returns over the baseline window (e.g. 1Y from 2Y ago)
        baseline_peers: list of peer return series over the same window
        recent_target: target's returns over recent window (e.g. last 90 days)
        recent_peers: list of peer return series over the recent window
        threshold: how big a drop in correlation triggers the alert

    Returns DriftResult with drifted=True if the drop > threshold.
    """
    base_corr = average_correlation(baseline_target, baseline_peers)
    recent_corr = average_correlation(recent_target, recent_peers)

    drift = None
    drifted = False
    if base_corr is not None and recent_corr is not None:
        drift = base_corr - recent_corr
        drifted = drift > threshold

    return DriftResult(
        symbol=symbol,
        baseline_correlation=base_corr,
        recent_correlation=recent_corr,
        drift=drift,
        drifted=drifted,
        sample_size_baseline=len(baseline_target) if baseline_target else 0,
        sample_size_recent=len(recent_target) if recent_target else 0,
    )
