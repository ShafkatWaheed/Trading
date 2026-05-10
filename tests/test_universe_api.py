"""Tests for the universe service + /universe endpoint + conglomerate overrides."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.services.universe_service import get_universe
from src.data.conglomerate_overrides import (
    CONGLOMERATE_TAGS,
    apply_conglomerate_overrides,
)
from src.data.universe_loader import load_tier_a
from src.utils.db import get_connection, init_db


# ── Conglomerate weight integrity ───────────────────────────────────


def test_every_conglomerate_weights_sum_to_one():
    for symbol, tags in CONGLOMERATE_TAGS:
        total = sum(w for _, w in tags)
        assert abs(total - 1.0) < 0.01, f"{symbol} weights sum to {total}, not 1.0"


def test_no_duplicate_conglomerate_symbols():
    syms = [s for s, _ in CONGLOMERATE_TAGS]
    assert len(syms) == len(set(syms))


def test_apply_conglomerate_overrides_replaces_yfinance_tag():
    """If yfinance wrote a single AMZN→Internet Retail row, the override must
    replace it with multiple weighted rows."""
    init_db()
    load_tier_a()

    conn = get_connection()
    try:
        # Simulate a prior yfinance run: insert a single tag we'll watch get replaced.
        conn.execute("DELETE FROM stock_industry WHERE symbol='AMZN'")
        conn.execute(
            "INSERT INTO stock_industry (symbol, industry_code, weight, is_primary, source) "
            "VALUES ('AMZN', 'Internet Retail', 1.0, 1, 'yfinance')"
        )
        conn.commit()
    finally:
        conn.close()

    apply_conglomerate_overrides()

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT industry_code, weight, is_primary, source FROM stock_industry "
            "WHERE symbol='AMZN' ORDER BY weight DESC"
        ).fetchall()
        # No yfinance rows left, only hand_conglomerate
        assert all(r["source"] == "hand_conglomerate" for r in rows)
        # Multiple industries now
        assert len(rows) >= 3
        # Total weight ≈ 1.0
        assert abs(sum(r["weight"] for r in rows) - 1.0) < 0.01
        # Exactly one is_primary
        assert sum(1 for r in rows if r["is_primary"]) == 1
        # The primary is the highest-weight
        primary = next(r for r in rows if r["is_primary"])
        assert primary["weight"] == max(r["weight"] for r in rows)
    finally:
        conn.close()


def test_apply_conglomerate_overrides_idempotent():
    apply_conglomerate_overrides()
    second = apply_conglomerate_overrides()
    assert second["symbols"] == len(CONGLOMERATE_TAGS)


# ── Universe service ────────────────────────────────────────────────


def test_get_universe_returns_tier_a_stocks_when_tier_filter_set():
    load_tier_a()
    out = get_universe(tier=["A"], limit=500)
    assert all(s["tier"] == "A" for s in out["stocks"])
    assert out["counts"]["A"] >= 100  # Tier A seed is ~150


def test_get_universe_returns_industries_attached():
    load_tier_a()
    out = get_universe(tier=["A"], limit=10)
    sample = out["stocks"][0]
    assert "industries" in sample
    assert all("code" in i and "weight" in i for i in sample["industries"])


def test_get_universe_filter_by_industry():
    load_tier_a()
    out = get_universe(industry="Semiconductors", limit=100)
    syms = {s["symbol"] for s in out["stocks"]}
    # Several Tier A semis must be present
    assert "NVDA" in syms
    assert "AMD" in syms
    assert "AVGO" in syms


def test_get_universe_filter_by_sector():
    load_tier_a()
    out = get_universe(sector="Healthcare", limit=200)
    # Tier A pharma giants should be present
    syms = {s["symbol"] for s in out["stocks"]}
    assert "LLY" in syms
    assert "JNJ" in syms
    assert "MRK" in syms


def test_get_universe_pagination():
    load_tier_a()
    page1 = get_universe(tier=["A"], limit=10, offset=0)
    page2 = get_universe(tier=["A"], limit=10, offset=10)
    syms1 = {s["symbol"] for s in page1["stocks"]}
    syms2 = {s["symbol"] for s in page2["stocks"]}
    # Different pages should not overlap
    assert not (syms1 & syms2)


def test_get_universe_counts_independent_of_pagination():
    load_tier_a()
    a = get_universe(tier=["A"], limit=10)
    b = get_universe(tier=["A"], limit=200)
    # Counts are over the whole universe, not the paginated result
    assert a["counts"] == b["counts"]


# ── /universe endpoint ─────────────────────────────────────────────


def test_universe_endpoint_smoke():
    init_db()
    load_tier_a()
    client = TestClient(app)
    r = client.get("/universe?tier=A&limit=20")
    assert r.status_code == 200
    payload = r.json()
    assert "stocks" in payload
    assert "counts" in payload
    assert payload["counts"]["A"] >= 100
    assert all(s["tier"] == "A" for s in payload["stocks"])


def test_universe_endpoint_industry_filter_returns_only_that_industry():
    init_db()
    load_tier_a()
    client = TestClient(app)
    r = client.get("/universe?industry=Semiconductors&limit=100")
    assert r.status_code == 200
    syms = {s["symbol"] for s in r.json()["stocks"]}
    assert "NVDA" in syms


def test_universe_endpoint_rejects_invalid_limit():
    client = TestClient(app)
    r = client.get("/universe?limit=0")
    assert r.status_code == 422   # FastAPI validation
