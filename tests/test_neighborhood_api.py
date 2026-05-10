"""Tests for the neighborhood service + GET /graph/stock/{sym}/neighborhood."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services.neighborhood_service import get_neighborhood
from src.data.peer_seed_loader import load_all_hand_peers
from src.data.relations_seed_loader import load_spine
from src.data.universe_loader import load_tier_a
from src.utils.db import init_db


@pytest.fixture(scope="module", autouse=True)
def _seed_graph():
    init_db()
    load_tier_a()
    load_all_hand_peers()
    load_spine()


@pytest.fixture
def client():
    return TestClient(app)


# ── service ──────────────────────────────────────────────────────


def test_get_neighborhood_returns_panels():
    out = get_neighborhood("NVDA")
    for k in ("suppliers", "customers", "peers", "substitutes", "complements"):
        assert k in out
        assert isinstance(out[k], list)


def test_nvda_neighborhood_includes_tsm_supplier():
    out = get_neighborhood("NVDA")
    sup_syms = {e["symbol"] for e in out["suppliers"]}
    assert "TSM" in sup_syms


def test_nvda_neighborhood_includes_msft_customer():
    out = get_neighborhood("NVDA")
    cust_syms = {e["symbol"] for e in out["customers"]}
    assert "MSFT" in cust_syms


def test_nvda_neighborhood_includes_amd_peer():
    out = get_neighborhood("NVDA")
    peer_syms = {e["symbol"] for e in out["peers"]}
    assert "AMD" in peer_syms


def test_nvda_neighborhood_includes_complement_with_vrt():
    out = get_neighborhood("NVDA")
    comps = {e["symbol"] for e in out["complements"]}
    assert "VRT" in comps or "GEV" in comps or "ETN" in comps


def test_neighborhood_attaches_tier_to_each_neighbor():
    out = get_neighborhood("NVDA")
    for panel in ("suppliers", "customers", "peers"):
        for e in out[panel]:
            # Tier must be A/B/C/D for in-universe neighbors (None acceptable for orphans).
            if e["tier"]:
                assert e["tier"] in ("A", "B", "C", "D")


def test_neighborhood_attaches_self_metadata():
    out = get_neighborhood("NVDA")
    assert out["symbol"] == "NVDA"
    assert out["tier"] == "A"
    assert out["name"] is not None


def test_neighborhood_unknown_symbol_returns_empty_panels():
    out = get_neighborhood("ZZZNOTAREALSYMBOL")
    assert out["tier"] is None
    for panel in ("suppliers", "customers", "peers", "substitutes", "complements"):
        assert out[panel] == []


def test_substitutes_panel_carries_negative_polarity():
    out = get_neighborhood("TSLA")
    if out["substitutes"]:
        for e in out["substitutes"]:
            assert e["polarity"] < 0


# ── /graph/stock/{sym}/neighborhood endpoint ─────────────────────


def test_endpoint_returns_200(client):
    r = client.get("/graph/stock/NVDA/neighborhood")
    assert r.status_code == 200
    payload = r.json()
    assert payload["symbol"] == "NVDA"
    for k in ("suppliers", "customers", "peers", "substitutes", "complements"):
        assert k in payload


def test_endpoint_lowercase_symbol_normalised(client):
    r = client.get("/graph/stock/nvda/neighborhood")
    assert r.status_code == 200
    assert r.json()["symbol"] == "NVDA"


def test_endpoint_payload_includes_supply_chain_evidence(client):
    r = client.get("/graph/stock/NVDA/neighborhood")
    payload = r.json()
    if payload["suppliers"]:
        # At least one supplier should have evidence text from the seed
        has_evidence = any(s.get("evidence") for s in payload["suppliers"])
        assert has_evidence


def test_endpoint_unknown_symbol_returns_200_with_empties(client):
    r = client.get("/graph/stock/XYZNOPE/neighborhood")
    assert r.status_code == 200
    assert r.json()["suppliers"] == []
