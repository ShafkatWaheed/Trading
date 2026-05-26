"""Tests for src.graph.composite_confidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.data.relations_seed_loader import load_spine
from src.data.universe_loader import load_tier_a
from src.graph.composite_confidence import (
    composite_confidence_score,
    count_news_co_mentions,
    recompute_for_all,
)
from src.utils.db import get_connection, init_db


NOW = datetime(2026, 5, 26, tzinfo=timezone.utc)


def test_hand_seed_alone_yields_baseline_score():
    """A hand-seeded edge with no other signals scores around the hand-seed
    weight (0.5)."""
    s = composite_confidence_score(
        evidence="seed:hand | NVDA's foundry",
        concentration_pct=None,
        last_verified_at=None,
        now=NOW,
    )
    assert abs(s - 0.5) < 0.001


def test_10k_mined_with_disclosed_pct_scores_above_hand_seed():
    """A 10-K disclosure with a quantified 25% concentration is the
    strongest combination short of also being hand-seeded — it adds the
    named-in-10K weight (0.2) AND the disclosed-pct channel (0.3 for 20-30)."""
    s = composite_confidence_score(
        evidence="10k_mined: 25% of revenue",
        concentration_pct=25,
        last_verified_at=None,
        now=NOW,
    )
    # 0.20 (10k named) + 0.30 (20..30 pct) = 0.50
    assert abs(s - 0.50) < 0.001


def test_recent_verification_adds_a_boost():
    """An otherwise weak 10k_mined edge gets a small bump if it was
    re-extracted in the last 540 days."""
    recent_iso = (NOW - timedelta(days=30)).isoformat()
    no_recent = composite_confidence_score(
        evidence="10k_mined: just named",
        concentration_pct=None,
        last_verified_at=None,
        now=NOW,
    )
    with_recent = composite_confidence_score(
        evidence="10k_mined: just named",
        concentration_pct=None,
        last_verified_at=recent_iso,
        now=NOW,
    )
    assert with_recent > no_recent
    assert abs(with_recent - no_recent - 0.10) < 0.001


def test_hand_seed_plus_disclosed_pct_clamps_at_1():
    """All channels lit: hand_seed (0.50) + disclosed 30%+ (0.40) + recent (0.10)
    = 1.00. Clamp keeps it at exactly 1."""
    recent_iso = (NOW - timedelta(days=10)).isoformat()
    s = composite_confidence_score(
        evidence="seed:hand | TSM is sole foundry",
        concentration_pct=40,
        last_verified_at=recent_iso,
        now=NOW,
    )
    assert s == 1.0


def test_stale_verification_does_not_contribute():
    """A verification older than 540 days no longer counts."""
    old_iso = (NOW - timedelta(days=700)).isoformat()
    s = composite_confidence_score(
        evidence="10k_mined: x",
        concentration_pct=None,
        last_verified_at=old_iso,
        now=NOW,
    )
    # 10k_named only = 0.20
    assert abs(s - 0.20) < 0.001


def test_invalid_last_verified_returns_zero_contribution():
    s = composite_confidence_score(
        evidence="seed:hand",
        concentration_pct=None,
        last_verified_at="not-a-date",
        now=NOW,
    )
    # Hand seed only
    assert abs(s - 0.50) < 0.001


def test_recompute_for_all_writes_score_per_row():
    """recompute_for_all walks every stock_relations row and populates the
    composite_confidence column. Verify a hand-seeded row gets exactly 0.5."""
    init_db()
    load_tier_a()
    load_spine()
    conn = get_connection()
    try:
        out = recompute_for_all(conn)
        assert out["updated"] >= 1

        # NVDA→TSM is hand-seeded with no concentration_pct — expect 0.50
        # (last_verified_at is NULL on hand-seed rows, no recent bump)
        row = conn.execute(
            "SELECT composite_confidence, evidence, concentration_pct "
            "FROM stock_relations "
            "WHERE from_symbol='NVDA' AND to_symbol='TSM' AND relation_type='supplier'"
        ).fetchone()
        assert row is not None
        assert row["evidence"].startswith("seed:hand")
        assert row["composite_confidence"] == 0.5
    finally:
        conn.close()


# ── new channels: ETF co-holding + return correlation ───────────


def test_etf_co_holding_adds_capped_contribution():
    """Each shared ETF adds 0.04, up to a cap of 0.15 (4 ETFs)."""
    # 0 shared → no contribution
    s0 = composite_confidence_score(
        evidence="10k_mined: x", concentration_pct=None, last_verified_at=None,
        etf_co_holding_count=0,
    )
    s1 = composite_confidence_score(
        evidence="10k_mined: x", concentration_pct=None, last_verified_at=None,
        etf_co_holding_count=1,
    )
    s4 = composite_confidence_score(
        evidence="10k_mined: x", concentration_pct=None, last_verified_at=None,
        etf_co_holding_count=4,
    )
    s10 = composite_confidence_score(
        evidence="10k_mined: x", concentration_pct=None, last_verified_at=None,
        etf_co_holding_count=10,
    )
    assert abs(s1 - s0 - 0.04) < 0.001
    # Cap at 0.15: 4 ETFs * 0.04 = 0.16 → clamped to 0.15
    assert abs(s4 - s0 - 0.15) < 0.001
    # More ETFs don't push past the cap
    assert s10 == s4


def test_pair_correlation_uses_absolute_value():
    """A strong negative correlation (substitute edge) gets the same channel
    weight as a strong positive correlation."""
    pos = composite_confidence_score(
        evidence="10k_mined: x", concentration_pct=None, last_verified_at=None,
        pair_correlation=0.70,
    )
    neg = composite_confidence_score(
        evidence="10k_mined: x", concentration_pct=None, last_verified_at=None,
        pair_correlation=-0.70,
    )
    weak = composite_confidence_score(
        evidence="10k_mined: x", concentration_pct=None, last_verified_at=None,
        pair_correlation=0.10,
    )
    assert pos == neg
    # |r|=0.70 ≥ 0.50 → high-correlation weight = 0.15
    assert abs(pos - 0.20 - 0.15) < 0.001
    # |r|=0.10 → 0 contribution
    assert weak == 0.20


def test_correlation_threshold_tiers():
    """Three tiers: |r|>=0.5 → 0.15, |r|>=0.3 → 0.08, below → 0."""
    base_kwargs = dict(evidence="10k_mined: x", concentration_pct=None, last_verified_at=None)
    base = composite_confidence_score(**base_kwargs)
    high = composite_confidence_score(**base_kwargs, pair_correlation=0.55)
    medium = composite_confidence_score(**base_kwargs, pair_correlation=0.35)
    low = composite_confidence_score(**base_kwargs, pair_correlation=0.20)
    assert abs(high - base - 0.15) < 0.001
    assert abs(medium - base - 0.08) < 0.001
    assert low == base


def test_full_stack_all_channels_can_reach_one():
    """Hand-seed + 30%+ disclosed + recent + 4 ETFs + r>=0.5 should hit cap."""
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    recent = (now - timedelta(days=10)).isoformat()
    s = composite_confidence_score(
        evidence="seed:hand | x",
        concentration_pct=40,
        last_verified_at=recent,
        etf_co_holding_count=4,
        pair_correlation=0.6,
        now=now,
    )
    # 0.50 + 0.40 + 0.10 + 0.15 + 0.15 = 1.30 → clamped to 1.0
    assert s == 1.0


def test_recompute_for_all_uses_etf_holdings_when_provided():
    """If etf_holdings is passed, edges whose endpoints co-appear get bumped."""
    from src.data.universe_loader import load_tier_a
    from src.data.relations_seed_loader import load_spine
    from src.graph.composite_confidence import recompute_for_all

    init_db()
    load_tier_a()
    load_spine()
    conn = get_connection()
    try:
        # Synthetic ETF basket: NVDA + TSM held together in 2 funds → +0.08
        etfs = {
            "etf_a": {"NVDA", "TSM", "MSFT"},
            "etf_b": {"NVDA", "TSM"},
        }
        recompute_for_all(conn, etf_holdings=etfs)
        row = conn.execute(
            "SELECT composite_confidence FROM stock_relations "
            "WHERE from_symbol='NVDA' AND to_symbol='TSM' AND relation_type='supplier'"
        ).fetchone()
        # hand_seed 0.50 + 2 ETFs (0.08) = 0.58
        assert row is not None
        assert abs(row["composite_confidence"] - 0.58) < 0.001
    finally:
        conn.close()


def test_recompute_for_all_uses_correlation_fn_when_provided():
    """If correlation_fn is passed, edges with |r|>=0.30 get bumped."""
    from src.data.universe_loader import load_tier_a
    from src.data.relations_seed_loader import load_spine
    from src.graph.composite_confidence import recompute_for_all

    init_db()
    load_tier_a()
    load_spine()
    conn = get_connection()
    try:
        # Synthetic correlation: NVDA↔TSM strongly correlated
        def corr_fn(a, b):
            if {a, b} == {"NVDA", "TSM"}:
                return 0.80
            return None

        recompute_for_all(conn, correlation_fn=corr_fn)
        row = conn.execute(
            "SELECT composite_confidence FROM stock_relations "
            "WHERE from_symbol='NVDA' AND to_symbol='TSM' AND relation_type='supplier'"
        ).fetchone()
        # hand_seed 0.50 + corr 0.15 = 0.65
        assert row is not None
        assert abs(row["composite_confidence"] - 0.65) < 0.001
    finally:
        conn.close()


def test_correlation_fn_exceptions_are_swallowed():
    """A flaky correlation fetcher must not crash the backfill."""
    from src.data.universe_loader import load_tier_a
    from src.data.relations_seed_loader import load_spine
    from src.graph.composite_confidence import recompute_for_all

    init_db()
    load_tier_a()
    load_spine()
    conn = get_connection()
    try:
        def angry_corr_fn(a, b):
            raise RuntimeError("simulated network failure")
        out = recompute_for_all(conn, correlation_fn=angry_corr_fn)
        assert out["updated"] >= 1
        # Hand-seeded row still scored — just with no correlation contribution
        row = conn.execute(
            "SELECT composite_confidence FROM stock_relations "
            "WHERE from_symbol='NVDA' AND to_symbol='TSM' AND relation_type='supplier'"
        ).fetchone()
        assert row["composite_confidence"] == 0.5
    finally:
        conn.close()


# ── news co-mention channel ─────────────────────────────────────


def test_count_news_co_mentions_finds_ticker_in_title():
    articles = [
        {"title": "Apple results lift sentiment; MSFT also strong", "content_snippet": ""},
        {"title": "Tech rally", "content_snippet": "AAPL up but TSM held back."},
        {"title": "Unrelated story", "content_snippet": "Banking news."},
    ]
    # AAPL articles mentioning TSM
    assert count_news_co_mentions("AAPL", "TSM", articles_for_target=articles) == 1


def test_count_news_co_mentions_uses_aliases():
    """If the article uses the company name instead of the ticker, aliases catch it."""
    articles = [
        {"title": "Microsoft signs deal with Apple", "content_snippet": ""},
    ]
    n = count_news_co_mentions(
        "AAPL", "MSFT",
        articles_for_target=articles,
        other_aliases=["Microsoft"],
    )
    assert n == 1


def test_count_news_co_mentions_empty_articles_returns_zero():
    assert count_news_co_mentions("AAPL", "MSFT", articles_for_target=[]) == 0


def test_news_channel_score_tiers():
    """3 tiers: 6+ → 0.10; 3-5 → 0.06; 1-2 → 0.03; 0 → 0."""
    base_kwargs = dict(evidence="10k_mined: x", concentration_pct=None, last_verified_at=None)
    base = composite_confidence_score(**base_kwargs)
    s1 = composite_confidence_score(**base_kwargs, news_co_mention_count=1)
    s4 = composite_confidence_score(**base_kwargs, news_co_mention_count=4)
    s10 = composite_confidence_score(**base_kwargs, news_co_mention_count=10)
    assert abs(s1 - base - 0.03) < 0.001
    assert abs(s4 - base - 0.06) < 0.001
    assert abs(s10 - base - 0.10) < 0.001


def test_recompute_for_all_uses_news_co_mention_fn():
    """If news_co_mention_fn returns a count, that channel contributes."""
    from src.data.universe_loader import load_tier_a
    from src.data.relations_seed_loader import load_spine
    from src.graph.composite_confidence import recompute_for_all

    init_db()
    load_tier_a()
    load_spine()
    conn = get_connection()
    try:
        def news_fn(a, b):
            if {a, b} == {"NVDA", "TSM"}:
                return 7   # → high-tier 0.10 contribution
            return 0
        recompute_for_all(conn, news_co_mention_fn=news_fn)
        row = conn.execute(
            "SELECT composite_confidence FROM stock_relations "
            "WHERE from_symbol='NVDA' AND to_symbol='TSM' AND relation_type='supplier'"
        ).fetchone()
        # hand_seed 0.50 + news 0.10 = 0.60
        assert row is not None
        assert abs(row["composite_confidence"] - 0.60) < 0.001
    finally:
        conn.close()


def test_news_co_mention_fn_exceptions_are_swallowed():
    from src.data.universe_loader import load_tier_a
    from src.data.relations_seed_loader import load_spine
    from src.graph.composite_confidence import recompute_for_all

    init_db()
    load_tier_a()
    load_spine()
    conn = get_connection()
    try:
        def angry(a, b):
            raise RuntimeError("simulated tavily 429")
        out = recompute_for_all(conn, news_co_mention_fn=angry)
        assert out["updated"] >= 1
        row = conn.execute(
            "SELECT composite_confidence FROM stock_relations "
            "WHERE from_symbol='NVDA' AND to_symbol='TSM' AND relation_type='supplier'"
        ).fetchone()
        # No channels lit beyond hand_seed → 0.5
        assert row["composite_confidence"] == 0.5
    finally:
        conn.close()
