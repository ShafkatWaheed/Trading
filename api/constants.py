"""Shared API constants."""
from __future__ import annotations


# Period label → number of trading days. Used by every service that has
# a 1D / 1W / 1M / 3M / 6M / 1Y selector.
PERIOD_DAYS: dict[str, int] = {
    "1D": 1,
    "1W": 5,
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
}

PERIOD_LABELS: list[str] = list(PERIOD_DAYS.keys())


def resolve_period(period: str, default: str = "1M") -> tuple[str, int]:
    """Return (period_label, lookback_days). Falls back to default on bad input."""
    if period in PERIOD_DAYS:
        return period, PERIOD_DAYS[period]
    return default, PERIOD_DAYS[default]
