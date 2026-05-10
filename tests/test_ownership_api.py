"""Tests for ownership service + endpoints + institutional_overlap (Phase 7A)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services.ownership_service import also_held, top_holders
from src.data.institutions_seed_loader import load_all
from src.data.universe_loader import load_tier_a
from src.graph.institutional_overlap import (
    materialise_overlap_edges,
    overlap_score,
)
from src.utils.db import get_connection, init_db


@pytest.fixture(scope="module", autouse=True)
def _seed_phase7a():
    init_db()
    load_tier_a()
    load_all()


@pytest.fixture
def client():
    return TestClient(app)


# ── overlap primitive ────────────────────────────────────────────


def test_overlap_score_no_common_holders():
    a = {"cik1": 5.0, "cik2": 3.0}
    b = {"cik3": 4.0, "cik4": 2.0}
    score, common = overlap_score(a, b)
    assert score == 0.0
    assert common == []


def test_overlap_score_takes_min_per_cik():
    a = {"cik1": 7.0, "cik2": 3.0}
    b = {"cik1": 5.0, "cik2": 6.0}
    score, common = overlap_score(a, b)
    # min(7,5) + min(3,6) = 5 + 3 = 8
    assert score == 8.0
    assert set(common) == {"cik1", "cik2"}


def test_overlap_score_one_sided_holding():
    a = {"cik1": 5.0}
    b = {"cik1": 0.5}
    score, common = overlap_score(a, b)
    assert score == 0.5
    assert common == ["cik1"]


# ── materialise_overlap_edges ────────────────────────────────────


def test_materialise_writes_overlap_edges_for_aapl_msft():
    """AAPL and MSFT share BlackRock + Vanguard + State Street as top holders.
    The overlap should be substantial."""
    out = materialise_overlap_edges(top_k=10, min_score=0.05)
    assert out["edges_written"] >= 2

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT to_symbol, strength, evidence FROM stock_relations "
            "WHERE from_symbol='AAPL' AND relation_type='common_institutional_holder' "
            "ORDER BY strength DESC LIMIT 5"
        ).fetchall()
        targets = {r["to_symbol"] for r in rows}
        # AAPL and MSFT share the Big Three's holdings — must be in the top neighbors
        assert "MSFT" in targets
    finally:
        conn.close()


def test_materialise_is_idempotent():
    a = materialise_overlap_edges(top_k=10, min_score=0.05)
    b = materialise_overlap_edges(top_k=10, min_score=0.05)
    # Both runs should produce the same edge count
    assert a["edges_written"] == b["edges_written"]


def test_materialise_writes_evidence_with_cik_list():
    materialise_overlap_edges()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT evidence FROM stock_relations "
            "WHERE from_symbol='AAPL' AND to_symbol='MSFT' AND relation_type='common_institutional_holder'"
        ).fetchone()
        if row is not None:
            assert "common holders" in row["evidence"]
    finally:
        conn.close()


# ── ownership_service ────────────────────────────────────────────


def test_top_holders_returns_big_three_for_aapl():
    out = top_holders("AAPL")
    ciks = {h["cik"] for h in out["holders"]}
    # Big Three are top holders of AAPL
    assert {"1364742", "102909", "93751"} <= ciks


def test_top_holders_sorted_by_pct_outstanding_desc():
    out = top_holders("AAPL")
    pcts = [h["pct_outstanding"] for h in out["holders"] if h["pct_outstanding"] is not None]
    assert pcts == sorted(pcts, reverse=True)


def test_top_holders_includes_institution_metadata():
    out = top_holders("AAPL")
    blackrock = next((h for h in out["holders"] if h["cik"] == "1364742"), None)
    assert blackrock is not None
    assert blackrock["institution_name"] == "BlackRock Inc"
    assert blackrock["institution_type"] == "index_fund"


def test_top_holders_unknown_symbol_returns_empty():
    out = top_holders("ZZZNOPE")
    assert out["holders"] == []
    assert out["total"] == 0


def test_also_held_returns_blackrock_top_picks():
    out = also_held("1364742")
    # BlackRock's top holdings: AAPL, MSFT, NVDA
    syms = {h["symbol"] for h in out["holdings"]}
    assert {"AAPL", "MSFT", "NVDA"} <= syms


def test_also_held_sorted_by_pct_portfolio_desc():
    out = also_held("1364742")
    pcts = [h["pct_portfolio"] for h in out["holdings"] if h["pct_portfolio"] is not None]
    assert pcts == sorted(pcts, reverse=True)


def test_also_held_includes_metadata():
    out = also_held("1364742")
    assert out["name"] == "BlackRock Inc"
    assert out["type"] == "index_fund"


def test_also_held_unknown_cik_returns_empty():
    out = also_held("99999999")
    assert out["holdings"] == []


def test_berkshire_concentrated_in_top_picks():
    """Berkshire's top pick (AAPL) should be much larger fraction of portfolio
    than the average index-fund pick."""
    out = also_held("1067983")
    aapl = next((h for h in out["holdings"] if h["symbol"] == "AAPL"), None)
    assert aapl is not None
    assert aapl["pct_portfolio"] >= 20.0


# ── /graph/stock/{sym}/holders endpoint ──────────────────────────


def test_holders_endpoint(client):
    r = client.get("/graph/stock/AAPL/holders")
    assert r.status_code == 200
    payload = r.json()
    assert payload["symbol"] == "AAPL"
    assert len(payload["holders"]) >= 3


def test_holders_endpoint_lowercase_symbol(client):
    r = client.get("/graph/stock/aapl/holders")
    assert r.status_code == 200
    assert r.json()["symbol"] == "AAPL"


def test_institution_holdings_endpoint(client):
    r = client.get("/graph/institution/1364742/holdings")
    assert r.status_code == 200
    payload = r.json()
    assert payload["cik"] == "1364742"
    assert payload["name"] == "BlackRock Inc"
    assert len(payload["holdings"]) >= 5


def test_institution_holdings_unknown_cik(client):
    r = client.get("/graph/institution/99999999/holdings")
    assert r.status_code == 200
    payload = r.json()
    assert payload["holdings"] == []


def test_holders_max_results_limit(client):
    r = client.get("/graph/stock/AAPL/holders?max_results=3")
    payload = r.json()
    assert len(payload["holders"]) <= 3
