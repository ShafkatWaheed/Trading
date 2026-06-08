"""Unit tests for Quiver alt-data scorers (src.data.quiver_altdata).

Pure functions over synthetic rows — no network, no production DB.
"""
from src.data import quiver_altdata as A


# ── dark pool ───────────────────────────────────────────────────────────────

def _dp(date, short, total, dpi=0.4):
    return {"Date": date, "OTC_Short": short, "OTC_Total": total, "DPI": dpi}


def test_dark_pool_high_short_is_bearish():
    rows = [_dp(f"2026-05-{d:02d}", 65, 100) for d in range(1, 21)]
    out = A.score_dark_pool(rows)
    assert out["direction"] == "bearish"
    assert out["score"] == -1
    assert out["recent_short_pct"] == 65.0
    assert 0.2 <= out["strength"] <= 0.85


def test_dark_pool_low_short_is_bullish():
    rows = [_dp(f"2026-05-{d:02d}", 35, 100) for d in range(1, 21)]
    out = A.score_dark_pool(rows)
    assert out["direction"] == "bullish"
    assert out["score"] == 1


def test_dark_pool_normal_is_neutral_and_handles_zero_total():
    rows = [_dp(f"2026-05-{d:02d}", 50, 100) for d in range(1, 21)]
    rows.append(_dp("2026-05-21", 0, 0))  # zero-total row must not crash
    out = A.score_dark_pool(rows)
    assert out["direction"] == "neutral"
    assert out["score"] == 0


def test_dark_pool_empty_returns_none():
    assert A.score_dark_pool([]) is None
    assert A.score_dark_pool([_dp("2026-05-01", 0, 0)]) is None


# ── government contracts ─────────────────────────────────────────────────────

def _gc(year, qtr, amount):
    return {"Year": year, "Qtr": qtr, "Amount": amount}


def test_gov_contracts_growth_is_bullish():
    rows = [_gc(2024, q, 100) for q in range(1, 5)]          # prior 4q = 400
    rows += [_gc(2025, q, 200) for q in range(1, 5)]          # recent 4q = 800
    out = A.score_gov_contracts(rows)
    assert out["direction"] == "bullish"
    assert out["yoy_growth_pct"] == 100.0
    assert out["recent_4q_total"] == 800.0


def test_gov_contracts_decline_is_bearish():
    rows = [_gc(2024, q, 200) for q in range(1, 5)]          # prior = 800
    rows += [_gc(2025, q, 50) for q in range(1, 5)]           # recent = 200 (-75%)
    out = A.score_gov_contracts(rows)
    assert out["direction"] == "bearish"


def test_gov_contracts_no_history_suppressed():
    assert A.score_gov_contracts([]) is None
    assert A.score_gov_contracts([_gc(2025, 1, 0)]) is None


# ── lobbying (Tier 3, low strength, always neutral) ─────────────────────────

def test_lobbying_is_context_low_strength():
    rows = [
        {"Date": "2025-03-01", "Amount": 500000, "Issue": "Taxes"},
        {"Date": "2024-03-01", "Amount": 200000, "Issue": "Trade"},
    ]
    out = A.score_lobbying(rows)
    assert out["direction"] == "neutral"
    assert out["strength"] <= 0.35
    assert out["trend"] == "rising"
    assert "Taxes" in out["top_issues"]


def test_lobbying_empty_returns_none():
    assert A.score_lobbying([]) is None


# ── corporate flights (Tier 3, novelty) ─────────────────────────────────────

def test_flights_low_strength_and_routes():
    rows = [
        {"Date": "2026-05-01", "DepartureCity": "Austin", "ArrivalCity": "Reno"},
        {"Date": "2026-05-03", "DepartureCity": "Reno", "ArrivalCity": "Austin"},
    ]
    out = A.score_flights(rows)
    assert out["direction"] == "neutral"
    assert out["strength"] <= 0.3
    assert out["flight_count"] == 2
    assert "Austin → Reno" in out["recent_routes"]


def test_flights_empty_returns_none():
    assert A.score_flights([]) is None
