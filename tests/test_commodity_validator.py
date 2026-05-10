"""Tests for src/analysis/commodity_validator.py — Phase 6 backtest validation.

All synthetic price series; no live network or backtester calls.
"""

from __future__ import annotations

import math

import pytest

from src.analysis.commodity_validator import (
    DEFAULT_MIN_CORR,
    ValidationResult,
    pearson_correlation,
    update_exposure_confidence,
    validate_exposure,
)
from src.data.commodity_seed_loader import load_all
from src.data.universe_loader import load_tier_a
from src.utils.db import get_connection, init_db


# ── pearson correlation primitive ────────────────────────────────


def test_perfect_positive_correlation():
    xs = [1, 2, 3, 4, 5]
    ys = [2, 4, 6, 8, 10]
    assert math.isclose(pearson_correlation(xs, ys), 1.0)


def test_perfect_negative_correlation():
    xs = [1, 2, 3, 4, 5]
    ys = [10, 8, 6, 4, 2]
    assert math.isclose(pearson_correlation(xs, ys), -1.0)


def test_no_correlation_returns_near_zero():
    """Two orthogonal sinusoidal-ish patterns. Period mismatch keeps the
    Pearson correlation near zero."""
    xs = [1, 1, -1, -1, 1, 1, -1, -1, 1, 1, -1, -1]   # period 4
    ys = [1, -1, 1, -1, 1, -1, 1, -1, 1, -1, 1, -1]   # period 2
    # These are orthogonal — correlation should be exactly 0
    assert abs(pearson_correlation(xs, ys)) < 0.1


def test_short_inputs_return_zero():
    assert pearson_correlation([], []) == 0.0
    assert pearson_correlation([1], [1]) == 0.0
    assert pearson_correlation([1, 2], [3, 4]) == 0.0


def test_zero_variance_inputs_return_zero():
    assert pearson_correlation([1, 1, 1, 1], [1, 2, 3, 4]) == 0.0


# ── validate_exposure ────────────────────────────────────────────


def _generate_correlated_series(
    n: int = 100,
    target_corr: float = 0.5,
    seed: int = 0,
) -> tuple[list[float], list[float]]:
    """Build a synthetic (xs, ys) pair with approximately the given correlation.

    Uses a deterministic LCG so we don't introduce randomness into tests.
    """
    a = 1664525
    c_lcg = 1013904223
    m = 2 ** 32
    state = (seed + 1) % m

    def lcg() -> float:
        nonlocal state
        state = (a * state + c_lcg) % m
        return state / m - 0.5  # in [-0.5, 0.5]

    xs = [lcg() for _ in range(n)]
    noise = [lcg() for _ in range(n)]
    # ys = target * xs + (1-|target|) * noise
    factor = abs(target_corr)
    sign = 1.0 if target_corr >= 0 else -1.0
    ys = [sign * factor * x + (1 - factor) * noise_i for x, noise_i in zip(xs, noise)]
    return xs, ys


def test_validate_returns_validated_when_polarity_matches_strong_corr():
    xs, ys = _generate_correlated_series(target_corr=+0.6)
    out = validate_exposure(xs, ys, asserted_polarity=+1.0)
    assert out.confidence_label == "validated"
    assert out.correlation > DEFAULT_MIN_CORR


def test_validate_returns_disputed_when_polarity_opposite():
    """Asserted polarity is +1 but data shows strong negative correlation."""
    xs, ys = _generate_correlated_series(target_corr=-0.6)
    out = validate_exposure(xs, ys, asserted_polarity=+1.0)
    assert out.confidence_label == "disputed"


def test_validate_returns_weak_when_correlation_below_threshold():
    xs, ys = _generate_correlated_series(target_corr=0.05)
    out = validate_exposure(xs, ys, asserted_polarity=+1.0)
    assert out.confidence_label == "weak"


def test_validate_negative_polarity_validated_with_negative_corr():
    """Asserted -1 polarity (input squeeze) with empirical -0.5 corr → validated."""
    xs, ys = _generate_correlated_series(target_corr=-0.5)
    out = validate_exposure(xs, ys, asserted_polarity=-1.0)
    assert out.confidence_label == "validated"


def test_validate_carries_sample_size():
    xs, ys = _generate_correlated_series(n=42, target_corr=0.4)
    out = validate_exposure(xs, ys, asserted_polarity=+1.0)
    assert out.sample_size == 42


def test_min_corr_param_overrides_default():
    """A correlation around 0.30 should be 'validated' under default 0.20
    threshold but 'weak' under a stricter 0.50 threshold."""
    xs, ys = _generate_correlated_series(target_corr=0.30)
    out_default = validate_exposure(xs, ys, asserted_polarity=+1.0)
    out_strict = validate_exposure(xs, ys, asserted_polarity=+1.0, min_corr=0.50)
    # Default treats moderate corr as validated; strict treats it as weak
    assert out_default.confidence_label == "validated"
    assert out_strict.confidence_label == "weak"


# ── DB integration ───────────────────────────────────────────────


def test_update_exposure_does_not_overwrite_hand_loaded():
    """Hand-loaded rows must keep confidence='high' even if validator runs."""
    init_db()
    load_tier_a()
    load_all()

    conn = get_connection()
    try:
        # Pre-condition: XOM crude_oil output is hand-loaded
        before = conn.execute(
            "SELECT confidence, source FROM stock_commodity_exposure "
            "WHERE symbol='XOM' AND commodity_code='crude_oil' AND role='output'"
        ).fetchone()
        assert before["source"] == "hand"
        assert before["confidence"] == "high"
    finally:
        conn.close()

    # Try to relabel as 'disputed' — should be a no-op for hand-source rows
    update_exposure_confidence("XOM", "crude_oil", "output", "disputed", correlation=-0.5)

    conn = get_connection()
    try:
        after = conn.execute(
            "SELECT confidence, source FROM stock_commodity_exposure "
            "WHERE symbol='XOM' AND commodity_code='crude_oil' AND role='output'"
        ).fetchone()
        assert after["source"] == "hand"
        assert after["confidence"] == "high"   # unchanged
    finally:
        conn.close()


def test_update_exposure_relabels_claude_source_rows():
    """A claude-source row CAN be relabeled by the validator."""
    init_db()
    load_tier_a()
    load_all()

    conn = get_connection()
    try:
        # Insert a claude-source row that we'll relabel
        conn.execute(
            "INSERT OR REPLACE INTO stock_commodity_exposure "
            "(symbol, commodity_code, role, polarity, elasticity, confidence, source) "
            "VALUES ('TSLA', 'rare_earths', 'input', -1, 0.3, 'medium', 'claude')"
        )
        conn.commit()
    finally:
        conn.close()

    update_exposure_confidence("TSLA", "rare_earths", "input", "validated", correlation=-0.45)

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT confidence, evidence FROM stock_commodity_exposure "
            "WHERE symbol='TSLA' AND commodity_code='rare_earths' AND role='input'"
        ).fetchone()
        assert row["confidence"] == "validated"
        assert "corr=-0.45" in (row["evidence"] or "")
    finally:
        conn.execute(
            "DELETE FROM stock_commodity_exposure "
            "WHERE symbol='TSLA' AND commodity_code='rare_earths' AND role='input'"
        )
        conn.commit()
        conn.close()


def test_update_exposure_unknown_row_is_noop():
    """Updating a non-existent row must not raise."""
    init_db()
    update_exposure_confidence("ZZZ_NOT_REAL", "crude_oil", "output", "validated")
    # No assertion; just verifying no exception
