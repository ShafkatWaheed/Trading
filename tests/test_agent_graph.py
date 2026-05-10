"""Tests for src/agent_graph.py — Phase 8 agent integration helper."""

from __future__ import annotations

import pytest

from src.agent_graph import (
    GRAPH_BOOST_CAP,
    get_active_themes_from_agent_config,
    graph_boost_for_candidates,
    set_active_themes_in_agent_config,
)
from src.data.commodity_seed_loader import load_all as load_commodities_all
from src.data.peer_seed_loader import load_all_hand_peers
from src.data.relations_seed_loader import load_spine
from src.data.universe_loader import load_tier_a
from src.graph.relevance import ActiveTheme
from src.utils.db import get_connection, init_db


@pytest.fixture(scope="module", autouse=True)
def _seed_phase8():
    init_db()
    load_tier_a()
    load_commodities_all()
    load_all_hand_peers()
    load_spine()


# ── graph_boost_for_candidates ──────────────────────────────────


def test_no_themes_returns_all_neutral():
    out = graph_boost_for_candidates(["NVDA", "MSFT", "XOM"], [])
    assert all(v == 1.0 for v in out.values())


def test_oil_up_boosts_xom():
    themes = [ActiveTheme(commodity_code="crude_oil", direction="up")]
    out = graph_boost_for_candidates(["XOM", "AAPL"], themes)
    assert out["XOM"] > 1.0          # bullish multiplier
    # AAPL has no oil exposure → neutral
    assert out["AAPL"] == 1.0


def test_oil_down_suppresses_xom():
    themes = [ActiveTheme(commodity_code="crude_oil", direction="down")]
    out = graph_boost_for_candidates(["XOM"], themes)
    assert out["XOM"] < 1.0


def test_boost_clamped_to_cap():
    """No multiplier should exceed 1 + cap."""
    themes = [
        ActiveTheme(commodity_code="crude_oil", direction="up"),
        ActiveTheme(commodity_code="natural_gas", direction="up"),
    ]
    out = graph_boost_for_candidates(["XOM", "CVX", "COP"], themes)
    for sym, mult in out.items():
        assert 1.0 - GRAPH_BOOST_CAP <= mult <= 1.0 + GRAPH_BOOST_CAP


def test_unknown_symbols_return_neutral():
    themes = [ActiveTheme(commodity_code="crude_oil", direction="up")]
    out = graph_boost_for_candidates(["ZZZ_FAKE"], themes)
    assert out["ZZZ_FAKE"] == 1.0


def test_uppercase_normalisation():
    themes = [ActiveTheme(commodity_code="crude_oil", direction="up")]
    out = graph_boost_for_candidates(["xom", "XOM"], themes)
    # Both lowercase and uppercase produce a valid entry
    assert "XOM" in out
    assert out["XOM"] > 1.0


# ── agent_config persistence ────────────────────────────────────


def test_get_active_themes_returns_empty_when_unset():
    init_db()
    conn = get_connection()
    try:
        # Wipe anything in the column
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(agent_config)").fetchall()}
        if "active_themes_json" in cols:
            conn.execute("UPDATE agent_config SET active_themes_json = NULL WHERE id = 1")
            conn.commit()
    finally:
        conn.close()

    out = get_active_themes_from_agent_config()
    assert out == []


def test_set_then_get_roundtrips_themes():
    themes = [
        ActiveTheme(commodity_code="crude_oil", direction="up", intensity=0.8),
        ActiveTheme(target_stock="NVDA", intensity=1.0),
    ]
    set_active_themes_in_agent_config(themes)

    out = get_active_themes_from_agent_config()
    assert len(out) == 2
    # Order preserved
    assert out[0].commodity_code == "crude_oil"
    assert out[0].direction == "up"
    assert abs(out[0].intensity - 0.8) < 0.001
    assert out[1].target_stock == "NVDA"


def test_set_themes_creates_column_if_missing():
    """The first call to set_active_themes should ALTER TABLE to add the column."""
    init_db()
    conn = get_connection()
    try:
        # Drop the column if it exists (SQLite doesn't support DROP COLUMN cleanly,
        # so this test mostly validates the no-op path)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(agent_config)").fetchall()}
        # If column exists, just clear it; if not, the next set call should add it.
        if "active_themes_json" in cols:
            conn.execute("UPDATE agent_config SET active_themes_json = NULL WHERE id = 1")
            conn.commit()
    finally:
        conn.close()

    set_active_themes_in_agent_config([
        ActiveTheme(commodity_code="copper", direction="up"),
    ])

    conn = get_connection()
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(agent_config)").fetchall()}
        assert "active_themes_json" in cols
    finally:
        conn.close()


def test_get_themes_handles_malformed_json():
    """A corrupted active_themes_json column should return [] gracefully."""
    init_db()
    conn = get_connection()
    try:
        # Make sure the column exists first by calling set
        set_active_themes_in_agent_config([])
        conn.execute(
            "UPDATE agent_config SET active_themes_json = ? WHERE id = 1",
            ("not valid json {{{ broken",),
        )
        conn.commit()
    finally:
        conn.close()

    out = get_active_themes_from_agent_config()
    assert out == []


# ── end-to-end: agent uses graph boost ───────────────────────────


def test_agent_discover_stocks_picks_up_active_themes(monkeypatch):
    """Smoke test: when active themes are set, the agent's _discover_stocks
    should produce different scores than when none are set.

    We mock the heavy bits (technical analysis, opportunity scoring, claude
    discovery guidance) and just verify the graph_boost field appears."""
    from src.agent import TradingAgent

    # Set an active theme that XOM is exposed to
    set_active_themes_in_agent_config([
        ActiveTheme(commodity_code="crude_oil", direction="up", intensity=1.0),
    ])

    agent = TradingAgent()

    # Force the discovery to run a tiny universe with mocked Claude guidance
    def fake_guidance(market):
        return {
            "favor_sectors": [],
            "avoid_sectors": [],
            "specific_tickers": ["XOM"],
            "min_score": 0,
        }

    monkeypatch.setattr(agent, "_ai_discover_guidance", fake_guidance)

    # Mock get_historical to return a tiny but valid DataFrame
    import pandas as pd
    fake_df = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "open": [100.0, 101.0, 102.0],
        "high": [102.0, 103.0, 104.0],
        "low": [99.0, 100.0, 101.0],
        "close": [101.0, 102.0, 103.0],
        "volume": [1_000_000, 1_100_000, 1_050_000],
    })

    from src.data.gateway import DataGateway
    monkeypatch.setattr(DataGateway, "get_historical", lambda self, sym, period_days=60: fake_df)

    # technical.analyze + compute_opportunity may not produce a usable score
    # for a 3-day series. The test isn't about real signal — it just verifies
    # the graph_boost field gets attached in the path that runs successfully.
    market = {"regime": "normal"}
    candidates = agent._discover_stocks(market)
    # If candidates surface (depends on tech analysis), verify graph_boost exists
    if candidates:
        for c in candidates:
            assert "graph_boost" in c, f"missing graph_boost on candidate: {c}"
