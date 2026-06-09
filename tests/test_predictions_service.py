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


# ── Phase 2: actuals + accuracy ─────────────────────────────────────


def _seed_actuals(date: str, picks_with_ranks: list[tuple[str, int, float]],
                  universe_size: int = 100) -> None:
    """Insert daily_prediction_actuals rows directly.

    Each tuple: (symbol, universe_rank, change_pct). Saves wiring real
    historical-bar mocks for every actuals test.
    """
    init_db()
    conn = get_connection()
    try:
        for sym, rank, change in picks_with_ranks:
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_prediction_actuals
                  (prediction_date, symbol, open_price, close_price,
                   change_pct, universe_rank, universe_size, recorded_at)
                VALUES (?, ?, 100.0, ?, ?, ?, ?, datetime('now'))
                """,
                (date, sym, 100.0 + change, change, rank, universe_size),
            )
        conn.commit()
    finally:
        conn.close()


def _seed_predictions_directly(date: str, picks: list[tuple[str, int]],
                                strategy_version: int) -> None:
    """Insert daily_predictions rows directly. Tuple: (symbol, rank)."""
    init_db()
    conn = get_connection()
    try:
        for sym, rank in picks:
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_predictions
                  (prediction_date, rank, symbol, score, reasoning,
                   strategy_version, created_at)
                VALUES (?, ?, ?, 0, '', ?, datetime('now'))
                """,
                (date, rank, sym, strategy_version),
            )
        conn.commit()
    finally:
        conn.close()


def test_get_predictions_with_actuals_includes_open_close_and_rank():
    strat = predictions_service.get_active_strategy()
    _seed_predictions_directly("2026-06-08", [("SYN_X", 1), ("SYN_Y", 2)], strat["version"])
    _seed_actuals("2026-06-08", [
        ("SYN_X", 7, 4.2),    # ranked 7th in universe with +4.2% return
        ("SYN_Y", 88, -1.1),
    ])

    out = predictions_service.get_predictions_with_actuals("2026-06-08")
    assert out["actuals_present"] is True
    syms = {p["symbol"]: p for p in out["picks"]}
    assert syms["SYN_X"]["universe_rank"] == 7
    assert abs(syms["SYN_X"]["actual_change_pct"] - 4.2) < 0.001
    assert syms["SYN_Y"]["universe_rank"] == 88


def test_get_predictions_with_actuals_handles_missing_actuals():
    """Picks without an actuals row get None values, not crashes."""
    strat = predictions_service.get_active_strategy()
    _seed_predictions_directly("2026-06-08", [("SYN_X", 1)], strat["version"])

    out = predictions_service.get_predictions_with_actuals("2026-06-08")
    assert out["actuals_present"] is False
    assert out["picks"][0]["universe_rank"] is None
    assert out["picks"][0]["actual_change_pct"] is None


def test_accuracy_window_computes_hit_rate():
    """3 days × 2 picks each; hit_threshold=25. Pin both counts and per-strategy
    breakdown."""
    strat = predictions_service.get_active_strategy()
    for d in ["2026-06-05", "2026-06-06", "2026-06-07"]:
        _seed_predictions_directly(d, [("SYN_A", 1), ("SYN_B", 2)], strat["version"])
    # Day 1: both hit (rank 5, 20)
    # Day 2: one hit, one miss (rank 10, 50)
    # Day 3: both miss (rank 80, 90)
    _seed_actuals("2026-06-05", [("SYN_A", 5, 3.1), ("SYN_B", 20, 2.0)])
    _seed_actuals("2026-06-06", [("SYN_A", 10, 1.5), ("SYN_B", 50, -0.5)])
    _seed_actuals("2026-06-07", [("SYN_A", 80, -2.0), ("SYN_B", 90, -3.1)])

    acc = predictions_service.get_accuracy_window(window_days=10, hit_threshold=25)
    assert acc["predictions_total"] == 6
    assert acc["hits"] == 3            # day1 both + day2 SYN_A
    assert abs(acc["hit_rate"] - 0.5) < 0.001
    assert acc["days_evaluated"] == 3
    assert strat["version"] in acc["by_strategy"]
    assert acc["by_strategy"][strat["version"]]["hits"] == 3


def test_accuracy_window_only_counts_completed_predictions():
    """Predictions WITHOUT an actuals row must not appear in totals."""
    strat = predictions_service.get_active_strategy()
    # 2 days predicted; only one has actuals
    _seed_predictions_directly("2026-06-05", [("SYN_A", 1)], strat["version"])
    _seed_predictions_directly("2026-06-06", [("SYN_A", 1)], strat["version"])
    _seed_actuals("2026-06-05", [("SYN_A", 3, 5.0)])

    acc = predictions_service.get_accuracy_window(window_days=30)
    assert acc["predictions_total"] == 1
    assert acc["hits"] == 1
    assert acc["days_evaluated"] == 1


