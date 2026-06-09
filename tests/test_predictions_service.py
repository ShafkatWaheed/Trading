"""Tests for the daily top-10 gainers predictions service.

Phase 1 scope — schema bootstrap, baseline strategy auto-insert, idempotent
generate, read-only fetch. Phase 2/3 (actuals + Claude adaptation) covered
by separate test files when those land.

Uses the temp DB via tests/conftest.py — production trading.db untouched.
Synthetic symbols only.
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from api.services import predictions_service
from src.utils.db import get_connection, init_db


# ── helpers ──────────────────────────────────────────────────────────


def _seed_tier_a_synthetic(symbols: list[str]) -> None:
    """Insert synthetic Tier A symbols so the universe loader returns them.

    Source='test' keeps them scoped-cleanable per CLAUDE.md rule 4.
    """
    init_db()
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM stocks_universe WHERE source = 'test' "
            "AND symbol LIKE 'SYN_%'"
        )
        for sym in symbols:
            conn.execute(
                """
                INSERT OR REPLACE INTO stocks_universe
                  (symbol, name, tier, exchange, source)
                VALUES (?, ?, 'A', 'TEST', 'test')
                """,
                (sym, f"Synthetic {sym}"),
            )
        conn.commit()
    finally:
        conn.close()


def _fake_history(values: list[float]) -> pd.DataFrame:
    """Build a fake daily-close DataFrame with len(values) bars."""
    return pd.DataFrame({"Close": values})


@pytest.fixture(autouse=True)
def _clean_predictions_tables():
    """Wipe predictions + strategies + synthetic universe rows before each
    test. Scoping the universe wipe to source='test' satisfies the
    CLAUDE.md rule about NEVER touching production-sourced rows."""
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM daily_predictions")
    conn.execute("DELETE FROM daily_prediction_actuals")
    conn.execute("DELETE FROM prediction_strategies")
    conn.execute("DELETE FROM stocks_universe WHERE source = 'test'")
    conn.commit()
    conn.close()


# ── strategy bootstrap ───────────────────────────────────────────────


def test_get_active_strategy_bootstraps_baseline():
    strat = predictions_service.get_active_strategy()
    assert strat["version"] == 1
    assert strat["name"] == "5d_momentum_v1"
    assert strat["config"]["lookback_days"] == 5
    assert strat["config"]["top_n"] == 10


def test_active_strategy_is_idempotent():
    """Calling twice must NOT insert a second baseline row."""
    a = predictions_service.get_active_strategy()
    b = predictions_service.get_active_strategy()
    assert a["version"] == b["version"]
    init_db()
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) AS n FROM prediction_strategies").fetchone()["n"]
    conn.close()
    assert n == 1


# ── universe loader ─────────────────────────────────────────────────


def test_load_universe_returns_tier_a_symbols():
    _seed_tier_a_synthetic(["SYN_AAA", "SYN_BBB", "SYN_CCC"])
    symbols = predictions_service._load_universe("A")
    assert set(symbols) >= {"SYN_AAA", "SYN_BBB", "SYN_CCC"}


# ── scoring + ranking ────────────────────────────────────────────────


def test_score_one_computes_5d_change():
    """Synthetic price series: 100 → 110 over 5 days should score +10%."""
    hist = _fake_history([100, 102, 105, 108, 109, 110])
    with patch.object(predictions_service.DataGateway, "get_historical", return_value=hist):
        out = predictions_service._score_one("SYN_X", lookback_days=5, min_history_days=6)
    assert out is not None
    assert out["symbol"] == "SYN_X"
    assert abs(out["score"] - 10.0) < 0.01
    assert "10.0%" in out["reasoning"]


def test_score_one_handles_missing_data():
    """If get_historical returns too few bars, score returns None."""
    hist = _fake_history([100, 101])    # only 2 bars
    with patch.object(predictions_service.DataGateway, "get_historical", return_value=hist):
        out = predictions_service._score_one("SYN_X", lookback_days=5, min_history_days=6)
    assert out is None


def test_score_one_handles_zero_prior_price():
    """Defensive: prior price = 0 must not crash (no /0)."""
    hist = _fake_history([0, 1, 2, 3, 4, 5])
    with patch.object(predictions_service.DataGateway, "get_historical", return_value=hist):
        out = predictions_service._score_one("SYN_X", lookback_days=5, min_history_days=6)
    assert out is None


# ── generate + idempotency ──────────────────────────────────────────


def test_generate_picks_top_10_by_momentum():
    """Higher 5d % return symbols rank higher."""
    _seed_tier_a_synthetic([f"SYN_{i}" for i in range(15)])

    # Each SYN_i: 5d return = i% (SYN_14 highest, SYN_0 flat)
    def _fake_get_historical(self, symbol, period_days=180):
        i = int(symbol.split("_")[1])
        # Build history: prior_5d = 100, today = 100 + i
        return _fake_history([100, 100, 100, 100, 100, 100 + i])

    with patch.object(predictions_service.DataGateway, "get_historical", _fake_get_historical):
        out = predictions_service.generate_predictions_for_date("2026-06-09", force=True)

    assert len(out["picks"]) == 10
    assert out["picks"][0]["symbol"] == "SYN_14"   # highest momentum
    assert out["picks"][9]["symbol"] == "SYN_5"    # 10th-highest
    # Ranks must be 1..10 in order
    assert [p["rank"] for p in out["picks"]] == list(range(1, 11))
    # All picks share the same strategy version (whatever the active one is).
    # Don't hard-code "==1" since SQLite AUTOINCREMENT survives DELETE across
    # tests and the counter may be higher on later runs.
    versions = {p["strategy_version"] for p in out["picks"]}
    assert len(versions) == 1
    assert next(iter(versions)) == out["strategy_version"]


def test_generate_is_idempotent_without_force():
    """Second call returns the first call's results — no re-scoring."""
    _seed_tier_a_synthetic([f"SYN_{i}" for i in range(11)])

    def _fake_get_historical(self, symbol, period_days=180):
        i = int(symbol.split("_")[1])
        return _fake_history([100, 100, 100, 100, 100, 100 + i])

    with patch.object(predictions_service.DataGateway, "get_historical", _fake_get_historical):
        first = predictions_service.generate_predictions_for_date("2026-06-09")

    # Second call: gateway should NOT be called. Patch to raise to confirm.
    def _explode(self, symbol, period_days=180):
        raise AssertionError("gateway re-invoked despite existing predictions")

    with patch.object(predictions_service.DataGateway, "get_historical", _explode):
        second = predictions_service.generate_predictions_for_date("2026-06-09")

    assert [p["symbol"] for p in first["picks"]] == [p["symbol"] for p in second["picks"]]


