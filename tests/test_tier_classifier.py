"""Tests for the deterministic tier classifier."""

from __future__ import annotations

import pytest

from src.data.tier_classifier import (
    StockClassificationInputs,
    TierThresholds,
    classify_tier,
    classify_universe,
)


# ── Tier A ─────────────────────────────────────────────────────────


def test_mega_cap_in_sp500_with_high_volume_is_A():
    s = StockClassificationInputs(
        symbol="NVDA",
        market_cap=3.5e12,
        avg_dollar_volume=20e9,
        in_sp500=True,
        in_russell1000=True,
        in_qqq=True,
    )
    assert classify_tier(s) == "A"


def test_hand_seeded_overrides_to_A_even_without_market_cap():
    s = StockClassificationInputs(
        symbol="ARM",
        market_cap=None,
        avg_dollar_volume=None,
        hand_seeded_tier_a=True,
    )
    assert classify_tier(s) == "A"


def test_sp500_member_below_market_cap_floor_is_B_not_A():
    s = StockClassificationInputs(
        symbol="SMALL_SP",
        market_cap=10e9,           # below $50B
        avg_dollar_volume=500e6,
        in_sp500=True,
    )
    assert classify_tier(s) == "B"


def test_sp500_member_below_dollar_volume_floor_is_B_not_A():
    s = StockClassificationInputs(
        symbol="LOW_VOL_SP",
        market_cap=100e9,          # plenty of cap
        avg_dollar_volume=100e6,   # below $250M ADV floor
        in_sp500=True,
    )
    assert classify_tier(s) == "B"


# ── Tier B ─────────────────────────────────────────────────────────


def test_russell1000_only_is_B():
    s = StockClassificationInputs(
        symbol="RUSSELL_NAME",
        market_cap=8e9,
        avg_dollar_volume=80e6,
        in_russell1000=True,
    )
    assert classify_tier(s) == "B"


def test_qqq_only_is_B():
    s = StockClassificationInputs(symbol="NDX_NAME", in_qqq=True)
    assert classify_tier(s) == "B"


def test_tsx60_only_is_B():
    s = StockClassificationInputs(symbol="RY.TO", in_tsx60=True)
    assert classify_tier(s) == "B"


# ── Tier C ─────────────────────────────────────────────────────────


def test_russell2000_only_is_C():
    s = StockClassificationInputs(symbol="SMALL_R2K", in_russell2000=True)
    assert classify_tier(s) == "C"


def test_nasdaq_global_market_only_is_C():
    s = StockClassificationInputs(
        symbol="GLOBAL_MARKET_NAME",
        nasdaq_market_tier="Global Market",
    )
    assert classify_tier(s) == "C"


def test_nasdaq_global_select_only_is_C():
    # Global Select is the top NASDAQ tier; if not in any major index, still C.
    s = StockClassificationInputs(
        symbol="GLOBAL_SELECT_NAME",
        nasdaq_market_tier="Global Select",
    )
    assert classify_tier(s) == "C"


def test_tsx_broad_only_is_C():
    s = StockClassificationInputs(symbol="TSX_BROAD_NAME", on_tsx_broad=True)
    assert classify_tier(s) == "C"


# ── Tier D ─────────────────────────────────────────────────────────


def test_nasdaq_capital_market_only_is_D():
    s = StockClassificationInputs(
        symbol="NASDAQ_CAP_NAME",
        nasdaq_market_tier="Capital Market",
    )
    assert classify_tier(s) == "D"


def test_tsxv_only_is_D():
    s = StockClassificationInputs(symbol="TSXV_NAME", on_tsxv=True)
    assert classify_tier(s) == "D"


def test_cse_only_is_D():
    s = StockClassificationInputs(symbol="CSE_NAME", on_cse=True)
    assert classify_tier(s) == "D"


def test_completely_unknown_stock_is_D():
    s = StockClassificationInputs(symbol="UNKNOWN")
    assert classify_tier(s) == "D"


# ── Threshold overrides ────────────────────────────────────────────


def test_lowering_market_cap_threshold_promotes_to_A():
    s = StockClassificationInputs(
        symbol="MID_SP",
        market_cap=20e9,           # below default $50B
        avg_dollar_volume=300e6,
        in_sp500=True,
    )
    assert classify_tier(s) == "B"
    assert classify_tier(s, TierThresholds(a_market_cap_min=10e9)) == "A"


# ── Batch helper ───────────────────────────────────────────────────


def test_classify_universe_returns_per_symbol_tier():
    rows = [
        StockClassificationInputs(symbol="NVDA", market_cap=3e12, avg_dollar_volume=20e9, in_sp500=True),
        StockClassificationInputs(symbol="MIDCAP", in_russell1000=True),
        StockClassificationInputs(symbol="SMALLCAP", in_russell2000=True),
        StockClassificationInputs(symbol="NOTHING"),
    ]
    out = classify_universe(rows)
    assert out == {"NVDA": "A", "MIDCAP": "B", "SMALLCAP": "C", "NOTHING": "D"}