def test_accuracy_window_hit_threshold_tunable():
    """Tightening the threshold reduces hits without recomputing actuals."""
    strat = predictions_service.get_active_strategy()
    _seed_predictions_directly("2026-06-05", [("SYN_A", 1), ("SYN_B", 2)], strat["version"])
    _seed_actuals("2026-06-05", [("SYN_A", 10, 5.0), ("SYN_B", 30, 4.0)])

    loose = predictions_service.get_accuracy_window(window_days=30, hit_threshold=50)
    tight = predictions_service.get_accuracy_window(window_days=30, hit_threshold=15)
    assert loose["hits"] == 2     # both within rank 50
    assert tight["hits"] == 1     # only SYN_A within rank 15


# ── Phase 3b: strategy adaptation ───────────────────────────────────


def test_validate_proposed_strategy_accepts_valid_change_5d():
    out = predictions_service._validate_proposed_strategy({
        "name": "test-v2",
        "description": "trying a longer window",
        "config": {
            "ranking_signal":   "change_5d",
            "lookback_days":    5,
            "top_n":            10,
            "universe_tier":    "A",
            "min_history_days": 7,
        },
    })
    assert out is not None
    assert out["config"]["ranking_signal"] == "change_5d"
    assert out["config"]["lookback_days"] == 5   # pinned to signal
    assert out["config"]["min_history_days"] == 6   # pinned to lookback + 1


def test_validate_pins_lookback_to_signal():
    """Claude says signal=change_20d but lookback=3 — must pin to 20."""
    out = predictions_service._validate_proposed_strategy({
        "name": "test",
        "description": "x",
        "config": {
            "ranking_signal":   "change_20d",
            "lookback_days":    3,           # inconsistent
            "top_n":            10,
            "universe_tier":    "A",
        },
    })
    assert out is not None
    assert out["config"]["lookback_days"] == 20
    assert out["config"]["min_history_days"] == 21


def test_validate_rejects_unknown_signal():
    """Claude inventing a signal we can't compute must be rejected."""
    out = predictions_service._validate_proposed_strategy({
        "name": "made_up",
        "description": "VIX cross-correlated with the moon phase",
        "config": {
            "ranking_signal": "vix_moon_cross",
            "top_n": 10,
        },
    })
    assert out is None


def test_validate_rejects_missing_required_fields():
    assert predictions_service._validate_proposed_strategy(None) is None
    assert predictions_service._validate_proposed_strategy({}) is None
    assert predictions_service._validate_proposed_strategy({
        "name": "",
        "description": "blah",
        "config": {"ranking_signal": "change_5d"},
    }) is None    # empty name


def test_validate_rejects_non_tier_a():
    """V1 only supports Tier A. A Tier B proposal must be rejected."""
    out = predictions_service._validate_proposed_strategy({
        "name": "test",
        "description": "trying Tier B",
        "config": {
            "ranking_signal": "change_5d",
            "universe_tier": "B",
        },
    })
    assert out is None


def test_review_returns_no_proposal_when_no_history():
    """No completed predictions in window → no_completed_predictions_in_window."""
    out = predictions_service.review_and_propose_strategy(window_days=14)
    assert out["proposed"] is False
    assert out["reason"] == "no_completed_predictions_in_window"


def test_review_invokes_claude_and_persists_valid_proposal():
    """End-to-end: history exists → Claude returns a valid JSON proposal →
    a new (deactivated) strategy row is inserted."""
    strat = predictions_service.get_active_strategy()
    _seed_predictions_directly("2026-06-05", [("SYN_A", 1), ("SYN_B", 2)], strat["version"])
    _seed_actuals("2026-06-05", [("SYN_A", 10, 5.0), ("SYN_B", 30, 4.0)])

    fake_proposal = {
        "name": "change_20d_v1",
        "description": "20-day momentum looks more durable in the recent record",
        "config": {
            "ranking_signal":   "change_20d",
            "lookback_days":    20,
            "top_n":            10,
            "universe_tier":    "A",
            "min_history_days": 21,
        },
    }
    with patch.object(predictions_service, "ask_claude_json", return_value=fake_proposal):
        out = predictions_service.review_and_propose_strategy(window_days=14)

    assert out["proposed"] is True
    assert out["proposal"]["name"] == "change_20d_v1"
    assert out["proposal"]["version"] > strat["version"]
    # New row exists and is INACTIVE (deactivated_at IS NULL is what marks
    # active — but the inserted row has activated_at NULL too, so it's
    # neither active nor formally deactivated yet; activate() will set both).
    strategies = predictions_service.list_strategies()
    new = [s for s in strategies if s["version"] == out["proposal"]["version"]][0]
    assert new["is_active"] is False


