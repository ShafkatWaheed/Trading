"""Tests for src/news/aggregate.py — diminishing-returns merge, polarity, co-occurrence."""

from __future__ import annotations

import math

import pytest

from src.news.aggregate import (
    AggregateResult,
    CoOccurrenceRule,
    IndustryImpact,
    KeywordImpactRow,
    _diminishing_sum,
    _merge_directional,
    aggregate,
)
from src.news.tokenize import TokenMatch


# ── helpers ───────────────────────────────────────────────────────


def _kw_match(text: str, *, negated: bool = False, span: tuple[int, int] = (0, 1)) -> TokenMatch:
    return TokenMatch(text=text, kind="keyword", token_span=span, negated=negated)


def _country(text: str, *, span: tuple[int, int] = (0, 1)) -> TokenMatch:
    return TokenMatch(text=text, kind="country", token_span=span, negated=False)


# ── diminishing-returns math ─────────────────────────────────────


def test_diminishing_sum_caps_at_one():
    # Many strong contributions cap at 1.0 (asymptote).
    assert _diminishing_sum([0.9, 0.9, 0.9, 0.9]) < 1.0
    assert _diminishing_sum([0.9, 0.9, 0.9, 0.9]) > 0.99


def test_diminishing_sum_two_independent_contributions():
    # Two 0.5 weights: 1 - (1 - 0.5)(1 - 0.5) = 1 - 0.25 = 0.75
    assert math.isclose(_diminishing_sum([0.5, 0.5]), 0.75)


def test_diminishing_sum_empty_is_zero():
    assert _diminishing_sum([]) == 0.0


def test_diminishing_sum_single_value_passes_through():
    assert math.isclose(_diminishing_sum([0.4]), 0.4)


def test_merge_directional_pure_positive():
    pol, strength = _merge_directional([(1.0, 0.5), (1.0, 0.5)])
    assert pol == 1.0
    assert math.isclose(strength, 0.75)


def test_merge_directional_pure_negative():
    pol, strength = _merge_directional([(-1.0, 0.5), (-1.0, 0.5)])
    assert pol == -1.0
    assert math.isclose(strength, 0.75)


def test_merge_directional_conflicting_pulls_dominant():
    # +0.9 vs -0.3 → net positive
    pol, strength = _merge_directional([(1.0, 0.9), (-1.0, 0.3)])
    assert pol == 1.0
    assert strength >= 0.7


def test_merge_directional_returns_zero_when_no_input():
    pol, strength = _merge_directional([])
    assert pol == 0.0
    assert strength == 0.0


# ── single-keyword aggregation ───────────────────────────────────


def test_single_keyword_one_industry_match():
    matches = [_kw_match("ai")]
    rows = [KeywordImpactRow("ai", "Semiconductors", None, polarity=0.95, weight=0.9)]
    result = aggregate(matches, rows)
    assert len(result.industries) == 1
    impact = result.industries[0]
    assert impact.industry_code == "Semiconductors"
    assert impact.polarity == 1.0
    assert math.isclose(impact.strength, 0.95 * 0.9, abs_tol=0.001)


def test_keyword_with_target_stock_creates_stock_impact():
    matches = [_kw_match("fda approves")]
    rows = [KeywordImpactRow("fda approves", None, "LLY", polarity=1.0, weight=0.9)]
    result = aggregate(matches, rows)
    assert len(result.stocks) == 1
    assert result.stocks[0].symbol == "LLY"
    assert result.stocks[0].polarity == 1.0


def test_negated_keyword_flips_polarity():
    matches = [_kw_match("tariff", negated=True)]
    rows = [KeywordImpactRow("tariff", "Steel", None, polarity=0.7, weight=0.7)]
    result = aggregate(matches, rows)
    assert result.industries[0].polarity == -1.0
    assert "tariff" in result.negated_keywords


# ── multiple-keyword aggregation ─────────────────────────────────


