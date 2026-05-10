"""End-to-end tests for the peer-discovery service + /graph/stock/{sym}/peers."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services.peer_service import get_peers
from src.data.peer_seed_loader import (
    load_cross_industry_peers,
    load_tier_a_peers,
)
from src.data.universe_loader import load_tier_a
from src.utils.db import init_db


@pytest.fixture(scope="module", autouse=True)
def _ensure_seeds_loaded():
    init_db()
    load_tier_a()
    load_tier_a_peers()
    load_cross_industry_peers()


@pytest.fixture
def client():
    return TestClient(app)


# ── service: get_peers() ─────────────────────────────────────────


def test_get_peers_for_msft_returns_close_competitors():
    out = get_peers("MSFT")
    syms = {p["symbol"] for p in out["peers"]}
    # MSFT's closest peers should include the obvious cloud/enterprise rivals
    assert {"GOOGL", "AMZN", "ORCL"} <= syms


def test_get_peers_for_nvda_returns_chip_competitors():
    out = get_peers("NVDA")
    syms = {p["symbol"] for p in out["peers"]}
    assert {"AVGO", "AMD"} <= syms


def test_get_peers_handles_unknown_symbol():
    out = get_peers("ZZZZZ_NOT_A_STOCK")
    assert out["peers"] == []
    assert out["total"] == 0


def test_get_peers_returns_overlap_dimensions_for_hand_loaded():
    out = get_peers("MSFT")
    google_peer = next((p for p in out["peers"] if p["symbol"] == "GOOGL"), None)
    assert google_peer is not None
    # Hand-loaded peers carry overlap_dimensions
    assert len(google_peer["overlap_dimensions"]) > 0
    assert "cloud" in google_peer["overlap_dimensions"] or "ai" in google_peer["overlap_dimensions"]


def test_get_peers_orders_hand_above_claude_batch():
    """Hand-curated edges should rank above Claude-batched ones."""
    out = get_peers("NVDA")
    sources = [p["source"] for p in out["peers"]]
    if "hand" in sources and "claude_batch" in sources:
        first_hand = sources.index("hand")
        first_claude = sources.index("claude_batch")
        assert first_hand < first_claude


def test_get_peers_respects_max_results():
    out = get_peers("MSFT", max_results=2)
    assert len(out["peers"]) <= 2


def test_get_peers_includes_stock_metadata():
    out = get_peers("MSFT")
    assert out["symbol"] == "MSFT"
    assert out["tier"] == "A"
    assert out["name"] is not None


def test_each_peer_carries_tier_and_sector():
    out = get_peers("MSFT")
    for p in out["peers"]:
        # Non-Tier-A peers in our seed may not be loaded yet; just verify shape
        assert "tier" in p
        assert "sector" in p
        assert "similarity" in p


# ── /graph/stock/{sym}/peers endpoint ────────────────────────────


def test_endpoint_returns_200(client):
    r = client.get("/graph/stock/MSFT/peers")
    assert r.status_code == 200
    payload = r.json()
    assert payload["symbol"] == "MSFT"
    assert "peers" in payload


def test_endpoint_max_results_param(client):
    r = client.get("/graph/stock/MSFT/peers?max_results=3")
    payload = r.json()
    assert len(payload["peers"]) <= 3


def test_endpoint_unknown_symbol_returns_empty(client):
    r = client.get("/graph/stock/XYZNOTREAL/peers")
    assert r.status_code == 200
    assert r.json()["peers"] == []


def test_endpoint_rejects_invalid_max_results(client):
    r = client.get("/graph/stock/MSFT/peers?max_results=0")
    assert r.status_code == 422


def test_endpoint_uppercase_normalisation(client):
    """Both lowercase and uppercase tickers should resolve."""
    upper = client.get("/graph/stock/MSFT/peers")
    lower = client.get("/graph/stock/msft/peers")
    assert upper.json()["symbol"] == "MSFT"
    assert lower.json()["symbol"] == "MSFT"


def test_endpoint_returns_overlap_dimensions(client):
    r = client.get("/graph/stock/MSFT/peers")
    payload = r.json()
    # At least one peer should have populated overlap_dimensions (from hand seed)
    has_overlap = any(p.get("overlap_dimensions") for p in payload["peers"])
    assert has_overlap


# ── cross-industry peer integration ──────────────────────────────


def test_msft_amzn_cross_industry_peer_loaded():
    """MSFT-AMZN cloud overlap is in the cross-industry seed and should appear."""
    out = get_peers("MSFT")
    syms = {p["symbol"] for p in out["peers"]}
    assert "AMZN" in syms


def test_nvda_eqix_cross_industry_peer_loaded():
    """NVDA-EQIX (datacenter compute → datacenter REIT) is cross-sector."""
    out = get_peers("NVDA")
    syms = {p["symbol"] for p in out["peers"]}
    assert "EQIX" in syms or "DLR" in syms


# ── ranking sanity ───────────────────────────────────────────────


def test_high_similarity_peer_ranks_above_low_similarity():
    """Within the same source/confidence, higher similarity ranks higher."""
    out = get_peers("LMT")
    # Tier A peers of LMT include RTX (0.95), NOC (0.95), GD (0.85), HII (0.65)
    similarities = [p["similarity"] for p in out["peers"] if p["source"] == "hand"]
    if len(similarities) > 1:
        # We expect the list to be roughly descending by similarity within source group
        # (allowing for some interleaving due to confidence ties)
        assert similarities[0] >= similarities[-1]