def test_review_handles_claude_invalid_response():
    """Claude returns something that doesn't parse to a valid proposal —
    reason is surfaced, no row is inserted."""
    strat = predictions_service.get_active_strategy()
    _seed_predictions_directly("2026-06-05", [("SYN_A", 1)], strat["version"])
    _seed_actuals("2026-06-05", [("SYN_A", 10, 5.0)])

    with patch.object(predictions_service, "ask_claude_json", return_value={"garbage": "no config"}):
        out = predictions_service.review_and_propose_strategy(window_days=14)

    assert out["proposed"] is False
    assert out["reason"] == "claude_proposal_invalid_or_missing"
    # No new strategy row inserted
    strategies = predictions_service.list_strategies()
    assert len(strategies) == 1
    assert strategies[0]["version"] == strat["version"]


def test_activate_strategy_switches_active_row():
    """Activating a new version deactivates the previous active one."""
    old_strat = predictions_service.get_active_strategy()
    # Manually insert a second strategy
    init_db()
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO prediction_strategies
          (name, description, config_json, created_at)
        VALUES ('test_v2', 'a test', '{"ranking_signal":"change_20d","lookback_days":20,"top_n":10,"universe_tier":"A","min_history_days":21}', datetime('now'))
        """
    )
    new_version = int(cur.lastrowid)
    conn.commit()
    conn.close()

    res = predictions_service.activate_strategy(new_version)
    assert res["activated"] is True

    # Old active row is now deactivated
    strategies = predictions_service.list_strategies()
    by_v = {s["version"]: s for s in strategies}
    assert by_v[old_strat["version"]]["is_active"] is False
    assert by_v[old_strat["version"]]["deactivated_at"] is not None
    assert by_v[new_version]["is_active"] is True


def test_activate_unknown_version_returns_not_found():
    res = predictions_service.activate_strategy(999_999)
    assert res["activated"] is False
    assert res["reason"] == "version_not_found"


def test_activate_already_active_is_noop():
    strat = predictions_service.get_active_strategy()
    res = predictions_service.activate_strategy(strat["version"])
    assert res["activated"] is True
    assert res.get("no_op") is True


# ── Phase 4: composite_v1 pulse-aware scoring ───────────────────────


def _seed_industry(symbol: str, sector: str, industry_code: str | None = None) -> None:
    """Insert a synthetic industry mapping for `symbol`."""
    code = industry_code or f"TEST_IND_{sector.upper().replace(' ', '_')}"
    init_db()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO industries (code, sector) VALUES (?, ?)",
            (code, sector),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO stock_industry
              (symbol, industry_code, weight, is_primary, source)
            VALUES (?, ?, 1.0, 1, 'test')
            """,
            (symbol, code),
        )
        conn.commit()
    finally:
        conn.close()


def test_score_one_composite_uses_sector_match():
    """Two symbols with identical 5d momentum: the one in a pulse-top sector
    must score higher."""
    pulse = {
        "regime":            "bull",
        "top_sectors":       ["Technology"],
        "top_sectors_flow":  {"Technology": 2.5},
        "all_sector_flows":  {"Technology": 2.5, "Energy": -1.0},
    }
    hist = _fake_history([100, 100, 100, 100, 100, 105])    # +5% over 5d

    with patch.object(predictions_service.DataGateway, "get_historical", return_value=hist):
        in_top = predictions_service._score_one(
            "SYN_TECH",
            lookback_days=5, min_history_days=6,
            signal="composite_v1", pulse=pulse, sector="Technology",
        )
        out_of_top = predictions_service._score_one(
            "SYN_ENERGY",
            lookback_days=5, min_history_days=6,
            signal="composite_v1", pulse=pulse, sector="Energy",
        )

    assert in_top is not None and out_of_top is not None
    assert in_top["score"] > out_of_top["score"]
    assert in_top["components"]["sector_match"] is True
    assert out_of_top["components"]["sector_match"] is False


def test_score_one_composite_handles_unknown_sector():
    """If symbol has no sector mapping, sector_match defaults to 0 without
    crashing."""
    pulse = {
        "regime": "bull", "top_sectors": ["Technology"],
        "top_sectors_flow": {"Technology": 1.0},
        "all_sector_flows": {"Technology": 1.0},
    }
    hist = _fake_history([100, 100, 100, 100, 100, 110])
    with patch.object(predictions_service.DataGateway, "get_historical", return_value=hist):
        out = predictions_service._score_one(
            "SYN_X",
            lookback_days=5, min_history_days=6,
            signal="composite_v1", pulse=pulse, sector=None,
        )
    assert out is not None
    assert out["components"]["sector_match"] is False