def test_two_keywords_same_industry_compose():
    matches = [_kw_match("oil"), _kw_match("crude")]
    rows = [
        KeywordImpactRow("oil", "Oil & Gas E&P", None, polarity=1.0, weight=0.8),
        KeywordImpactRow("crude", "Oil & Gas E&P", None, polarity=1.0, weight=0.7),
    ]
    result = aggregate(matches, rows)
    assert len(result.industries) == 1
    impact = result.industries[0]
    # Composed: 1 - (1-0.8)(1-0.7) = 1 - 0.06 = 0.94
    assert math.isclose(impact.strength, 0.94, abs_tol=0.01)


def test_opposing_keywords_polarity_resolves_to_dominant():
    matches = [_kw_match("oil"), _kw_match("airlines")]
    rows = [
        KeywordImpactRow("oil", "Oil & Gas E&P", None, polarity=1.0, weight=0.8),
        KeywordImpactRow("airlines", "Oil & Gas E&P", None, polarity=-1.0, weight=0.3),
    ]
    result = aggregate(matches, rows)
    assert result.industries[0].polarity == 1.0  # bullish dominates


def test_keyword_no_matching_rows_produces_no_impact():
    matches = [_kw_match("unknown_keyword")]
    rows = [KeywordImpactRow("ai", "Semiconductors", None, polarity=1.0, weight=0.9)]
    result = aggregate(matches, rows)
    assert result.industries == []
    assert result.stocks == []


# ── co-occurrence boosts ─────────────────────────────────────────


def test_tariff_china_co_occurrence_boosts_steel():
    matches = [_kw_match("tariff"), _country("china")]
    rows = [
        KeywordImpactRow("tariff", "Steel", None, polarity=1.0, weight=0.7),
    ]
    result = aggregate(matches, rows)
    steel = next(i for i in result.industries if i.industry_code == "Steel")
    # Composed: 1 - (1 - 0.7)(1 - 0.10 boost) = 1 - 0.27 = 0.73
    assert steel.strength > 0.7  # boost applied


def test_co_occurrence_does_not_fire_when_only_one_keyword_present():
    """Tariff alone (no China) should NOT trigger the co-occurrence boost."""
    matches = [_kw_match("tariff")]
    rows = [KeywordImpactRow("tariff", "Steel", None, polarity=1.0, weight=0.7)]
    result = aggregate(matches, rows)
    steel = next(i for i in result.industries if i.industry_code == "Steel")
    # Strength should equal the base contribution alone (~0.7), not boosted.
    assert steel.strength <= 0.71


# ── result ergonomics ────────────────────────────────────────────


def test_industries_sorted_by_strength_desc():
    matches = [_kw_match("ai"), _kw_match("oil")]
    rows = [
        KeywordImpactRow("ai", "Semiconductors", None, polarity=1.0, weight=0.9),
        KeywordImpactRow("oil", "Oil & Gas E&P", None, polarity=1.0, weight=0.5),
    ]
    result = aggregate(matches, rows)
    assert result.industries[0].industry_code == "Semiconductors"
    assert result.industries[1].industry_code == "Oil & Gas E&P"


def test_contributing_keywords_recorded():
    matches = [_kw_match("oil"), _kw_match("crude")]
    rows = [
        KeywordImpactRow("oil", "Oil & Gas E&P", None, polarity=1.0, weight=0.8),
        KeywordImpactRow("crude", "Oil & Gas E&P", None, polarity=1.0, weight=0.7),
    ]
    result = aggregate(matches, rows)
    assert set(result.industries[0].contributing_keywords) == {"oil", "crude"}


def test_matched_keywords_and_countries_returned():
    matches = [_kw_match("oil"), _country("saudi arabia"), _kw_match("missile")]
    rows = []
    result = aggregate(matches, rows)
    assert "oil" in result.matched_keywords
    assert "missile" in result.matched_keywords
    assert "saudi arabia" in result.matched_countries


def test_zero_strength_industry_filtered_out():
    """If the diminishing-sum produces 0, the industry should not be in output."""
    matches = [_kw_match("ai")]
    rows = [KeywordImpactRow("ai", "Semiconductors", None, polarity=1.0, weight=0.0)]
    result = aggregate(matches, rows)
    assert result.industries == []
