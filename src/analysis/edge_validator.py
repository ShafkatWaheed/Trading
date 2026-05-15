"""Edge backtest validator (Phase 8).

Iterates over `stock_commodity_exposure` rows, fetches historical price
returns for the commodity (via the benchmark ETF) and the stock, and
runs `commodity_validator.validate_exposure` on the regression. Updates
the row's `confidence` field with one of {validated, disputed, weak}.

Hand-loaded edges (`source='hand'`) are NEVER overwritten.

Network-gated: tests inject a fake price-fetcher. Live runs use the
existing data layer (yfinance via `src/data/market.py`).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from src.analysis.commodity_validator import (
    ValidationResult,
    update_exposure_confidence,
    validate_exposure,
)
from src.utils.db import get_connection, init_db


@dataclass
class ExposureValidation:
    symbol: str
    commodity_code: str
    role: str
    asserted_polarity: float
    result: ValidationResult | None
    error: str | None = None


# ── price fetchers ───────────────────────────────────────────────


def _default_returns_fetcher(ticker: str, period_days: int = 504) -> list[float]:
    """Fetch daily-return series for `ticker` over the last N days.

    Uses the existing data layer (yfinance via MarketDataService). Returns
    an empty list on failure — caller decides how to handle.
    """
    try:
        from src.data.market import MarketDataService

        market = MarketDataService()
        df = market.get_historical(ticker, period_days=period_days)
        if df is None or df.empty:
            return []
        closes = df["close"].astype(float).tolist()
    except Exception:
        return []

    if len(closes) < 3:
        return []
    # Daily returns
    return [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] != 0
    ]


# ── per-row validation ──────────────────────────────────────────


def validate_one(
    *,
    symbol: str,
    commodity_code: str,
    role: str,
    asserted_polarity: float,
    benchmark_ticker: str | None,
    returns_fetcher: Callable[[str, int], list[float]] | None = None,
    period_days: int = 504,
) -> ExposureValidation:
    """Validate one (symbol, commodity, role) tuple by regressing returns.

    Returns ExposureValidation with either a ValidationResult or an error.
    """
    fetcher = returns_fetcher or _default_returns_fetcher

    if not benchmark_ticker:
        return ExposureValidation(
            symbol=symbol, commodity_code=commodity_code, role=role,
            asserted_polarity=asserted_polarity, result=None,
            error="no_benchmark_ticker",
        )

    stock_returns = fetcher(symbol, period_days)
    if not stock_returns:
        return ExposureValidation(
            symbol=symbol, commodity_code=commodity_code, role=role,
            asserted_polarity=asserted_polarity, result=None,
            error="no_stock_returns",
        )

    commodity_returns = fetcher(benchmark_ticker, period_days)
    if not commodity_returns:
        return ExposureValidation(
            symbol=symbol, commodity_code=commodity_code, role=role,
            asserted_polarity=asserted_polarity, result=None,
            error="no_commodity_returns",
        )

    result = validate_exposure(
        stock_returns=stock_returns,
        commodity_returns=commodity_returns,
        asserted_polarity=asserted_polarity,
    )
    return ExposureValidation(
        symbol=symbol, commodity_code=commodity_code, role=role,
        asserted_polarity=asserted_polarity, result=result,
    )


# ── batch runner ────────────────────────────────────────────────


def run_validation(
    *,
    skip_hand: bool = True,
    returns_fetcher: Callable[[str, int], list[float]] | None = None,
    period_days: int = 504,
    max_rows: int | None = None,
    log: bool = True,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Run validation across all eligible exposure rows.

    Args:
        skip_hand: True (default) — don't re-validate hand-curated rows.
            Hand rows are by definition 'high' confidence; we don't relabel them.
        returns_fetcher: dependency-injection point. None → live network fetch.
        period_days: backtest window (default ~2 years of trading days).
        max_rows: optional cap to limit a single run.

    Returns counts dict: validated, disputed, weak, errors, skipped_hand.
    """
    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    counts = {"validated": 0, "disputed": 0, "weak": 0, "errors": 0, "skipped_hand": 0}

    try:
        # Pull all (exposure × commodity benchmark) tuples in one query
        rows = conn.execute(
            """
            SELECT
                sce.symbol,
                sce.commodity_code,
                sce.role,
                sce.polarity,
                sce.source,
                c.benchmark_ticker
            FROM stock_commodity_exposure sce
            LEFT JOIN commodities c ON c.code = sce.commodity_code
            ORDER BY sce.symbol, sce.commodity_code, sce.role
            """
        ).fetchall()
        if max_rows is not None:
            rows = rows[:max_rows]

        for r in rows:
            if skip_hand and r["source"] == "hand":
                counts["skipped_hand"] += 1
                continue

            ev = validate_one(
                symbol=r["symbol"],
                commodity_code=r["commodity_code"],
                role=r["role"],
                asserted_polarity=float(r["polarity"]),
                benchmark_ticker=r["benchmark_ticker"],
                returns_fetcher=returns_fetcher,
                period_days=period_days,
            )

            if ev.error or ev.result is None:
                counts["errors"] += 1
                if log:
                    print(f"  [validate] {ev.symbol}/{ev.commodity_code}/{ev.role}: {ev.error}")
                continue

            label = ev.result.confidence_label   # 'validated' | 'disputed' | 'weak'
            counts[label] = counts.get(label, 0) + 1
            update_exposure_confidence(
                ev.symbol, ev.commodity_code, ev.role,
                label, correlation=ev.result.correlation, conn=conn,
            )
            if log:
                print(
                    f"  [validate] {ev.symbol}/{ev.commodity_code}/{ev.role}: "
                    f"corr={ev.result.correlation:+.2f} → {label}"
                )

        return counts
    finally:
        if own_conn:
            conn.close()


# ── Point-in-time backtest validator (Wave 1) ──────────────────────


class LookaheadViolation(Exception):
    """Raised when a SignalReading's available_at is after the decision timestamp."""


def assert_no_lookahead(
    readings: "list",
    *,
    decision_timestamp: str,
    strict: bool = False,
) -> None:
    """Raise LookaheadViolation if any reading is not available at decision time.

    Args:
      readings: list of SignalReading
      decision_timestamp: ISO 8601 UTC. A reading must have
                          available_at <= decision_timestamp (or < if strict).
      strict: when True, treat available_at == decision_timestamp as a violation.

    No-op on empty input. Aggregates all violations into a single
    exception message (do not stop at first).
    """
    if not readings:
        return

    violations = []
    for r in readings:
        available = r.available_at
        if strict:
            bad = available >= decision_timestamp
        else:
            bad = available > decision_timestamp
        if bad:
            violations.append(
                f"signal={r.signal_name} ticker={r.ticker} sector={r.sector} "
                f"available_at={available} > decision={decision_timestamp}"
            )

    if violations:
        n = len(violations)
        msg = f"{n} violation(s) found ({n} readings not yet available at decision time):\n  " + "\n  ".join(violations)
        raise LookaheadViolation(msg)