def test_score_one_change_signal_ignores_pulse():
    """change_Nd strategies must not be affected by pulse args even when
    passed — keeps the baseline truly pulse-independent."""
    pulse = {
        "regime": "bull", "top_sectors": ["Technology"],
        "top_sectors_flow": {"Technology": 5.0},
        "all_sector_flows": {"Technology": 5.0},
    }
    hist = _fake_history([100, 100, 100, 100, 100, 110])
    with patch.object(predictions_service.DataGateway, "get_historical", return_value=hist):
        a = predictions_service._score_one(
            "SYN_X",
            lookback_days=5, min_history_days=6,
            signal="change_5d", pulse=pulse, sector="Technology",
        )
        b = predictions_service._score_one(
            "SYN_X",
            lookback_days=5, min_history_days=6,
            signal="change_5d", pulse={}, sector=None,
        )
    assert a is not None and b is not None
    assert abs(a["score"] - b["score"]) < 0.001


def test_symbol_sectors_bulk_load():
    _seed_industry("SYN_A", "Technology")
    _seed_industry("SYN_B", "Energy")

    out = predictions_service._symbol_sectors(["SYN_A", "SYN_B", "SYN_NEVER_SEEN"])
    assert out == {"SYN_A": "Technology", "SYN_B": "Energy"}


def test_generate_attaches_pulse_context():
    """The payload returned by generate must include the pulse_context
    that was used during scoring."""
    _seed_tier_a_synthetic(["SYN_X"])

    def _fake_get_historical(self, symbol, period_days=180):
        return _fake_history([100, 100, 100, 100, 100, 110])

    fake_pulse = {
        "regime": "bull",
        "top_sectors": ["Technology"],
        "top_sectors_flow": {"Technology": 2.0},
        "all_sector_flows": {"Technology": 2.0},
    }
    with patch.object(predictions_service.DataGateway, "get_historical", _fake_get_historical), \
         patch.object(predictions_service, "_pulse_context", return_value=fake_pulse):
        out = predictions_service.generate_predictions_for_date("2026-06-09", force=True)

    assert out["pulse_context"] == fake_pulse


def test_validate_composite_v1_sanitizes_weights():
    """Weights outside [0,1] get clipped; non-numeric falls back to defaults."""
    out = predictions_service._validate_proposed_strategy({
        "name": "composite-test",
        "description": "trying composite",
        "config": {
            "ranking_signal": "composite_v1",
            "lookback_days": 5,
            "top_n": 10,
            "universe_tier": "A",
            "weights": {
                "momentum":     1.5,       # too high → 1.0
                "sector_match": -0.2,      # too low → 0.0
                "sector_flow":  "bad",     # not a number → default 0.2
            },
        },
    })
    assert out is not None
    w = out["config"]["weights"]
    assert w["momentum"] == 1.0
    assert w["sector_match"] == 0.0
    assert abs(w["sector_flow"] - 0.2) < 0.001


def test_validate_composite_v1_with_no_weights_uses_defaults():
    out = predictions_service._validate_proposed_strategy({
        "name": "composite-default",
        "description": "no weights specified",
        "config": {
            "ranking_signal": "composite_v1",
            "lookback_days": 5,
            "top_n": 10,
            "universe_tier": "A",
        },
    })
    assert out is not None
    w = out["config"]["weights"]
    assert w["momentum"] == 0.5
    assert w["sector_match"] == 0.3
    assert w["sector_flow"] == 0.2
    # Phase 5 weights default to 0
    assert w["bubble"] == 0.0
    assert w["analyst"] == 0.0
    assert w["congress"] == 0.0


# ── Phase 5: cached per-symbol signals (bubble, analyst, congress) ───


def _seed_cache(key: str, value: object, ttl_minutes: int = 60) -> None:
    """Insert a cache row directly so the bulk-load helpers see it."""
    from src.utils.db import cache_set
    cache_set(key, value, ttl_minutes=ttl_minutes)


def test_bulk_bubble_signals_maps_labels_correctly():
    _seed_cache("bubble_score:v1:SYN_HOT",   {"label": "Overheated", "score": 90})
    _seed_cache("bubble_score:v1:SYN_FAIR",  {"label": "Fair Value", "score": 50})
    _seed_cache("bubble_score:v1:SYN_CHEAP", {"label": "Undervalued","score": 20})

    out = predictions_service._bulk_bubble_signals(["SYN_HOT", "SYN_FAIR", "SYN_CHEAP", "SYN_MISSING"])
    assert out["SYN_HOT"] == -1.0
    assert out["SYN_FAIR"] == 0.0
    assert out["SYN_CHEAP"] == 1.0
    assert "SYN_MISSING" not in out


