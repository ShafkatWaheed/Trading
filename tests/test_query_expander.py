"""Tests for src/news/query_expander.py."""

from __future__ import annotations

import pytest

from src.news import query_expander


@pytest.fixture(autouse=True)
def _reset_lookup_cache():
    query_expander._LOOKUPS_CACHE = None
    yield
    query_expander._LOOKUPS_CACHE = None


def test_empty_query_returns_empty_expansion():
    out = query_expander.expand_query("")
    assert out["keywords"] == []
    assert out["commodities"] == []
    assert out["industries"] == []
    assert "empty" in out["interpretation"].lower()


def test_returns_safe_empty_when_claude_fails(monkeypatch):
    """A None response from Claude must not raise — degrade gracefully."""
    monkeypatch.setattr(
        "src.news.query_expander.ask_claude_json",
        lambda *a, **kw: None,
    )
    out = query_expander.expand_query("some query")
    assert out["keywords"] == []
    assert out["commodities"] == []
    assert out["_raw"] is None


def test_parses_well_formed_response(monkeypatch):
    fake = {
        "keywords": ["war", "opec", "sanctions"],
        "commodities": [{"code": "crude_oil", "direction": "up", "intensity": 0.9}],
        "industries": [
            {"code": "Aerospace & Defense", "polarity": 0.7},
            {"code": "Airlines", "polarity": -0.5},
        ],
        "themes": ["supply_shock", "geopolitical_risk"],
        "substitutes_hint": ["EVs benefit from high oil"],
        "interpretation": "Middle-east oil-supply shock scenario.",
    }
    monkeypatch.setattr(
        "src.news.query_expander.ask_claude_json",
        lambda *a, **kw: fake,
    )
    out = query_expander.expand_query("middle east war oil supply hit hard")
    assert out["keywords"] == ["war", "opec", "sanctions"]
    assert out["commodities"][0]["code"] == "crude_oil"
    assert out["commodities"][0]["direction"] == "up"
    assert abs(out["commodities"][0]["intensity"] - 0.9) < 0.001
    assert len(out["industries"]) == 2
    assert out["themes"] == ["supply_shock", "geopolitical_risk"]
    assert "Middle-east" in out["interpretation"]


def test_drops_unknown_commodity_codes(monkeypatch):
    fake = {
        "keywords": [],
        "commodities": [
            {"code": "crude_oil", "direction": "up", "intensity": 0.5},
            {"code": "unobtanium", "direction": "up", "intensity": 0.9},  # fake
        ],
        "industries": [],
        "themes": [],
        "substitutes_hint": [],
        "interpretation": "",
    }
    monkeypatch.setattr(
        "src.news.query_expander.ask_claude_json",
        lambda *a, **kw: fake,
    )
    out = query_expander.expand_query("query")
    codes = [c["code"] for c in out["commodities"]]
    assert "crude_oil" in codes
    assert "unobtanium" not in codes


def test_clamps_intensity_to_valid_range(monkeypatch):
    fake = {
        "keywords": [],
        "commodities": [{"code": "crude_oil", "direction": "up", "intensity": 5.0}],
        "industries": [],
        "themes": [],
        "substitutes_hint": [],
        "interpretation": "",
    }
    monkeypatch.setattr(
        "src.news.query_expander.ask_claude_json",
        lambda *a, **kw: fake,
    )
    out = query_expander.expand_query("query")
    assert out["commodities"][0]["intensity"] == 1.0


def test_normalises_direction(monkeypatch):
    fake = {
        "keywords": [],
        "commodities": [{"code": "crude_oil", "direction": "UPWARD", "intensity": 0.5}],
        "industries": [],
        "themes": [],
        "substitutes_hint": [],
        "interpretation": "",
    }
    monkeypatch.setattr(
        "src.news.query_expander.ask_claude_json",
        lambda *a, **kw: fake,
    )
    out = query_expander.expand_query("query")
    # Invalid direction falls back to "up"
    assert out["commodities"][0]["direction"] == "up"


def test_drops_unknown_industry_codes(monkeypatch):
    fake = {
        "keywords": [],
        "commodities": [],
        "industries": [
            {"code": "Aerospace & Defense", "polarity": 0.7},
            {"code": "Not A Real Industry Name", "polarity": 0.5},
        ],
        "themes": [],
        "substitutes_hint": [],
        "interpretation": "",
    }
    monkeypatch.setattr(
        "src.news.query_expander.ask_claude_json",
        lambda *a, **kw: fake,
    )
    out = query_expander.expand_query("q")
    codes = [i["code"] for i in out["industries"]]
    assert "Aerospace & Defense" in codes
    assert "Not A Real Industry Name" not in codes


def test_clamps_polarity_to_minus_one_to_one(monkeypatch):
    fake = {
        "keywords": [],
        "commodities": [],
        "industries": [{"code": "Aerospace & Defense", "polarity": 7.5}],
        "themes": [],
        "substitutes_hint": [],
        "interpretation": "",
    }
    monkeypatch.setattr(
        "src.news.query_expander.ask_claude_json",
        lambda *a, **kw: fake,
    )
    out = query_expander.expand_query("q")
    assert out["industries"][0]["polarity"] == 1.0


def test_garbage_response_returns_empty_arrays(monkeypatch):
    monkeypatch.setattr(
        "src.news.query_expander.ask_claude_json",
        lambda *a, **kw: "this isn't a dict",
    )
    out = query_expander.expand_query("q")
    assert out["keywords"] == []
    assert out["commodities"] == []
