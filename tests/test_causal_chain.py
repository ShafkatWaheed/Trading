"""Tests for src/graph/causal_chain.py — commodity-driven causal traversal."""

from __future__ import annotations

import pytest

from src.data.commodity_seed_loader import load_all as load_all_commodities
from src.data.peer_seed_loader import load_all_hand_peers
from src.data.relations_seed_loader import load_spine
from src.data.universe_loader import load_tier_a
from src.graph.causal_chain import (
    CausalHit,
    rank_hits,
    stocks_exposed_to,
    trace_from_commodities,
    trace_from_commodity,
)
from src.utils.db import init_db


@pytest.fixture(scope="module", autouse=True)
def _seed_phase6():
    init_db()
    load_tier_a()
    load_all_commodities()
    load_all_hand_peers()
    load_spine()


# ── direct exposures ─────────────────────────────────────────────


def test_stocks_exposed_to_oil_includes_majors():
    out = stocks_exposed_to("crude_oil")
    syms = {ce.symbol for ce in out}
    assert {"XOM", "CVX", "COP", "OXY", "EOG"} <= syms


def test_stocks_exposed_to_unknown_is_empty():
    out = stocks_exposed_to("totally_made_up_commodity")
    assert out == []


def test_oil_exposures_include_both_outputs_and_refiner_inputs():
    out = stocks_exposed_to("crude_oil")
    roles = {ce.role for ce in out}
    assert "output" in roles      # majors
    assert "input" in roles       # refiners


# ── trace_from_commodity: oil up ─────────────────────────────────


def test_oil_up_makes_producers_bullish():
    hits = trace_from_commodity("crude_oil", direction="up", expand_hops=0)
    xom = hits.get("XOM")
    assert xom is not None
    assert xom.polarity > 0    # producer benefits when oil goes up


def test_oil_up_chains_have_human_readable_step():
    hits = trace_from_commodity("crude_oil", direction="up", expand_hops=0)
    xom = hits["XOM"]
    assert len(xom.chain) >= 1
    # Chain text should include the commodity and the role
    assert "crude_oil" in xom.chain[0]
    assert "↑" in xom.chain[0]


def test_oil_down_flips_producer_polarity():
    hits = trace_from_commodity("crude_oil", direction="down", expand_hops=0)
    xom = hits["XOM"]
    assert xom.polarity < 0


# ── cost passthrough flip: gas → fertilizer ──────────────────────
# NOTE: We don't have CF/MOS/NTR in the Tier A universe, so we exercise the
# flip mechanism using utility refiners (KMI for gas) + crude_oil refiners.


def test_oil_up_makes_refiners_input_squeeze():
    """Refiners (VLO/MPC/PSX) hold input crude_oil at polarity=-1.
    On oil-up, the input-side hit should give refiners a negative direct hit,
    BUT the cost-passthrough flip via output gasoline/diesel should produce
    a stronger positive output story for the same stock."""
    hits = trace_from_commodity("crude_oil", direction="up", expand_hops=0)
    vlo = hits.get("VLO")
    assert vlo is not None
    # The flip mechanism prefers the output story when it dominates
    # (output gasoline polarity=+1 × elasticity=0.6 vs input crude=-1 × 0.55)
    # Expected: output story wins → polarity > 0
    assert vlo.polarity > 0
    # Chain mentions the supply-tightness flip
    assert any("squeeze" in step.lower() or "supply tightens" in step.lower()
               for step in vlo.chain)


# ── 1-hop graph expansion ────────────────────────────────────────


def test_expand_hops_pulls_in_supply_chain():
    """Direct hit XOM → 1-hop expansion should reach SLB (XOM is one of SLB's
    customers in the spine)."""
    hits = trace_from_commodity("crude_oil", direction="up", expand_hops=1)
    # Some stock NOT in direct exposures should appear via expansion.
    direct = {ce.symbol for ce in stocks_exposed_to("crude_oil")}
    expanded_only = {sym for sym in hits if sym not in direct}
    # Just verify we got some non-direct hits; specific names depend on spine
    assert expanded_only, f"expected graph expansion to add at least one hit; direct={len(direct)}, total={len(hits)}"


def test_zero_hops_returns_only_direct_exposures():
    hits = trace_from_commodity("crude_oil", direction="up", expand_hops=0)
    direct_syms = {ce.symbol for ce in stocks_exposed_to("crude_oil")}
    assert set(hits.keys()) == direct_syms


# ── multi-commodity confluence ────────────────────────────────────


def test_trace_from_multiple_commodities_merges_hits():
    """Oil up + gas up: XOM (output crude + output gas) should appear once
    with stronger magnitude than either alone."""
    moves = [("crude_oil", "up"), ("natural_gas", "up")]
    merged = trace_from_commodities(moves, expand_hops=0)
    assert "XOM" in merged
    xom = merged["XOM"]
    # Diminishing-returns sum of two outputs at elasticities 0.85 + 0.40
    # Expected mag ≈ 1 - (1-0.85)(1-0.40) = 0.91
    assert xom.magnitude > 0.85


def test_oil_up_gold_up_does_not_double_count_producers():
    """XOM has no gold exposure — gold up should not add a chain step for XOM."""
    moves = [("crude_oil", "up"), ("gold", "up")]
    merged = trace_from_commodities(moves, expand_hops=0)
    xom_chain = " ".join(merged["XOM"].chain)
    assert "gold" not in xom_chain.lower()


# ── ranking ──────────────────────────────────────────────────────


def test_rank_hits_orders_by_score_desc():
    hits = {
        "WEAK":   CausalHit("WEAK",   polarity=+0.5, magnitude=0.2),
        "STRONG": CausalHit("STRONG", polarity=+1.0, magnitude=0.9),
        "MIDDLE": CausalHit("MIDDLE", polarity=-1.0, magnitude=0.5),
    }
    out = rank_hits(hits)
    syms = [h.symbol for h in out]
    assert syms[0] == "STRONG"
    # |polarity|*magnitude: STRONG=0.9, MIDDLE=0.5, WEAK=0.10
    assert syms == ["STRONG", "MIDDLE", "WEAK"]


# ── miner outputs ────────────────────────────────────────────────


def test_uranium_up_makes_ccj_bullish():
    hits = trace_from_commodity("uranium", direction="up", expand_hops=0)
    ccj = hits.get("CCJ")
    assert ccj is not None
    assert ccj.polarity > 0
    assert ccj.magnitude >= 0.7


def test_copper_up_makes_fcx_bullish():
    hits = trace_from_commodity("copper", direction="up", expand_hops=0)
    fcx = hits.get("FCX")
    assert fcx is not None
    assert fcx.polarity > 0


# ── auto / EV inputs ─────────────────────────────────────────────


def test_lithium_up_makes_tsla_negative():
    hits = trace_from_commodity("lithium", direction="up", expand_hops=0)
    tsla = hits.get("TSLA")
    assert tsla is not None
    # TSLA is a lithium consumer (input), so lithium up = negative
    assert tsla.polarity < 0


# ── consumer staples ─────────────────────────────────────────────


def test_cocoa_up_pressures_mdlz():
    hits = trace_from_commodity("cocoa", direction="up", expand_hops=0)
    mdlz = hits.get("MDLZ")
    assert mdlz is not None
    assert mdlz.polarity < 0
    assert mdlz.magnitude >= 0.4


def test_coffee_up_pressures_sbux():
    hits = trace_from_commodity("coffee", direction="up", expand_hops=0)
    sbux = hits.get("SBUX")
    assert sbux is not None
    assert sbux.polarity < 0