def test_bulk_analyst_revisions_clipped_to_unit_range():
    _seed_cache("estimate_revisions:v1:SYN_UP",    {"net_change_30d": 7})    # → 0.7
    _seed_cache("estimate_revisions:v1:SYN_HUGE",  {"net_change_30d": 25})   # clipped → 1.0
    _seed_cache("estimate_revisions:v1:SYN_DOWN",  {"net_change_30d": -15})  # clipped → -1.0
    _seed_cache("estimate_revisions:v1:SYN_NONE",  {"net_change_30d": None})

    out = predictions_service._bulk_analyst_revisions(["SYN_UP", "SYN_HUGE", "SYN_DOWN", "SYN_NONE"])
    assert abs(out["SYN_UP"] - 0.7) < 0.001
    assert out["SYN_HUGE"] == 1.0
    assert out["SYN_DOWN"] == -1.0
    assert "SYN_NONE" not in out


def test_bulk_congress_buys_uses_30d_window():
    """Recent buys are flagged; old buys and sells are not."""
    from datetime import datetime, timedelta, timezone
    init_db()
    conn = get_connection()
    today = datetime.now(tz=timezone.utc).date()
    recent = (today - timedelta(days=10)).isoformat()
    old    = (today - timedelta(days=200)).isoformat()
    conn.executescript("DELETE FROM congress_trades WHERE filing_uuid LIKE 'test-%';")
    rows = [
        ("test-1", 0, "House", "Test Rep A", "D", "ST", "TX", None, "SYN_RECENT_BUY",
         "ST", "buy", recent, recent, 1000, 5000, "{}", "test"),
        ("test-2", 0, "House", "Test Rep B", "R", "ST", "FL", None, "SYN_OLD_BUY",
         "ST", "buy", old, old, 1000, 5000, "{}", "test"),
        ("test-3", 0, "House", "Test Rep C", "D", "ST", "NY", None, "SYN_SELL",
         "ST", "sell", recent, recent, 1000, 5000, "{}", "test"),
    ]
    for r in rows:
        conn.execute(
            "INSERT INTO congress_trades "
            "(filing_uuid, txn_index, chamber, politician_name, party, state, bioguide_id, asset_type, ticker, "
            " asset_type, transaction_type, transaction_date, filing_date, amount_low, amount_high, raw_text, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            r,
        )
    conn.commit()
    conn.close()

    out = predictions_service._bulk_congress_buys(
        ["SYN_RECENT_BUY", "SYN_OLD_BUY", "SYN_SELL", "SYN_NEVER_TRADED"]
    )
    assert out == {"SYN_RECENT_BUY": 1.0}


def test_composite_uses_bubble_signal_with_nonzero_weight():
    """When bubble weight > 0, an undervalued symbol outranks an overheated one
    with identical momentum + sector profile."""
    pulse = {
        "regime": "neutral",
        "top_sectors": [],
        "top_sectors_flow": {},
        "all_sector_flows": {},
    }
    hist = _fake_history([100, 100, 100, 100, 100, 102])    # +2% momentum
    weights = {"momentum": 0.5, "sector_match": 0.0, "sector_flow": 0.0,
               "bubble": 0.5, "analyst": 0.0, "congress": 0.0}

    with patch.object(predictions_service.DataGateway, "get_historical", return_value=hist):
        cheap = predictions_service._score_one(
            "SYN_CHEAP",
            lookback_days=5, min_history_days=6,
            signal="composite_v1", pulse=pulse, sector=None,
            weights=weights, bubble_signal=1.0,
        )
        hot = predictions_service._score_one(
            "SYN_HOT",
            lookback_days=5, min_history_days=6,
            signal="composite_v1", pulse=pulse, sector=None,
            weights=weights, bubble_signal=-1.0,
        )

    assert cheap is not None and hot is not None
    assert cheap["score"] > hot["score"]


def test_composite_uses_analyst_signal():
    pulse = {"regime": "neutral", "top_sectors": [], "top_sectors_flow": {}, "all_sector_flows": {}}
    hist = _fake_history([100, 100, 100, 100, 100, 102])
    weights = {"momentum": 0.5, "sector_match": 0.0, "sector_flow": 0.0,
               "bubble": 0.0, "analyst": 0.5, "congress": 0.0}

    with patch.object(predictions_service.DataGateway, "get_historical", return_value=hist):
        upgraded = predictions_service._score_one(
            "SYN_UP",
            lookback_days=5, min_history_days=6,
            signal="composite_v1", pulse=pulse, sector=None,
            weights=weights, analyst_signal=1.0,
        )
        flat = predictions_service._score_one(
            "SYN_FLAT",
            lookback_days=5, min_history_days=6,
            signal="composite_v1", pulse=pulse, sector=None,
            weights=weights, analyst_signal=0.0,
        )

    assert upgraded["score"] > flat["score"]


