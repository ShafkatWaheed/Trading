"""End-to-end tests for the /news-impact endpoint.

Loads the real keyword_impact seed + Tier A spine, then runs realistic
historical headlines through the API and verifies expected stocks surface.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from src.data.conglomerate_overrides import apply_conglomerate_overrides
from src.data.industries_seed import load_industries
from src.data.keyword_seed_loader import load_keyword_impact
from src.data.universe_loader import load_tier_a
from src.utils.db import init_db


@pytest.fixture(scope="module", autouse=True)
def _ensure_seeds_loaded():
    """Load all the seed data once for the module."""
    init_db()
    load_industries()
    load_tier_a()
    apply_conglomerate_overrides()
    load_keyword_impact()


@pytest.fixture
def client():
    return TestClient(app)


def _post(client: TestClient, text: str) -> dict:
    r = client.post("/news-impact", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def _symbols(payload: dict) -> set[str]:
    return {s["symbol"] for s in payload["stocks"]}


def _industries(payload: dict) -> dict[str, float]:
    """{industry_code: polarity}"""
    return {i["industry_code"]: i["polarity"] for i in payload["industries"]}


# ── basic plumbing ─────────────────────────────────────────────────


def test_endpoint_returns_200_for_simple_text(client):
    payload = _post(client, "AI demand booms")
    assert "stocks" in payload
    assert "industries" in payload


def test_endpoint_rejects_empty_body(client):
    r = client.post("/news-impact", json={"text": ""})
    assert r.status_code == 422


# ── headline 1: AI capex ───────────────────────────────────────────


def test_ai_capex_headline_returns_semis_positive(client):
    payload = _post(client, "OpenAI announces $50B GPU build-out for new data center")
    inds = _industries(payload)
    assert inds.get("Semiconductors", 0) > 0
    syms = _symbols(payload)
    # Tier A semis must surface
    assert {"NVDA", "AVGO", "AMD"} <= syms
    # Polarity must be positive
    nvda = next(s for s in payload["stocks"] if s["symbol"] == "NVDA")
    assert nvda["polarity"] > 0


def test_ai_capex_includes_second_derivative_power(client):
    payload = _post(client, "AI data center build-out drives record GPU orders")
    syms = _symbols(payload)
    # Power / utility / electrical infra plays should appear
    second_deriv = {"GEV", "ETN", "CEG", "VST", "NEE", "CCJ"}
    assert second_deriv & syms, f"expected at least one 2nd-derivative play; got {syms}"


# ── headline 2: oil shock ──────────────────────────────────────────


def test_iran_saudi_headline_returns_defense_and_oil_positive(client):
    payload = _post(client, "Iran fires missiles at Saudi Aramco oil refinery")
    syms = _symbols(payload)
    inds = _industries(payload)

    # Defense + oil positive
    assert inds.get("Aerospace & Defense", 0) > 0
    assert inds.get("Oil & Gas E&P", 0) > 0
    # Tier A defense + oil names surface
    assert {"LMT", "NOC", "RTX"} & syms
    assert {"XOM", "CVX", "OXY"} & syms


def test_oil_headline_makes_airlines_negative(client):
    payload = _post(client, "Oil prices surge to $120 after Iran-Saudi conflict")
    inds = _industries(payload)
    # Airlines polarity negative if matched
    if "Airlines" in inds:
        assert inds["Airlines"] < 0


# ── headline 3: tariff / trade war ─────────────────────────────────


def test_tariff_headline_promotes_steel_with_china_co_occurrence(client):
    payload = _post(client, "US imposes 25% tariff on Chinese steel imports")
    inds = _industries(payload)
    assert inds.get("Steel", 0) > 0


# ── headline 4: rate cut ───────────────────────────────────────────


def test_rate_cut_headline_promotes_growth_tech(client):
    payload = _post(client, "Fed announces rate cut, signaling end of tightening cycle")
    inds = _industries(payload)
    # Software + REITs positive; banks negative (NIM compression)
    assert inds.get("Software—Infrastructure", 0) > 0 or inds.get("Software—Application", 0) > 0
    if "REIT—Industrial" in inds:
        assert inds["REIT—Industrial"] > 0


# ── headline 5: gas crisis ─────────────────────────────────────────


def test_gas_crisis_promotes_fertilizers(client):
    payload = _post(
        client,
        "European natural gas storage at 30%, lowest since 2022, prices surge",
    )
    inds = _industries(payload)
    assert inds.get("Agricultural Inputs", 0) > 0


# ── headline 6: hurricane ──────────────────────────────────────────


def test_hurricane_makes_insurers_negative_and_home_improvement_positive(client):
    payload = _post(
        client,
        "Hurricane Milton makes landfall in Florida with Category 4 strength",
    )
    inds = _industries(payload)
    # Insurance polarity negative
    if "Insurance—Property & Casualty" in inds:
        assert inds["Insurance—Property & Casualty"] < 0
    # Home improvement retail positive (HD/LOW)
    if "Home Improvement Retail" in inds:
        assert inds["Home Improvement Retail"] > 0


# ── headline 7: GLP-1 ──────────────────────────────────────────────


def test_glp1_headline_promotes_pharma_and_hits_snacks(client):
    payload = _post(client, "Eli Lilly Mounjaro and Wegovy GLP-1 demand exceeds expectations")
    inds = _industries(payload)
    assert inds.get("Drug Manufacturers—General", 0) > 0
    if "Packaged Foods" in inds:
        assert inds["Packaged Foods"] < 0


# ── negation handling ─────────────────────────────────────────────


def test_negated_headline_flips_polarity(client):
    """'Tariffs cancelled' should NOT make Steel positive — negation flips."""
    payload = _post(client, "Tariffs on Chinese steel cancelled after deal reached")
    assert "tariff" in payload["negated_keywords"]
    inds = _industries(payload)
    if "Steel" in inds:
        # The "tariff" hit was negated; the only Steel-positive contribution
        # would have come from the "tariff" keyword. Either Steel is absent
        # or its polarity is now negative (or near zero).
        assert inds["Steel"] <= 0.0


# ── traceability ──────────────────────────────────────────────────


def test_response_includes_matched_keyword_trace(client):
    payload = _post(client, "Iran fires missiles at Saudi oil refinery")
    matched = set(payload["matched_keywords"])
    assert {"oil"} <= matched
    countries = set(payload["matched_countries"])
    assert "iran" in countries


def test_response_includes_contributing_keywords_per_stock(client):
    payload = _post(client, "OpenAI announces $50B GPU build-out for new data center")
    nvda = next((s for s in payload["stocks"] if s["symbol"] == "NVDA"), None)
    assert nvda is not None
    assert len(nvda["contributing_keywords"]) >= 1


def test_results_sorted_by_composite_score(client):
    payload = _post(client, "AI demand booms with new GPU and data center capex")
    scores = [s["composite_score"] for s in payload["stocks"]]
    # direct_target stocks come first; among non-direct, scores must be non-increasing
    non_direct = [s for s in payload["stocks"] if not s["direct_target"]]
    if len(non_direct) > 1:
        scores_nd = [s["composite_score"] for s in non_direct]
        assert scores_nd == sorted(scores_nd, reverse=True)


def test_tier_a_stocks_preferred_over_lower_tiers(client):
    """When Tier A and Tier B/C stocks both match, Tier A on average should
    rank higher (the tier weight multiplier favours A=1.0 over B=0.7/C=0.4).

    With ~3k stocks in the universe, individual Tier B stocks can outscore
    individual Tier A stocks on industry-fit grounds — that's expected. We
    instead check the *aggregate*: mean Tier A composite_score >= mean of
    the rest, which is the soundness property the tier weight is supposed
    to enforce.
    """
    payload = _post(client, "GPU demand booms")
    tier_a = [s for s in payload["stocks"] if s["tier"] == "A"]
    others = [s for s in payload["stocks"] if s["tier"] != "A"]
    if tier_a and others:
        avg_a = sum(s["composite_score"] for s in tier_a) / len(tier_a)
        avg_o = sum(s["composite_score"] for s in others) / len(others)
        assert avg_a >= avg_o, (
            f"Tier A average ({avg_a:.3f}) should be >= other tiers ({avg_o:.3f})"
        )
