"""Layer 1: confidence decay over time.

A pure function that returns the *effective* confidence of an edge given its
base confidence weight and how long ago the edge was last validated. The
decay halves the confidence every `half_life_days` (default 540 ≈ 18 months)
so an unmaintained edge fades from 1.0 → 0.5 → 0.25 → 0.125 over multiple years.

Used by query-time scoring (multiply edge weight by `effective_confidence`)
and by the orchestrator to flag stocks whose primary edges have decayed
below a threshold.
"""

from __future__ import annotations

from datetime import datetime, timezone


# Half-life in days. Tweak globally here if the prototype's edge-quality
# half-life turns out to be different in practice.
DEFAULT_HALF_LIFE_DAYS: int = 540


def parse_isoformat(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # SQLite typically stores ISO 8601 with 'Z' or +00:00; Python tolerates both.
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def effective_confidence(
    base: float,
    as_of: str | datetime | None,
    *,
    half_life_days: int = DEFAULT_HALF_LIFE_DAYS,
    now: datetime | None = None,
) -> float:
    """Return base confidence × 0.5 ** (age_days / half_life_days).

    Inputs:
        base: starting confidence weight in [0..1]
        as_of: edge timestamp (ISO string OR datetime); None → 0 (treat as fully decayed)
        now: optional override for the "current time" — useful for tests

    Returns 0..base.
    """
    if base <= 0:
        return 0.0
    ts = as_of if isinstance(as_of, datetime) else parse_isoformat(as_of)
    if ts is None:
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    age_days = max(0.0, (current - ts).total_seconds() / 86400.0)
    return base * (0.5 ** (age_days / max(1.0, half_life_days)))


def is_stale(
    as_of: str | datetime | None,
    *,
    threshold_confidence: float = 0.5,
    base: float = 1.0,
    half_life_days: int = DEFAULT_HALF_LIFE_DAYS,
    now: datetime | None = None,
) -> bool:
    """True if effective_confidence has fallen below `threshold_confidence`.

    Default threshold (0.5) corresponds to one full half-life since `as_of`.
    """
    return effective_confidence(
        base, as_of, half_life_days=half_life_days, now=now
    ) < threshold_confidence