def test_composite_uses_congress_signal():
    pulse = {"regime": "neutral", "top_sectors": [], "top_sectors_flow": {}, "all_sector_flows": {}}
    hist = _fake_history([100, 100, 100, 100, 100, 102])
    weights = {"momentum": 0.5, "sector_match": 0.0, "sector_flow": 0.0,
               "bubble": 0.0, "analyst": 0.0, "congress": 0.5}

    with patch.object(predictions_service.DataGateway, "get_historical", return_value=hist):
        bought = predictions_service._score_one(
            "SYN_HILL",
            lookback_days=5, min_history_days=6,
            signal="composite_v1", pulse=pulse, sector=None,
            weights=weights, congress_signal=1.0,
        )
        plain = predictions_service._score_one(
            "SYN_NORM",
            lookback_days=5, min_history_days=6,
            signal="composite_v1", pulse=pulse, sector=None,
            weights=weights, congress_signal=0.0,
        )

    assert bought["score"] > plain["score"]


# ── Phase 6: Playbook (skills.md) ────────────────────────────────────


@pytest.fixture
def _isolated_skills(tmp_path, monkeypatch):
    """Redirect _SKILLS_PATH to a per-test temp file so tests don't touch
    the real data/predictions/skills.md."""
    monkeypatch.setattr(
        predictions_service, "_SKILLS_PATH", tmp_path / "skills.md"
    )
    return tmp_path / "skills.md"


def test_ensure_skills_file_creates_template(_isolated_skills):
    p = predictions_service._ensure_skills_file()
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert predictions_service._SKILLS_VERSION_TAG in content
    assert "Prediction Playbook" in content
    assert "Active patterns" in content


def test_read_skills_returns_template_on_first_read(_isolated_skills):
    content = predictions_service._read_skills()
    assert predictions_service._SKILLS_VERSION_TAG in content


def test_write_skills_round_trip(_isolated_skills):
    new = predictions_service._SKILLS_VERSION_TAG + "\n# Custom playbook\n_Last updated: 2026-06-09_\n"
    predictions_service._write_skills(new)
    assert predictions_service._read_skills() == new


def test_get_skills_returns_metadata(_isolated_skills):
    out = predictions_service.get_skills()
    assert "content" in out
    assert "last_updated" in out
    assert "path" in out
    assert predictions_service._SKILLS_VERSION_TAG in out["content"]


def test_update_skills_returns_reason_when_no_history(_isolated_skills):
    out = predictions_service.update_prediction_skills(window_days=30)
    assert out["updated"] is False
    assert out["reason"] == "no_completed_predictions_in_window"


def test_update_skills_writes_claude_response(_isolated_skills):
    """End-to-end: history exists → Claude returns valid markdown → file
    gets rewritten with the new content."""
    strat = predictions_service.get_active_strategy()
    _seed_predictions_directly("2026-06-05", [("SYN_A", 1)], strat["version"])
    _seed_actuals("2026-06-05", [("SYN_A", 8, 4.2)])

    new_content = (
        predictions_service._SKILLS_VERSION_TAG +
        "\n# Updated playbook\n\n"
        "## Active patterns\n- 1/1 picks hit top-25 in bull regime\n\n"
        "_Last updated: 2026-06-09_\n"
    )
    with patch.object(predictions_service, "ask_claude_json", return_value=new_content):
        out = predictions_service.update_prediction_skills(window_days=30)

    assert out["updated"] is True
    assert "Updated playbook" in predictions_service._read_skills()


def test_update_skills_rejects_response_missing_version_tag(_isolated_skills):
    """Defensive: if Claude doesn't return the version tag, we leave the
    existing playbook intact rather than overwriting with junk."""
    strat = predictions_service.get_active_strategy()
    _seed_predictions_directly("2026-06-05", [("SYN_A", 1)], strat["version"])
    _seed_actuals("2026-06-05", [("SYN_A", 8, 4.2)])

    original = predictions_service._read_skills()
    bad_response = "# No version tag here\nblah blah"
    with patch.object(predictions_service, "ask_claude_json", return_value=bad_response), \
         patch("src.utils.claude_cli.ask_claude", return_value=bad_response):
        out = predictions_service.update_prediction_skills(window_days=30)

    assert out["updated"] is False
    assert out["reason"] == "claude_response_missing_version_tag"
    # Playbook unchanged
    assert predictions_service._read_skills() == original


def test_update_skills_trims_preamble_before_version_tag(_isolated_skills):
    """Claude sometimes adds explanatory preamble despite being told not to.
    Trim it as long as the version tag is present somewhere in the response."""
    strat = predictions_service.get_active_strategy()
    _seed_predictions_directly("2026-06-05", [("SYN_A", 1)], strat["version"])
    _seed_actuals("2026-06-05", [("SYN_A", 8, 4.2)])

    response_with_preamble = (
        "Here's the new playbook:\n\n```markdown\n"
        + predictions_service._SKILLS_VERSION_TAG +
        "\n# Cleaned\n_Last updated: 2026-06-09_\n```"
    )
    with patch.object(predictions_service, "ask_claude_json", return_value=response_with_preamble):
        out = predictions_service.update_prediction_skills(window_days=30)

    assert out["updated"] is True
    saved = predictions_service._read_skills()
    assert saved.startswith(predictions_service._SKILLS_VERSION_TAG)
    assert "Cleaned" in saved
    # Preamble was trimmed
    assert "Here's the new playbook" not in saved


