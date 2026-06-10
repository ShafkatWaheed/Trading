"""Cold-start the AI analyst: strict point-in-time walk-forward (default 1 week).

For each past trading day (oldest→newest): predict (bootstrap mode, no live
search), grade open→close, and rewrite the playbook (on week-ends during the
walk, plus an unconditional final rewrite over the whole window so a short run
always builds the playbook). Idempotent/resumable — days already predicted are
skipped. Default window is 1 week (fast); the live forward-loop enriches the
playbook from there. Run: .venv/bin/python -m scripts.bootstrap_ai_analyst [--days 7]
"""
from __future__ import annotations

import argparse
import logging

from api.services import analyst_playbook, analyst_pit_service
from api.services.analyst_predictor import predict_for_date
from api.services.predictions_service import (
    get_accuracy_window,
    record_actuals_for_date,
    _load_history_with_context,
    _load_universe_ab,
)
from src.utils.db import get_connection, init_db

logger = logging.getLogger(__name__)

# Minimum fraction of the loaded universe the prefetch must cover before we
# trust the bootstrap. Below this, the run aborts loudly (likely throttling)
# rather than silently persisting 0 picks. Only enforced on a populated
# universe — an empty universe (e.g. tests' empty temp DB) skips the guard.
_MIN_COVERAGE = 0.5


def _already_predicted(date: str) -> bool:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT 1 FROM daily_predictions WHERE prediction_date=? LIMIT 1", (date,)
        ).fetchone() is not None
    finally:
        conn.close()


def _trading_days(n: int) -> list[str]:
    """Last `n` trading days (oldest→newest), YYYY-MM-DD, ending yesterday.

    Uses the NYSE calendar when pandas_market_calendars is installed; otherwise
    falls back to business days (Mon-Fri). The fallback over-counts holidays
    slightly — harmless for a cold-start window, since the assembler simply
    skips any day with no price bar <= D.
    """
    import datetime as _dt
    import pandas as pd
    end = _dt.date.today() - _dt.timedelta(days=1)
    try:
        import pandas_market_calendars as mcal
        sched = mcal.get_calendar("NYSE").schedule(
            start_date=(end - _dt.timedelta(days=n * 2)).isoformat(),
            end_date=end.isoformat())
        return [d.date().isoformat() for d in sched.index][-n:]
    except Exception:
        return [d.date().isoformat() for d in pd.bdate_range(end=end, periods=n)]


def _is_week_end(date: str) -> bool:
    import datetime as _dt
    return _dt.date.fromisoformat(date).weekday() == 4  # Friday


def _rewrite_playbook_window(date: str) -> None:
    history = _load_history_with_context(window_days=7)
    accuracy = get_accuracy_window(window_days=7, hit_threshold_pct=15)
    analyst_playbook.rewrite(history=history, accuracy=accuracy)


def _final_playbook_rewrite(window_days: int) -> None:
    """Rewrite the playbook from the whole cold-start window at the END of the run.

    Guarantees a short cold-start (e.g. 1 week) always builds the playbook even
    when no week-end day was walked — in a short window the only Friday is often
    already-predicted and thus skipped, so the in-loop rewrite never fires.
    No-op when there is no completed history (analyst_playbook.rewrite handles it).
    """
    history = _load_history_with_context(window_days=window_days)
    accuracy = get_accuracy_window(window_days=window_days, hit_threshold_pct=15)
    analyst_playbook.rewrite(history=history, accuracy=accuracy)


def _prefetch(symbols: list[str]) -> dict:
    """Bulk-fetch daily price history ONCE for the whole walk-forward.

    Module-level seam so tests can monkeypatch it to `lambda syms: {}` (no
    network). The returned {symbol: full-series DataFrame} is threaded through
    each day's predict/grade so the per-day work slices it in-memory instead of
    re-fetching the ~1,022-symbol universe (get_historical's cache TTL is only
    15 min).
    """
    return analyst_pit_service.prefetch_price_history(symbols)


def run(days: int = 7) -> dict:
    init_db()
    universe = _load_universe_ab()
    history = _prefetch(universe)
    # Fail loud if a populated universe came back mostly empty: that means
    # yfinance throttled the prefetch, and continuing would silently persist 0
    # picks while logging success. An EMPTY universe (e.g. empty temp DB) is
    # exempt so the guard never trips spuriously.
    if universe and len(history) < _MIN_COVERAGE * len(universe):
        raise RuntimeError(
            f"prefetch covered only {len(history)}/{len(universe)} symbols "
            f"(< {int(_MIN_COVERAGE * 100)}%) — likely yfinance throttling. "
            f"Aborting so the bootstrap does not silently persist 0 picks.")
    predicted = graded = 0
    for d in _trading_days(days):
        if _already_predicted(d):
            continue
        predict_for_date(d, mode="bootstrap", history=history)
        predicted += 1
        record_actuals_for_date(d, history=history)
        graded += 1
        if _is_week_end(d):
            _rewrite_playbook_window(d)
    # Always rebuild the playbook from the full cold-start window at the end, so
    # a short (1-week) run produces a playbook even if no fresh Friday was walked.
    _final_playbook_rewrite(days)
    acc = get_accuracy_window(window_days=days, hit_threshold_pct=15)
    logger.info("bootstrap done: predicted=%d graded=%d hit_rate=%s",
                predicted, graded, acc.get("hit_rate"))
    return {"predicted": predicted, "graded": graded, "accuracy": acc}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7,
                        help="cold-start window in calendar days (default 7 = ~1 week)")
    print(run(parser.parse_args().days))
