"""Tests for the Phase 8 graph-relevance scorer + endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from src.data.commodity_seed_loader import load_all as load_commodities_all
from src.data.peer_seed_loader import load_all_hand_peers
from src.data.relations_seed_loader import load_spine
from src.data.universe_loader import load_tier_a
from src.graph.relevance import (
    ActiveTheme,
    relevance_for_stock,
    relevance_for_universe,
    top_n,
)
from src.utils.db import init_db


@pytest.fixture(scope="module", autouse=True)
def _seed_phase8():
    init_db()
    load_tier_a()
    load_commodities_all()
    load_all_hand_peers()
    load_spine()


@pytest.fixture
def client():
    return TestClient(app)


# ── core relevance scoring ────────────────────────────────────────


def test_no_active_themes_returns_empty():
    out = relevance_for_universe([])
    assert out == {}


def test_oil_up_makes_xom_bullish():
    themes = [ActiveTheme(commodity_code="crude_oil", direction="up", intensity=1.0)]
    out = relevance_for_universe(themes)
    assert "XOM" in out
    assert out["XOM"].score > 0
    assert out["XOM"].magnitude > 0


def test_oil_up_does_not_include_unrelated_stocks():
    themes = [ActiveTheme(commodity_code="crude_oil", direction="up")]
    out = relevance_for_universe(themes)
    # AAPL has no crude-oil exposure → should be 0 OR absent
    if "AAPL" in out:
        assert out["AAPL"].magnitude < 0.1


def test_oil_down_flips_polarity():
    up = relevance_for_universe([ActiveTheme(commodity_code="crude_oil", direction="up")])
    down = relevance_for_universe([ActiveTheme(commodity_code="crude_oil", direction="down")])
    assert "XOM" in up and "XOM" in down
    # Oil down → XOM bearish
    assert up["XOM"].score > 0
    assert down["XOM"].score < 0


def test_intensity_scales_score():
    full = relevance_for_universe(
        [ActiveTheme(commodity_code="crude_oil", direction="up", intensity=1.0)]
    )
    half = relevance_for_universe(
        [ActiveTheme(commodity_code="crude_oil", direction="up", intensity=0.5)]
    )
    assert full["XOM"].magnitude > half["XOM"].magnitude


def test_target_stock_seed_appears_in_results():
    themes = [ActiveTheme(target_stock="NVDA", intensity=1.0)]
    out = relevance_for_universe(themes)
    # NVDA itself should be in results (as a seed)
    assert "NVDA" in out
    # 1-hop neighbors should also appear (TSM as supplier, MSFT as customer, AVGO as peer)
    assert {"TSM", "MSFT", "AVGO"} & set(out.keys())


def test_multiple_themes_compose():
    """Oil up AND uranium up — XOM (oil) and CCJ (uranium) should both surface."""
    themes = [
        ActiveTheme(commodity_code="crude_oil", direction="up"),
        ActiveTheme(commodity_code="uranium", direction="up"),
    ]
    out = relevance_for_universe(themes)
    assert "XOM" in out
    assert "CCJ" in out
    assert out["XOM"].score > 0
    assert out["CCJ"].score > 0


def test_tier_filter_restricts_results():
    themes = [ActiveTheme(commodity_code="crude_oil", direction="up")]
    out_a = relevance_for_universe(themes, tier=["A"])
    out_b = relevance_for_universe(themes, tier=["B"])
    # Tier A should have ≥ Tier B (everything in our seed is Tier A right now)
    assert len(out_a) >= len(out_b)


# ── relevance_for_stock convenience ──────────────────────────────


def test_relevance_for_stock_returns_zero_when_unaffected():
    themes = [ActiveTheme(commodity_code="cocoa", direction="up")]
    score = relevance_for_stock("XOM", themes)
    assert score.magnitude < 0.1


def test_relevance_for_stock_handles_unknown_symbol():
    themes = [ActiveTheme(commodity_code="crude_oil", direction="up")]
    score = relevance_for_stock("ZZZNOTAREAL", themes)
    assert score.magnitude == 0.0


# ── top_n helper ─────────────────────────────────────────────────


def test_top_n_sorts_by_magnitude_desc():
    themes = [ActiveTheme(commodity_code="crude_oil", direction="up")]
    scores = relevance_for_universe(themes)
    ranked = top_n(scores, n=5)
    mags = [r.magnitude for r in ranked]
    assert mags == sorted(mags, reverse=True)
    assert len(ranked) <= 5


def test_top_n_bullish_only_filters_negative_scores():
    """In an oil-up scenario, refiners (input crude_oil polarity=-1) might be
    bearish before the cost-passthrough flip. Bullish-only filter drops them."""
    themes = [ActiveTheme(commodity_code="crude_oil", direction="up")]
    scores = relevance_for_universe(themes)
    bullish = top_n(scores, bullish_only=True)
    for r in bullish:
        assert r.score > 0


# ── /graph/relevance endpoint ────────────────────────────────────


def test_endpoint_returns_200(client):
    r = client.post(
        "/graph/relevance",
        json={
            "active_themes": [{"commodity_code": "crude_oil", "direction": "up"}],
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert "active_themes" in payload
    assert "relevance" in payload


def test_endpoint_returns_xom_for_oil_up(client):
    r = client.post(
        "/graph/relevance",
        json={
            "active_themes": [{"commodity_code": "crude_oil", "direction": "up"}],
        },
    )
    syms = {row["symbol"] for row in r.json()["relevance"]}
    assert "XOM" in syms


def test_endpoint_rejects_empty_active_themes(client):
    r = client.post("/graph/relevance", json={"active_themes": []})
    assert r.status_code == 422


def test_endpoint_handles_target_stock_seed(client):
    r = client.post(
        "/graph/relevance",
        json={
            "active_themes": [{"target_stock": "NVDA", "intensity": 1.0}],
        },
    )
    assert r.status_code == 200
    syms = {row["symbol"] for row in r.json()["relevance"]}
    # NVDA seed itself + at least one 1-hop neighbor
    assert "NVDA" in syms or len(syms) >= 1


def test_endpoint_bullish_only_filters_negative(client):
    r = client.post(
        "/graph/relevance",
        json={
            "active_themes": [{"commodity_code": "crude_oil", "direction": "up"}],
            "bullish_only": True,
            "limit": 30,
        },
    )
    for row in r.json()["relevance"]:
        assert row["score"] > 0


def test_endpoint_tier_filter(client):
    r = client.post(
        "/graph/relevance",
        json={
            "active_themes": [{"commodity_code": "crude_oil", "direction": "up"}],
            "tier": ["A"],
        },
    )
    assert r.status_code == 200