# ── Phase 7: full signal bundle ──────────────────────────────────────


def test_bulk_options_signals_maps_signal_field():
    _seed_cache("options_flow:v1:SYN_BULL", {"available": True, "signal": "bullish"})
    _seed_cache("options_flow:v1:SYN_BEAR", {"available": True, "signal": "bearish"})
    _seed_cache("options_flow:v1:SYN_NA",   {"available": False})

    out = predictions_service._bulk_options_signals(["SYN_BULL", "SYN_BEAR", "SYN_NA"])
    assert out["SYN_BULL"] == 1.0
    assert out["SYN_BEAR"] == -1.0
    assert "SYN_NA" not in out


def test_bulk_news_signals_clamps_net_sentiment():
    _seed_cache("news_feed:v1:SYN_POS",  {"net_sentiment": 0.7})
    _seed_cache("news_feed:v1:SYN_NEG",  {"net_sentiment": -0.4})
    _seed_cache("news_feed:v1:SYN_HOT",  {"net_sentiment": 1.6})    # clipped → 1.0

    out = predictions_service._bulk_news_signals(["SYN_POS", "SYN_NEG", "SYN_HOT"])
    assert abs(out["SYN_POS"] - 0.7) < 0.01
    assert abs(out["SYN_NEG"] - (-0.4)) < 0.01
    assert out["SYN_HOT"] == 1.0


def test_bulk_peer_valuation_signals_returns_discount():
    _seed_cache("peer_valuation:v1:SYN_CHEAP", {
        "rows": [{"is_self": True, "pe_ratio": 12.0}],
        "medians": {"pe_ratio": 20.0},   # 1 - 12/20 = 0.4 → cheap
    })
    _seed_cache("peer_valuation:v1:SYN_RICH", {
        "rows": [{"is_self": True, "pe_ratio": 40.0}],
        "medians": {"pe_ratio": 20.0},   # 1 - 40/20 = -1.0 → expensive (clipped)
    })

    out = predictions_service._bulk_peer_valuation_signals(["SYN_CHEAP", "SYN_RICH"])
    assert abs(out["SYN_CHEAP"] - 0.4) < 0.01
    assert out["SYN_RICH"] == -1.0


def test_bulk_catalyst_signals_only_counts_high_weight_within_horizon():
    _seed_cache("catalyst_calendar:v1:SYN_HIT", {
        "events": [
            {"days_out": 12, "weight": "high",   "title": "earnings"},
            {"days_out": 99, "weight": "high",   "title": "too far"},
        ],
    })
    _seed_cache("catalyst_calendar:v1:SYN_LOW", {
        "events": [{"days_out": 5, "weight": "low", "title": "investor day"}],
    })

    out = predictions_service._bulk_catalyst_signals(["SYN_HIT", "SYN_LOW"])
    assert out["SYN_HIT"] == 1.0
    assert out["SYN_LOW"] == 0.0


def test_bulk_recommendation_signals_maps_actions():
    _seed_cache("recommendation:v1:SYN_BUY",   {"action": "buy"})
    _seed_cache("recommendation:v1:SYN_HOLD",  {"action": "hold"})
    _seed_cache("recommendation:v1:SYN_SELL",  {"action": "sell"})
    _seed_cache("recommendation:v1:SYN_UNKW",  {"action": "weird"})

    out = predictions_service._bulk_recommendation_signals(
        ["SYN_BUY", "SYN_HOLD", "SYN_SELL", "SYN_UNKW"]
    )
    assert out["SYN_BUY"] == 1.0
    assert out["SYN_HOLD"] == 0.0
    assert out["SYN_SELL"] == -1.0
    assert "SYN_UNKW" not in out


def test_bulk_fundamentals_signals_centers_at_50():
    _seed_cache("fundamentals_story:v1:SYN_STRONG", {"available": True, "overall_score": 80})
    _seed_cache("fundamentals_story:v1:SYN_AVG",    {"available": True, "overall_score": 50})
    _seed_cache("fundamentals_story:v1:SYN_WEAK",   {"available": True, "overall_score": 20})

    out = predictions_service._bulk_fundamentals_signals(["SYN_STRONG", "SYN_AVG", "SYN_WEAK"])
    assert abs(out["SYN_STRONG"] - 0.6) < 0.01   # (80-50)/50
    assert out["SYN_AVG"] == 0.0
    assert abs(out["SYN_WEAK"] - (-0.6)) < 0.01


