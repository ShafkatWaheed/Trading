"""Composite multi-channel confidence for stock_relations edges.

Each edge in stock_relations is supported by zero or more independent
evidence channels. The composite confidence is a 0..1 score that increases
with the number and quality of channels.

Channels currently considered (cheap — derived from columns already on the
row, no extra queries):

  * `hand_seed`     — `evidence LIKE 'seed:hand%'`.  Manually curated +
                      audited by a human; strongest single signal.
                      Contribution: 0.50
  * `disclosed_pct` — `concentration_pct IS NOT NULL`.  10-K Item 101
                      disclosure of customer concentration %. Reg-mandated.
                      Contribution: 0.40 (scaled by pct: 10%=0.20, 30%+=0.40)
  * `tenk_named`    — `evidence LIKE '10k_mined:%'`.  Named in a 10-K Item
                      1A but without a quantitative %. Weaker than disclosed.
                      Contribution: 0.20
  * `recent`        — `last_verified_at` within the last 540 days.  Even an
                      otherwise-weak edge gains confidence when it's been
                      re-verified recently.
                      Contribution: 0.10

Future channels (additive — call sites will pass them in once the data
layers mature):

  * `news_co_mention`     — N articles in last 90d mentioning both sides
  * `return_correlation`  — 60-day Pearson r > 0.3 with appropriate sign
  * `etf_co_holding`      — held in the same ETF basket

Combined score is clamped to [0, 1]. The function is pure — call sites
batch-update rows from a single SELECT.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


HAND_SEED_WEIGHT       = 0.50
DISCLOSED_PCT_BASE     = 0.40   # at >=30% concentration
TENK_NAMED_WEIGHT      = 0.20
RECENT_VERIFIED_WEIGHT = 0.10
RECENT_WINDOW_DAYS     = 540


def _pct_channel_score(concentration_pct: float | None) -> float:
    """Map disclosed % to channel contribution. Mirrors the strength ladder:
        >= 30 → full 0.40
        20..30 → 0.30
        10..20 → 0.20
        < 10 → 0
    """
    if concentration_pct is None:
        return 0.0
    if concentration_pct >= 30:
        return DISCLOSED_PCT_BASE
    if concentration_pct >= 20:
        return 0.30
    if concentration_pct >= 10:
        return 0.20
    return 0.0


def _recent_channel_score(last_verified_at: str | None, *, now: datetime | None = None) -> float:
    """Edges verified within the last RECENT_WINDOW_DAYS contribute extra."""
    if not last_verified_at:
        return 0.0
    try:
        ts = datetime.fromisoformat(last_verified_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    age = now - ts
    if age < timedelta(days=RECENT_WINDOW_DAYS):
        return RECENT_VERIFIED_WEIGHT
    return 0.0


def composite_confidence_score(
    *,
    evidence: str | None,
    concentration_pct: float | None,
    last_verified_at: str | None,
    now: datetime | None = None,
) -> float:
    """Score an edge from its column values. Pure function — easy to test."""
    score = 0.0
    ev = (evidence or "").lower()

    if ev.startswith("seed:hand"):
        score += HAND_SEED_WEIGHT
    elif ev.startswith("10k_mined"):
        score += TENK_NAMED_WEIGHT

    score += _pct_channel_score(concentration_pct)
    score += _recent_channel_score(last_verified_at, now=now)

    if score > 1.0:
        score = 1.0
    if score < 0.0:
        score = 0.0
    return round(score, 3)


def recompute_for_all(conn) -> dict:
    """Walk every stock_relations row and write composite_confidence.

    Returns {"updated": N}. Idempotent: a re-run on unchanged data yields
    the same values.
    """
    rows = conn.execute(
        "SELECT from_symbol, to_symbol, relation_type, evidence, "
        "       concentration_pct, last_verified_at "
        "FROM stock_relations"
    ).fetchall()
    updated = 0
    for r in rows:
        score = composite_confidence_score(
            evidence=r["evidence"],
            concentration_pct=r["concentration_pct"],
            last_verified_at=r["last_verified_at"],
        )
        conn.execute(
            "UPDATE stock_relations SET composite_confidence = ? "
            "WHERE from_symbol = ? AND to_symbol = ? AND relation_type = ?",
            (score, r["from_symbol"], r["to_symbol"], r["relation_type"]),
        )
        updated += 1
    conn.commit()
    return {"updated": updated}
