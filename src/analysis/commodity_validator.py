"""Backtest validator for commodity exposures (Phase 6).

For each `(symbol, commodity_code, role)` edge in `stock_commodity_exposure`,
regress the stock's returns against the commodity's returns over a 5-10 year
window. Update the edge's `confidence` field based on whether the empirical
correlation matches the LLM/hand-asserted polarity.

Pure function on (price_series, exposure) — the caller plugs in real price
data via the data layer or a test fixture. No live network access at the
core layer.

Status labels written to `confidence`:
    'validated'  — empirical sign matches AND |corr| > 0.20
    'disputed'   — empirical sign opposite the asserted polarity
    'weak'       — |corr| ≤ 0.20 (not enough signal either way)
    (existing 'high' / 'medium' / 'low' / 'hand' values are preserved when
    the validator can't run for lack of price data.)

Usage:
    from src.analysis.commodity_validator import validate_exposure
    new_confidence = validate_exposure(
        stock_returns=[0.01, -0.02, ...],
        commodity_returns=[0.005, -0.01, ...],
        asserted_polarity=+1.0,
    )
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


# Threshold above which we treat the empirical correlation as a real signal.
DEFAULT_MIN_CORR: float = 0.20


@dataclass(frozen=True)
class ValidationResult:
    """Output of one (symbol, commodity, role) validation pass."""
    correlation: float            # empirical Pearson correlation, -1..1
    asserted_polarity: float      # what the seed/Claude said
    confidence_label: str         # 'validated' | 'disputed' | 'weak'
    sample_size: int


def pearson_correlation(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Pearson r — standalone implementation, no scipy dependency.

    Returns 0.0 for inputs that are too short or zero-variance (a
    well-behaved degenerate case).
    """
    n = min(len(xs), len(ys))
    if n < 3:
        return 0.0
    xs = list(xs[:n])
    ys = list(ys[:n])
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def validate_exposure(
    stock_returns: Sequence[float],
    commodity_returns: Sequence[float],
    *,
    asserted_polarity: float,
    min_corr: float = DEFAULT_MIN_CORR,
) -> ValidationResult:
    """Compare empirical correlation against the seed's asserted polarity.

    Returns:
        ValidationResult with confidence_label ∈ {'validated','disputed','weak'}.
    """
    corr = pearson_correlation(stock_returns, commodity_returns)
    n = min(len(stock_returns), len(commodity_returns))

    if abs(corr) < min_corr:
        label = "weak"
    elif (corr > 0) == (asserted_polarity > 0):
        # Sign matches → validated
        label = "validated"
    else:
        # Sign opposite → disputed
        label = "disputed"

    return ValidationResult(
        correlation=corr,
        asserted_polarity=asserted_polarity,
        confidence_label=label,
        sample_size=n,
    )


# ── DB integration helpers (for the actual validator job) ─────────


def update_exposure_confidence(
    symbol: str,
    commodity_code: str,
    role: str,
    new_confidence: str,
    *,
    correlation: float | None = None,
    conn=None,
) -> None:
    """Update the `confidence` field on a single exposure row.

    Hand-loaded rows are NEVER overwritten — confidence stays as 'high'.
    Only LLM/auto rows get the validated/disputed/weak label.
    """
    from src.utils.db import get_connection, init_db

    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT source FROM stock_commodity_exposure "
            "WHERE symbol=? AND commodity_code=? AND role=?",
            (symbol, commodity_code, role),
        ).fetchone()
        if cur is None:
            return
        if cur["source"] == "hand":
            # Don't relabel hand-curated edges; their confidence is by definition 'high'.
            return

        evidence_suffix = ""
        if correlation is not None:
            evidence_suffix = f" | corr={correlation:.2f}"

        conn.execute(
            """
            UPDATE stock_commodity_exposure SET
                confidence = ?,
                evidence = COALESCE(evidence, '') || ?
            WHERE symbol=? AND commodity_code=? AND role=?
            """,
            (new_confidence, evidence_suffix, symbol, commodity_code, role),
        )
        conn.commit()
    finally:
        if own_conn:
            conn.close()