def test_bulk_all_signals_unions_each_source():
    """Single sym with rows in 3 different caches → bundle has all 3 keys."""
    _seed_cache("bubble_score:v1:SYN_X",       {"label": "Undervalued"})
    _seed_cache("news_feed:v1:SYN_X",          {"net_sentiment": 0.5})
    _seed_cache("recommendation:v1:SYN_X",     {"action": "buy"})

    bundle = predictions_service._bulk_all_signals(["SYN_X"])
    assert bundle["SYN_X"]["bubble"] == 1.0
    assert abs(bundle["SYN_X"]["news"] - 0.5) < 0.01
    assert bundle["SYN_X"]["recommendation"] == 1.0


def test_validate_composite_v1_includes_phase7_weights_with_zero_defaults():
    """All Phase 7 weights must be present in the cleaned config so the
    runtime _score_one never crashes on a missing key."""
    out = predictions_service._validate_proposed_strategy({
        "name": "composite-min",
        "description": "no weights",
        "config": {
            "ranking_signal": "composite_v1",
            "lookback_days": 5,
            "top_n": 10,
            "universe_tier": "A",
        },
    })
    w = out["config"]["weights"]
    for k in ("options", "news", "pre_earnings", "peer_valuation",
              "catalyst", "recommendation", "macro_fit",
              "analyst_consensus", "fundamentals"):
        assert k in w
        assert w[k] == 0.0


def test_score_one_uses_news_signal_with_nonzero_weight():
    """End-to-end: high news_signal weight + bullish news ranks higher than
    same-momentum stock with bearish news."""
    pulse = {"regime": "neutral", "top_sectors": [], "top_sectors_flow": {}, "all_sector_flows": {}}
    hist = _fake_history([100, 100, 100, 100, 100, 105])
    weights = {"momentum": 0.5, "news": 0.5}

    with patch.object(predictions_service.DataGateway, "get_historical", return_value=hist):
        good_news = predictions_service._score_one(
            "SYN_GOOD", lookback_days=5, min_history_days=6,
            signal="composite_v1", pulse=pulse, sector=None,
            weights=weights, news_signal=0.8,
        )
        bad_news = predictions_service._score_one(
            "SYN_BAD", lookback_days=5, min_history_days=6,
            signal="composite_v1", pulse=pulse, sector=None,
            weights=weights, news_signal=-0.8,
        )

    assert good_news["score"] > bad_news["score"]


def test_generate_persists_pulse_and_components_json():
    """Phase 6 schema: each pick row should store pulse_snapshot_json and
    components_json so the weekly playbook review has the macro context."""
    _seed_tier_a_synthetic(["SYN_X"])

    def _fake_get_historical(self, symbol, period_days=180):
        return _fake_history([100, 100, 100, 100, 100, 110])

    fake_pulse = {
        "regime": "bull",
        "top_sectors": ["Technology"],
        "top_sectors_flow": {"Technology": 2.0},
        "all_sector_flows": {"Technology": 2.0},
    }

    with patch.object(predictions_service.DataGateway, "get_historical", _fake_get_historical), \
         patch.object(predictions_service, "_pulse_context", return_value=fake_pulse):
        predictions_service.generate_predictions_for_date("2026-06-09", force=True)

    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT pulse_snapshot_json, components_json FROM daily_predictions "
        "WHERE prediction_date = '2026-06-09'"
    ).fetchone()
    conn.close()
    assert row is not None
    import json as _j
    pulse_back = _j.loads(row["pulse_snapshot_json"])
    assert pulse_back["regime"] == "bull"
    # Components is an empty {} for change_5d signal (it only fills for composite)
    assert row["components_json"] is not None


def test_phase5_signals_zero_by_default_in_composite():
    """With default weights, the new factors contribute 0 — composite_v1
    behaves exactly like the phase-4 momentum+sector recipe."""
    pulse = {"regime": "neutral", "top_sectors": [], "top_sectors_flow": {}, "all_sector_flows": {}}
    hist = _fake_history([100, 100, 100, 100, 100, 110])    # +10%

    with patch.object(predictions_service.DataGateway, "get_historical", return_value=hist):
        without = predictions_service._score_one(
            "SYN_X",
            lookback_days=5, min_history_days=6,
            signal="composite_v1", pulse=pulse, sector=None,
        )
        with_signals = predictions_service._score_one(
            "SYN_X",
            lookback_days=5, min_history_days=6,
            signal="composite_v1", pulse=pulse, sector=None,
            bubble_signal=1.0, analyst_signal=1.0, congress_signal=1.0,
        )
    # No weights passed → defaults apply, including 0 for phase-5 weights.
    # Without weights the new factors should not affect the score.
    assert abs(without["score"] - with_signals["score"]) < 0.001
