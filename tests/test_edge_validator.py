"""Tests for the Phase 8 edge validator (commodity exposure backtest).

Live network/yfinance fetch is mocked; tests use synthetic price-return
series with known correlations.
"""

from __future__ import annotations

import pytest

from src.analysis.edge_validator import (
    ExposureValidation,
    run_validation,
    validate_one,
)
from src.data.commodity_seed_loader import load_all as load_commodities_all
from src.data.universe_loader import load_tier_a
from src.utils.db import get_connection, init_db


@pytest.fixture(scope="module", autouse=True)
def _seed():
    init_db()
    load_tier_a()
    load_commodities_all()


# ── synthetic returns ────────────────────────────────────────────


def _correlated_series(
    n: int, target_corr: float, seed: int = 0,
) -> tuple[list[float], list[float]]:
    """LCG-based deterministic correlated series. Same generator as the
    commodity_validator tests, kept consistent for reproducibility."""
    a, c, m = 1664525, 1013904223, 2 ** 32
    state = (seed + 1) % m

    def next_val() -> float:
        nonlocal state
        state = (a * state + c) % m
        return state / m - 0.5

    xs = [next_val() for _ in range(n)]
    noise = [next_val() for _ in range(n)]
    factor = abs(target_corr)
    sign = 1.0 if target_corr >= 0 else -1.0
    ys = [sign * factor * x + (1 - factor) * noise_i for x, noise_i in zip(xs, noise)]
    return xs, ys


# ── validate_one ─────────────────────────────────────────────────


def test_validate_one_returns_validated_for_matching_polarity():
    """A stock with output:crude_oil polarity=+1 should validate when its
    returns correlate POSITIVELY with crude_oil ETF returns."""
    stock_r, oil_r = _correlated_series(n=120, target_corr=+0.7)

    def fake_fetch(ticker, days):
        if ticker == "USO":
            return oil_r
        return stock_r

    ev = validate_one(
        symbol="XOM",
        commodity_code="crude_oil",
        role="output",
        asserted_polarity=+1.0,
        benchmark_ticker="USO",
        returns_fetcher=fake_fetch,
    )
    assert ev.error is None
    assert ev.result is not None
    assert ev.result.confidence_label == "validated"


def test_validate_one_returns_disputed_when_polarity_opposite():
    """Asserted +1 (output) but actually negatively correlated → disputed."""
    stock_r, oil_r = _correlated_series(n=120, target_corr=-0.6)

    def fake_fetch(ticker, days):
        return oil_r if ticker == "USO" else stock_r

    ev = validate_one(
        symbol="X",
        commodity_code="crude_oil",
        role="output",
        asserted_polarity=+1.0,
        benchmark_ticker="USO",
        returns_fetcher=fake_fetch,
    )
    assert ev.result.confidence_label == "disputed"


def test_validate_one_returns_weak_for_low_correlation():
    stock_r, oil_r = _correlated_series(n=120, target_corr=0.05)

    def fake_fetch(ticker, days):
        return oil_r if ticker == "USO" else stock_r

    ev = validate_one(
        symbol="X",
        commodity_code="crude_oil",
        role="output",
        asserted_polarity=+1.0,
        benchmark_ticker="USO",
        returns_fetcher=fake_fetch,
    )
    assert ev.result.confidence_label == "weak"


def test_validate_one_handles_missing_benchmark_ticker():
    ev = validate_one(
        symbol="ANY",
        commodity_code="ammonia",
        role="output",
        asserted_polarity=+1.0,
        benchmark_ticker=None,
    )
    assert ev.error == "no_benchmark_ticker"
    assert ev.result is None


def test_validate_one_handles_no_stock_returns():
    def fake_fetch(ticker, days):
        return [] if ticker != "USO" else [0.01, -0.01, 0.02]

    ev = validate_one(
        symbol="DEAD",
        commodity_code="crude_oil",
        role="output",
        asserted_polarity=+1.0,
        benchmark_ticker="USO",
        returns_fetcher=fake_fetch,
    )
    assert ev.error == "no_stock_returns"


def test_validate_one_handles_no_commodity_returns():
    def fake_fetch(ticker, days):
        return [] if ticker == "USO" else [0.01] * 10

    ev = validate_one(
        symbol="X",
        commodity_code="crude_oil",
        role="output",
        asserted_polarity=+1.0,
        benchmark_ticker="USO",
        returns_fetcher=fake_fetch,
    )
    assert ev.error == "no_commodity_returns"


