"""Tests for the brief's 3-bucket classifier (_classify3).

Pin the behavior changes from the misclassification fix:
  1. PROMISING is checked BEFORE hype — a real grower never gets hype-tagged
  2. PEG-fallback hype rule is GONE — bubble cache miss doesn't default to hype
  3. Sector-relative HYPE threshold — Tech tolerates higher bubble scores
  4. bucket_reason explains which rule fired
  5. Borderline promising-but-rich annotation
"""
from __future__ import annotations

from api.services.brief_service import _classify3, _hype_threshold


# ── Fixtures (plain dicts mirror fund shape) ─────────────────────────


def _f(**kwargs) -> dict:
    """Convenience: build a minimal fundamentals dict."""
    defaults = {
        "revenue_growth": None,
        "eps_growth": None,
        "profit_margin": None,
        "net_income": None,
        "peg_ratio": None,
        "market_cap": None,
        "sector": None,
    }
    defaults.update(kwargs)
    return defaults


# ── Rule order: PROMISING before HYPE ────────────────────────────────


def test_high_growth_with_high_bubble_stays_promising():
    """The whole point of the fix: NVDA-shaped names (rev_growth=50% + bubble=82
    in Tech, above the 75 threshold) should be 'promising' with a
    'priced rich' annotation — NOT 'hype'."""
    fund = _f(revenue_growth=0.50, profit_margin=0.20, sector="Technology")
    bucket, reason = _classify3(fund, bubble_score=82.0, sector="Technology")
    assert bucket == "promising"
    assert "rev_growth=50%" in reason
    # And the "priced rich" annotation is woven into the reason when
    # bubble crosses the sector hype threshold (75 for Tech).
    assert "priced rich" in reason


def test_eps_grower_with_high_bubble_stays_promising():
    fund = _f(eps_growth=0.40, profit_margin=0.15, sector="Healthcare")
    bucket, reason = _classify3(fund, bubble_score=75.0, sector="Healthcare")
    assert bucket == "promising"
    assert "eps_growth=40%" in reason


# ── Sector-relative HYPE threshold ───────────────────────────────────


def test_tech_threshold_higher_than_energy():
    assert _hype_threshold("Technology") > _hype_threshold("Energy")
    assert _hype_threshold("Communication Services") == _hype_threshold("Technology")


def test_unknown_sector_uses_default_threshold():
    assert _hype_threshold(None) == 65
    assert _hype_threshold("MadeUpSector") == 65


def test_hype_only_at_or_above_sector_threshold():
    fund = _f(sector="Energy")    # low-growth Energy name
    # Energy threshold is 50 — 49 is NOT hype, 55 IS hype.
    bucket, _ = _classify3(fund, bubble_score=49.0, sector="Energy")
    assert bucket != "hype"
    bucket, reason = _classify3(fund, bubble_score=55.0, sector="Energy")
    assert bucket == "hype"
    assert "55" in reason
    assert "50" in reason


def test_tech_stock_at_energy_threshold_is_not_hype():
    """A Tech stock with bubble=65 is NOT hype (Tech threshold is 75)."""
    fund = _f(sector="Technology")
    bucket, _ = _classify3(fund, bubble_score=65.0, sector="Technology")
    assert bucket != "hype"
    # But at 76 it crosses Tech threshold
    bucket, _ = _classify3(fund, bubble_score=76.0, sector="Technology")
    assert bucket == "hype"


# ── PEG-fallback HYPE rule was DROPPED ──────────────────────────────


def test_high_peg_big_cap_without_bubble_no_longer_flagged_hype():
    """OLD behavior: bubble_score=None + PEG>3 + mcap>$50B → 'hype'.
    NEW behavior: that path is gone. Stock falls through to None bucket
    (and gets dropped from picks instead of misclassified)."""
    fund = _f(peg_ratio=3.5, market_cap=200e9, sector="Technology")
    bucket, reason = _classify3(fund, bubble_score=None, sector="Technology")
    assert bucket != "hype"


# ── STABLE rule unchanged ───────────────────────────────────────────


def test_stable_modest_grower_with_margin():
    fund = _f(revenue_growth=0.10, profit_margin=0.12, net_income=1e9)
    bucket, reason = _classify3(fund, bubble_score=40.0)
    assert bucket == "stable"
    assert "5-30%" in reason


def test_negative_net_income_blocks_stable():
    fund = _f(revenue_growth=0.10, profit_margin=0.12, net_income=-1e9)
    bucket, _ = _classify3(fund, bubble_score=40.0)
    assert bucket != "stable"


# ── None when no rule fires ─────────────────────────────────────────


def test_no_signal_returns_none_bucket_and_none_reason():
    """A boring stock with no fundamentals signal AND no bubble signal
    gets dropped — the bucket_reason being None is what _classify_all
    uses to filter it out."""
    fund = _f(revenue_growth=0.02, profit_margin=0.02)
    bucket, reason = _classify3(fund, bubble_score=40.0)
    assert bucket is None
    assert reason is None


# ── bucket_reason quality ────────────────────────────────────────────


def test_bucket_reason_quantifies_growth_for_promising():
    fund = _f(revenue_growth=0.42)
    bucket, reason = _classify3(fund, bubble_score=None)
    assert bucket == "promising"
    assert "42%" in reason
    assert "25%" in reason


def test_bucket_reason_names_threshold_for_hype():
    fund = _f(sector="Industrials")
    bucket, reason = _classify3(fund, bubble_score=65.0, sector="Industrials")
    assert bucket == "hype"
    assert "60" in reason     # Industrials threshold = 60
    assert "Industrials" in reason


def test_bucket_reason_annotates_priced_rich_for_grower_with_high_bubble():
    fund = _f(revenue_growth=0.50, sector="Technology")
    bucket, reason = _classify3(fund, bubble_score=78.0, sector="Technology")
    assert bucket == "promising"
    assert "priced rich" in reason
    # The bubble number is exposed so users can see it
    assert "78" in reason
