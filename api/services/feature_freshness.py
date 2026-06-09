"""Per-feature staleness checks for the UI banner.

Each feature page in the frontend can ask "is my data fresh?" via
GET /freshness/feature/{name} and render a banner when staleness is
detected. This catches the "All Clear" bug class — when the backend
returns an empty/stale response that the UI renders as if it were
fresh.

Each feature defines:
  - "what cache keys / DB rows back this page?"
  - "how old is too old?"

The check returns:
  {
    stale: bool,
    last_updated: str | None,   # iso timestamp
    age_minutes: int | None,
    reason: str | None,         # human-readable e.g. "scores last computed 53h ago"
  }

If any backing source is older than its threshold, stale=true and
`reason` names the worst offender.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from src.utils.db import get_connection, init_db


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Tolerant — strip "Z" suffix and trailing tz info, treat as UTC if naive
        s2 = s.rstrip("Z")
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _age_minutes(ts: datetime | None) -> int | None:
    if ts is None:
        return None
    return int((_utcnow() - ts).total_seconds() / 60)


def _check_threshold(
    label: str, ts: datetime | None, threshold_minutes: int
) -> tuple[bool, str | None, int | None]:
    """Return (stale, reason, age_min) for one source."""
    age = _age_minutes(ts)
    if age is None:
        return True, f"{label} never recorded", None
    if age > threshold_minutes:
        hrs = age / 60
        return True, f"{label} is {hrs:.0f}h old (>{threshold_minutes // 60}h threshold)", age
    return False, None, age


def _latest_from_cache(prefix: str) -> datetime | None:
    """Return the newest created_at for any cache key starting with `prefix`."""
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(created_at) AS ts FROM cache WHERE key LIKE ?",
            (f"{prefix}:%",),
        ).fetchone()
    finally:
        conn.close()
    return _parse_iso(row["ts"]) if row and row["ts"] else None


def _latest_precomputed_scores() -> datetime | None:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(computed_at) AS ts FROM precomputed_scores"
        ).fetchone()
    finally:
        conn.close()
    return _parse_iso(row["ts"]) if row and row["ts"] else None


def _latest_prediction_actuals() -> datetime | None:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(recorded_at) AS ts FROM daily_prediction_actuals"
        ).fetchone()
    finally:
        conn.close()
    return _parse_iso(row["ts"]) if row and row["ts"] else None


# ── Feature checks ──────────────────────────────────────────────────


def check_predictions() -> dict:
    """Predictions depend on precomputed_scores (5:30 ET nightly job) +
    per-symbol cached signals. Stale if scores >36h old."""
    scores_ts = _latest_precomputed_scores()
    stale, reason, age = _check_threshold("precomputed scores", scores_ts, 36 * 60)
    return {
        "stale":        stale,
        "last_updated": scores_ts.isoformat() if scores_ts else None,
        "age_minutes":  age,
        "reason":       reason,
    }


def check_brief() -> dict:
    """Brief uses today's market context — cached pulse + news. Stale if
    cached brief itself >24h or the pulse keys >12h."""
    brief_ts = _latest_from_cache("brief:v8")
    pulse_ts = _latest_from_cache("market:pulse")
    worst = None
    worst_reason = None
    worst_age = None
    for label, ts, threshold in [
        ("brief output",  brief_ts, 24 * 60),
        ("market pulse",  pulse_ts, 12 * 60),
    ]:
        s, r, a = _check_threshold(label, ts, threshold)
        if s and (worst_age is None or (a or 0) > (worst_age or 0)):
            worst = ts
            worst_reason = r
            worst_age = a
    return {
        "stale":        worst is not None or worst_reason is not None,
        "last_updated": brief_ts.isoformat() if brief_ts else None,
        "age_minutes":  _age_minutes(brief_ts),
        "reason":       worst_reason,
    }


def check_market_pulse() -> dict:
    """Market pulse depends on FRED + sector flows. Stale if any pulse
    key >12h old (most refresh on a 4-6h cadence)."""
    pulse_ts = _latest_from_cache("market:pulse")
    stale, reason, age = _check_threshold("market pulse", pulse_ts, 12 * 60)
    return {
        "stale":        stale,
        "last_updated": pulse_ts.isoformat() if pulse_ts else None,
        "age_minutes":  age,
        "reason":       reason,
    }


def check_daily_picks() -> dict:
    """Daily picks share the precomputed_scores pipeline + Claude personalities.
    Stale if either scores >36h or no fresh daily_picks_v1 cache for today."""
    scores_ts = _latest_precomputed_scores()
    picks_ts = _latest_from_cache("daily_picks_v1")
    worst_reason = None
    age_to_show = None
    for label, ts, threshold in [
        ("precomputed scores", scores_ts, 36 * 60),
        ("daily picks cache",  picks_ts, 24 * 60),
    ]:
        s, r, a = _check_threshold(label, ts, threshold)
        if s and worst_reason is None:
            worst_reason = r
            age_to_show = a
    return {
        "stale":        worst_reason is not None,
        "last_updated": (picks_ts or scores_ts).isoformat() if (picks_ts or scores_ts) else None,
        "age_minutes":  age_to_show,
        "reason":       worst_reason,
    }


def check_accuracy() -> dict:
    """Predictions accuracy depends on EOD actuals being recorded. Stale
    if no actuals row in the last 48h (markets typically close 5d/week,
    so 48h covers a Friday → Monday gap with margin)."""
    actuals_ts = _latest_prediction_actuals()
    stale, reason, age = _check_threshold("prediction actuals", actuals_ts, 48 * 60)
    return {
        "stale":        stale,
        "last_updated": actuals_ts.isoformat() if actuals_ts else None,
        "age_minutes":  age,
        "reason":       reason,
    }


_FEATURES = {
    "predictions":   check_predictions,
    "brief":         check_brief,
    "market_pulse":  check_market_pulse,
    "daily_picks":   check_daily_picks,
    "accuracy":      check_accuracy,
}


def get_feature_freshness(name: str) -> dict:
    """Look up the freshness checker by feature name."""
    fn = _FEATURES.get(name)
    if not fn:
        return {
            "stale":        False,
            "last_updated": None,
            "age_minutes":  None,
            "reason":       f"unknown feature: {name}",
        }
    return fn()


def get_all_features_freshness() -> dict:
    """Run every feature check at once — useful for a dashboard panel."""
    return {name: fn() for name, fn in _FEATURES.items()}
