"""Tests for src.graph.composite_confidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.data.relations_seed_loader import load_spine
from src.data.universe_loader import load_tier_a
from src.graph.composite_confidence import (
    composite_confidence_score,
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