# ── run_validation batch behaviour ──────────────────────────────


def test_run_validation_skips_hand_rows():
    """Default behaviour: hand-curated rows are NOT re-validated."""
    out = run_validation(
        skip_hand=True,
        returns_fetcher=lambda t, d: [0.01, 0.02, -0.01, 0.03] * 30,
        log=False,
        # Sample large enough to guarantee hand rows are reached even after
        # the universe-expansion injection of ~2k Claude-sourced exposures.
        max_rows=200,
    )
    assert out["skipped_hand"] >= 1


def test_run_validation_processes_non_hand_rows():
    """Insert a synthetic non-hand exposure row and verify it gets validated."""
    init_db()
    conn = get_connection()
    try:
        # Add a synthetic Claude-source exposure that needs validation
        conn.execute("DELETE FROM stock_commodity_exposure WHERE symbol='SYN_V1'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_V1'")
        conn.execute(
            "INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_V1', 'B', 'test')"
        )
        conn.execute(
            "INSERT INTO stock_commodity_exposure "
            "(symbol, commodity_code, role, polarity, elasticity, confidence, evidence, source) "
            "VALUES ('SYN_V1', 'crude_oil', 'output', 1.0, 0.5, 'medium', 'claude says', 'claude')"
        )
        conn.commit()
    finally:
        conn.close()

    # Provide returns that confirm the +1 polarity
    stock_r, oil_r = _correlated_series(n=120, target_corr=+0.6)

    def fake_fetch(ticker, days):
        return oil_r if ticker == "USO" else stock_r

    out = run_validation(
        skip_hand=True,
        returns_fetcher=fake_fetch,
        log=False,
    )
    # The synthetic row should have been validated
    assert out["validated"] >= 1

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT confidence FROM stock_commodity_exposure "
            "WHERE symbol='SYN_V1' AND commodity_code='crude_oil' AND role='output'"
        ).fetchone()
        assert row["confidence"] == "validated"
    finally:
        conn.execute("DELETE FROM stock_commodity_exposure WHERE symbol='SYN_V1'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_V1'")
        conn.commit()
        conn.close()


def test_run_validation_does_not_relabel_hand_rows_even_with_disagreement():
    """Verify that hand rows stay 'high' even if returns_fetcher would
    suggest a different label."""
    # Pre-condition: XOM crude_oil output is hand-loaded (from load_all_commodities)
    conn = get_connection()
    try:
        before = conn.execute(
            "SELECT confidence, source FROM stock_commodity_exposure "
            "WHERE symbol='XOM' AND commodity_code='crude_oil' AND role='output'"
        ).fetchone()
        assert before["source"] == "hand"
        assert before["confidence"] == "high"
    finally:
        conn.close()

    # Run with skip_hand=True (default) — XOM should be skipped entirely
    out = run_validation(skip_hand=True, returns_fetcher=lambda t, d: [], log=False)
    # Verify XOM stayed as hand/high
    conn = get_connection()
    try:
        after = conn.execute(
            "SELECT confidence, source FROM stock_commodity_exposure "
            "WHERE symbol='XOM' AND commodity_code='crude_oil' AND role='output'"
        ).fetchone()
        assert after["source"] == "hand"
        assert after["confidence"] == "high"
    finally:
        conn.close()


def test_run_validation_counts_errors():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stock_commodity_exposure WHERE symbol='SYN_ERR'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_ERR'")
        conn.execute(
            "INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_ERR', 'B', 'test')"
        )
        conn.execute(
            "INSERT INTO stock_commodity_exposure "
            "(symbol, commodity_code, role, polarity, elasticity, confidence, evidence, source) "
            "VALUES ('SYN_ERR', 'crude_oil', 'output', 1.0, 0.5, 'medium', 'fake', 'claude')"
        )
        conn.commit()
    finally:
        conn.close()

    # Always-empty fetcher → all rows error out
    out = run_validation(
        skip_hand=True,
        returns_fetcher=lambda t, d: [],
        log=False,
    )
    assert out["errors"] >= 1

    conn = get_connection()
    try:
        conn.execute("DELETE FROM stock_commodity_exposure WHERE symbol='SYN_ERR'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_ERR'")
        conn.commit()
    finally:
        conn.close()
