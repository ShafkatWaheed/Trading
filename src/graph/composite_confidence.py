"""Composite multi-channel confidence for stock_relations edges.

Each edge in stock_relations is supported by zero or more independent
evidence channels. The composite confidence is a 0..1 score that increases
with the number and quality of channels.

Channels:

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
  * `etf_co_holding`— Count of ETFs holding both ends of the edge. Cheap +
                      local (no network — loaded from data/index_cache).
                      Contribution: 0.04 per ETF, capped at 0.15 (4+ ETFs).
  * `pair_correlation` — 60-day Pearson r between the two symbols' daily
                      returns. Caller supplies it via an injectable fetcher.
                      Contribution: |r|>=0.5 → 0.15; |r|>=0.3 → 0.08; else 0.

Future channel (still unwired — needs news ingestion):

  * `news_co_mention`     — N articles in last 90d mentioning both sides

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
ETF_CO_HOLDING_PER     = 0.04
ETF_CO_HOLDING_CAP     = 0.15   # 4 ETFs maxes out the channel
CORRELATION_HIGH       = 0.50   # |r| >= 0.50 → strong corr
CORRELATION_MEDIUM     = 0.30   # |r| >= 0.30 → medium corr
CORRELATION_HIGH_WEIGHT   = 0.15
CORRELATION_MEDIUM_WEIGHT = 0.08
NEWS_CO_MENTION_HIGH   = 6      # 6+ co-mentions in last 90d → strong signal
NEWS_CO_MENTION_MED    = 3      # 3..5 → medium
NEWS_CO_MENTION_HIGH_WEIGHT = 0.10
NEWS_CO_MENTION_MED_WEIGHT  = 0.06
NEWS_CO_MENTION_LOW_WEIGHT  = 0.03    # 1..2 → small signal (could be noise)


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


def _etf_channel_score(etf_co_holding_count: int | None) -> float:
    """Each shared ETF contributes 0.04, capped at 0.15 (4+ ETFs)."""
    if not etf_co_holding_count or etf_co_holding_count <= 0:
        return 0.0
    return min(etf_co_holding_count * ETF_CO_HOLDING_PER, ETF_CO_HOLDING_CAP)


def _correlation_channel_score(pair_correlation: float | None) -> float:
    """Map |r| to a channel contribution.

    Caller supplies the Pearson r; we use its absolute value so substitute
    edges (negative correlation expected) get credit too.
    """
    if pair_correlation is None:
        return 0.0
    try:
        r = abs(float(pair_correlation))
    except (TypeError, ValueError):
        return 0.0
    if r >= CORRELATION_HIGH:
        return CORRELATION_HIGH_WEIGHT
    if r >= CORRELATION_MEDIUM:
        return CORRELATION_MEDIUM_WEIGHT
    return 0.0


def _news_channel_score(news_co_mention_count: int | None) -> float:
    """3 tiers based on how many recent articles mention both endpoints."""
    if not news_co_mention_count or news_co_mention_count <= 0:
        return 0.0
    if news_co_mention_count >= NEWS_CO_MENTION_HIGH:
        return NEWS_CO_MENTION_HIGH_WEIGHT
    if news_co_mention_count >= NEWS_CO_MENTION_MED:
        return NEWS_CO_MENTION_MED_WEIGHT
    return NEWS_CO_MENTION_LOW_WEIGHT


def count_news_co_mentions(
    target: str,
    other: str,
    *,
    articles_for_target: list[dict],
    other_aliases: list[str] | None = None,
) -> int:
    """How many of `target`'s recent articles also mention `other`?

    Pure function — caller supplies pre-fetched articles (cached news avoids
    network in the hot path). Match is case-insensitive against `title` +
    `content_snippet`; `other_aliases` adds company names beyond the bare
    ticker (e.g. ['Microsoft', 'MSFT.US'] for MSFT).
    """
    if not articles_for_target:
        return 0
    needles = {other.lower()}
    if other_aliases:
        for alias in other_aliases:
            if alias:
                needles.add(alias.lower())
    count = 0
    for art in articles_for_target:
        text = ((art.get("title") or "") + " " + (art.get("content_snippet") or "")).lower()
        if any(n in text for n in needles):
            count += 1
    return count


def composite_confidence_score(
    *,
    evidence: str | None,
    concentration_pct: float | None,
    last_verified_at: str | None,
    etf_co_holding_count: int | None = None,
    pair_correlation: float | None = None,
    news_co_mention_count: int | None = None,
    now: datetime | None = None,
) -> float:
    """Score an edge from its column values + optional cross-channel signals.

    Pure function — easy to test. Caller passes channel inputs they have;
    omitted channels contribute 0.
    """
    score = 0.0
    ev = (evidence or "").lower()

    if ev.startswith("seed:hand"):
        score += HAND_SEED_WEIGHT
    elif ev.startswith("10k_mined"):
        score += TENK_NAMED_WEIGHT

    score += _pct_channel_score(concentration_pct)
    score += _recent_channel_score(last_verified_at, now=now)
    score += _etf_channel_score(etf_co_holding_count)
    score += _correlation_channel_score(pair_correlation)
    score += _news_channel_score(news_co_mention_count)

    if score > 1.0:
        score = 1.0
    if score < 0.0:
        score = 0.0
    return round(score, 3)


def _etf_co_holding_count(
    a: str, b: str, etf_holdings: dict[str, set[str]] | None,
) -> int:
    """How many ETFs hold both `a` and `b`."""
    if not etf_holdings:
        return 0
    return sum(1 for syms in etf_holdings.values() if a in syms and b in syms)


def recompute_for_all(
    conn,
    *,
    etf_holdings: dict[str, set[str]] | None = None,
    correlation_fn=None,
    news_co_mention_fn=None,
) -> dict:
    """Walk every stock_relations row and write composite_confidence.

    `etf_holdings` (e.g. from `src.data.index_loader.load_all_cached()`):
        {index_name: set(tickers)}.  Provide to enable the ETF co-holding
        channel; pass None to skip (channel scores 0).

    `correlation_fn(a, b) -> float | None`:
        Pearson r between A and B's recent returns. Provide to enable the
        return-correlation channel; pass None to skip. Exceptions swallowed.

    `news_co_mention_fn(a, b) -> int | None`:
        Count of recent articles mentioning both. Provide to enable the
        news-co-mention channel; pass None to skip. Exceptions swallowed.

    Returns {"updated": N}. Idempotent.
    """
    rows = conn.execute(
        "SELECT from_symbol, to_symbol, relation_type, evidence, "
        "       concentration_pct, last_verified_at "
        "FROM stock_relations"
    ).fetchall()
    updated = 0
    for r in rows:
        a, b = r["from_symbol"], r["to_symbol"]
        etf_count = _etf_co_holding_count(a, b, etf_holdings)
        corr: float | None = None
        if correlation_fn is not None:
            try:
                corr = correlation_fn(a, b)
            except Exception:
                corr = None
        news_count: int | None = None
        if news_co_mention_fn is not None:
            try:
                news_count = news_co_mention_fn(a, b)
            except Exception:
                news_count = None

        score = composite_confidence_score(
            evidence=r["evidence"],
            concentration_pct=r["concentration_pct"],
            last_verified_at=r["last_verified_at"],
            etf_co_holding_count=etf_count,
            pair_correlation=corr,
            news_co_mention_count=news_count,
        )
        conn.execute(
            "UPDATE stock_relations SET composite_confidence = ? "
            "WHERE from_symbol = ? AND to_symbol = ? AND relation_type = ?",
            (score, a, b, r["relation_type"]),
        )
        updated += 1
    conn.commit()
    return {"updated": updated}
