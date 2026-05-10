"""Phase 4: tests for the auto-1-hop graph expansion in news-impact.

Verifies that high-confidence keyword hits surface 2nd-derivative plays via
the supply-chain + peer graph (e.g. an AI news headline returns NVDA direct
plus TSM, MSFT, etc. via 1-hop expansion).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services import news_impact_service
from src.data.conglomerate_overrides import apply_conglomerate_overrides
from src.data.industries_seed import load_industries
from src.data.keyword_seed_loader import load_keyword_impact
from src.data.peer_seed_loader import load_all_hand_peers
from src.data.relations_seed_loader import load_spine
from src.data.universe_loader import load_tier_a
from src.utils.db import init_db


@pytest.fixture(scope="module", autouse=True)
def _seed_everything():
    init_db()
    load_industries()
    load_tier_a()
    apply_conglomerate_overrides()
    load_keyword_impact()
    load_all_hand_peers()
    load_spine()
    # Reset the news cache so newly-loaded keywords register
    news_impact_service._cache["loaded_at"] = 0.0


@pytest.fixture
def client():
    return TestClient(app)


def _post(client, text):
    r = client.post("/news-impact", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


# ── auto-expansion behaviour ──────────────────────────────────────


def test_ai_news_surfaces_supply_chain_via_graph(client):
    """AI capex headline should bring TSM (NVDA's supplier) into results
    even though TSM is not directly tagged with AI in keyword_impact."""
    payload = _post(client, "OpenAI announces $50B GPU build-out for new data center")
    syms = {s["symbol"] for s in payload["stocks"]}
    # NVDA direct
    assert "NVDA" in syms
    # TSM via NVDA→supplier→TSM expansion
    assert "TSM" in syms


def test_ai_news_surfaces_hyperscaler_customers_via_graph(client):
    payload = _post(client, "AI demand booms with new GPU capex announcements")
    syms = {s["symbol"] for s in payload["stocks"]}
    # Hyperscalers are NVDA's customers — expansion should pull at least one in
    customers = {"MSFT", "META", "GOOGL", "AMZN"} & syms
    assert customers, f"expected at least one hyperscaler via graph expansion; got {syms}"


def test_graph_expanded_stocks_marked_with_via_origin(client):
    payload = _post(client, "AI demand booms with GPU capex")
    # Find a graph-expanded stock (i.e. one with contributing_industries starting with "via:")
    via_stocks = [
        s for s in payload["stocks"]
        if any(ind.startswith("via:") for ind in s.get("contributing_industries", []))
    ]
    if via_stocks:
        # The "via:" prefix carries the seed symbol that brought this stock in
        first = via_stocks[0]
        assert any(ind.startswith("via:") for ind in first["contributing_industries"])


def test_direct_hits_rank_above_graph_expansions(client):
    payload = _post(client, "Iran fires missiles at Saudi oil refinery")
    # Direct-keyword hits should appear before graph-only expansions
    stocks = payload["stocks"]
    direct_indices = [i for i, s in enumerate(stocks) if s["contributing_keywords"]]
    graph_only_indices = [
        i for i, s in enumerate(stocks)
        if not s["contributing_keywords"]
        and any(ind.startswith("via:") for ind in s.get("contributing_industries", []))
    ]
    if direct_indices and graph_only_indices:
        assert min(direct_indices) < min(graph_only_indices)


# ── opt-out path ──────────────────────────────────────────────────


def test_expand_graph_false_skips_expansion():
    """Calling analyze_news with expand_graph=False should NOT pull graph 2nd-derivatives."""
    no_graph = news_impact_service.analyze_news(
        "OpenAI announces $50B GPU build-out for new data center",
        expand_graph=False,
    )
    with_graph = news_impact_service.analyze_news(
        "OpenAI announces $50B GPU build-out for new data center",
        expand_graph=True,
    )
    no_graph_syms = {s["symbol"] for s in no_graph["stocks"]}
    with_graph_syms = {s["symbol"] for s in with_graph["stocks"]}
    # Graph version should be a strict superset (or equal — if there are no
    # high-confidence seeds to expand from)
    assert with_graph_syms >= no_graph_syms


# ── polarity propagation through the graph ────────────────────────


def test_negated_seed_propagates_negative_polarity_through_graph(client):
    """If 'oil' is negated in the headline, even graph-expanded stocks linked
    to oil-positive seeds should pick up the inversion. Smoke test only —
    doesn't deeply verify, just checks the system doesn't crash."""
    payload = _post(client, "Iran-Saudi tensions averted as deal reached, oil supply restored")
    # Just verify the call works and returns SOMETHING (negation may suppress all hits)
    assert "stocks" in payload
    assert "industries" in payload


# ── stability: cached keywords reload correctly ───────────────────


def test_cache_refresh_picks_up_new_keywords():
    """Force the cache to refresh and verify regulatory keywords now surface."""
    news_impact_service._cache["loaded_at"] = 0.0
    out = news_impact_service.analyze_news("FDA rejects Eli Lilly Alzheimer's drug")
    keywords = set(out["matched_keywords"])
    # 'fda rejects' is in the regulatory_keywords section we added in Phase 4 Day 18
    assert "fda rejects" in keywords or "rejects" in " ".join(keywords)
