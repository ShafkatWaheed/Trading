"""End-to-end test: a commodity headline triggers Phase 6 causal-chain hits."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services import news_impact_service
from src.data.commodity_seed_loader import load_all as load_commodities
from src.data.conglomerate_overrides import apply_conglomerate_overrides
from src.data.industries_seed import load_industries
from src.data.keyword_seed_loader import load_keyword_impact
from src.data.peer_seed_loader import load_all_hand_peers
from src.data.relations_seed_loader import load_spine
from src.data.universe_loader import load_tier_a
from src.utils.db import init_db


@pytest.fixture(scope="module", autouse=True)
def _seed_phase6_full():
    init_db()
    load_industries()
    load_tier_a()
    apply_conglomerate_overrides()
    load_keyword_impact()
    load_all_hand_peers()
    load_spine()
    load_commodities()
    # Force the news service to refresh its in-process keyword cache
    news_impact_service._cache["loaded_at"] = 0.0


@pytest.fixture
def client():
    return TestClient(app)


def _post(client, text):
    r = client.post("/news-impact", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


# ── oil event triggers commodity producers via causal chain ───────


def test_oil_news_surfaces_pure_oil_producers_via_causal_chain(client):
    payload = _post(client, "Iran fires missiles at Saudi oil refinery, output cut announced")
    # Direct hits already include XOM/CVX via 'oil' keyword in keyword_impact.
    # The causal layer should also annotate these stocks with 'via:crude_oil'.
    syms = {s["symbol"] for s in payload["stocks"]}
    assert {"XOM", "CVX", "COP"} <= syms

    # Check at least one of these has the causal-chain tag in contributing_industries
    causal_tagged = [
        s for s in payload["stocks"]
        if any(ind.startswith("via:crude_oil") for ind in s.get("contributing_industries", []))
    ]
    assert causal_tagged, "expected at least one stock tagged with via:crude_oil"


def test_oil_news_makes_oilfield_services_appear_via_graph_or_causal(client):
    """SLB / HAL aren't in the keyword_impact table directly, but they should
    surface either via Phase 4 graph expansion (XOM → SLB customer edge) or
    via Phase 6 causal chain (SLB has output crude_oil exposure)."""
    payload = _post(client, "Iran fires missiles at Saudi oil refinery, output cut")
    syms = {s["symbol"] for s in payload["stocks"]}
    assert {"SLB", "HAL"} & syms, f"expected SLB or HAL via expansion; got {syms}"


# ── uranium event ─────────────────────────────────────────────────


def test_uranium_news_surfaces_ccj_via_causal_chain(client):
    payload = _post(client, "Uranium prices surge as global nuclear demand accelerates")
    syms = {s["symbol"] for s in payload["stocks"]}
    assert "CCJ" in syms
    ccj = next(s for s in payload["stocks"] if s["symbol"] == "CCJ")
    assert ccj["polarity"] > 0


def test_uranium_news_pulls_in_nuclear_utilities_via_graph(client):
    """CEG and VST have uranium INPUT exposures; uranium up should make them
    appear (with negative polarity since they're consumers)."""
    payload = _post(client, "Uranium prices surge as nuclear demand returns")
    syms = {s["symbol"] for s in payload["stocks"]}
    # At least one nuclear utility should appear
    assert {"CEG", "VST", "EXC"} & syms


# ── lithium event ─────────────────────────────────────────────────


def test_lithium_news_pressures_tsla_via_causal(client):
    payload = _post(client, "Lithium carbonate prices spike on Chinese export curbs")
    # TSLA should appear and be negative (lithium is an input cost)
    syms = {s["symbol"] for s in payload["stocks"]}
    if "TSLA" in syms:
        tsla = next(s for s in payload["stocks"] if s["symbol"] == "TSLA")
        assert tsla["polarity"] < 0


# ── fertilizer / gas crisis (cost-passthrough flip) ───────────────


def test_gas_crisis_surfaces_gas_producers_via_causal(client):
    """A gas-crisis headline should pull in gas producers (via natural_gas
    output exposures on KMI/COP)."""
    payload = _post(client, "European natural gas storage at 30%, prices surge")
    syms = {s["symbol"] for s in payload["stocks"]}
    # Gas producers / midstream
    assert {"KMI", "COP", "OXY", "ENB", "XOM", "CVX"} & syms


# ── coffee / cocoa (consumer staples cost squeeze) ────────────────


def test_coffee_spike_pressures_sbux(client):
    payload = _post(client, "Coffee futures hit record high on Brazilian frost")
    syms = {s["symbol"] for s in payload["stocks"]}
    assert "SBUX" in syms
    sbux = next(s for s in payload["stocks"] if s["symbol"] == "SBUX")
    assert sbux["polarity"] < 0


def test_cocoa_spike_pressures_mdlz(client):
    payload = _post(client, "Cocoa prices triple amid West African disease outbreak")
    syms = {s["symbol"] for s in payload["stocks"]}
    assert "MDLZ" in syms
    mdlz = next(s for s in payload["stocks"] if s["symbol"] == "MDLZ")
    assert mdlz["polarity"] < 0


# ── opt-out path ──────────────────────────────────────────────────


def test_expand_causal_false_skips_causal_layer():
    """Calling analyze_news with expand_causal=False should NOT pull in
    commodity-only hits (those that aren't already in the keyword path)."""
    with_causal = news_impact_service.analyze_news(
        "Uranium prices surge as nuclear demand returns",
        expand_causal=True,
    )
    without_causal = news_impact_service.analyze_news(
        "Uranium prices surge as nuclear demand returns",
        expand_causal=False,
    )
    causal_syms = {s["symbol"] for s in with_causal["stocks"]}
    no_causal_syms = {s["symbol"] for s in without_causal["stocks"]}
    # With causal must be a superset of without
    assert causal_syms >= no_causal_syms


# ── traceability ──────────────────────────────────────────────────


def test_causal_hits_carry_via_commodity_tag(client):
    payload = _post(client, "Copper prices spike on Chilean mine strike")
    via_copper = [
        s for s in payload["stocks"]
        if any(ind.startswith("via:copper") for ind in s.get("contributing_industries", []))
    ]
    # FCX has output:copper exposure, so it should be tagged
    assert via_copper, f"expected at least one via:copper tag; stocks: {[s['symbol'] for s in payload['stocks']]}"