def test_force_regenerates_predictions():
    """force=True must re-score even when a row already exists."""
    _seed_tier_a_synthetic(["SYN_A", "SYN_B"])

    def _v1(self, symbol, period_days=180):
        # SYN_A wins
        if symbol == "SYN_A":
            return _fake_history([100, 100, 100, 100, 100, 120])
        return _fake_history([100, 100, 100, 100, 100, 105])

    with patch.object(predictions_service.DataGateway, "get_historical", _v1):
        first = predictions_service.generate_predictions_for_date("2026-06-09")
    assert first["picks"][0]["symbol"] == "SYN_A"

    # Force regenerate with SYN_B now winning
    def _v2(self, symbol, period_days=180):
        if symbol == "SYN_B":
            return _fake_history([100, 100, 100, 100, 100, 130])
        return _fake_history([100, 100, 100, 100, 100, 105])

    with patch.object(predictions_service.DataGateway, "get_historical", _v2):
        second = predictions_service.generate_predictions_for_date("2026-06-09", force=True)
    assert second["picks"][0]["symbol"] == "SYN_B"


def test_empty_universe_returns_no_picks_without_crashing():
    """If Tier A is empty, return cleanly — don't crash."""
    out = predictions_service.generate_predictions_for_date("2026-06-09", force=True)
    assert out["picks"] == []
    assert out["universe_size"] == 0


def test_get_predictions_for_date_returns_empty_on_miss():
    assert predictions_service.get_predictions_for_date("1999-01-01")["picks"] == []
