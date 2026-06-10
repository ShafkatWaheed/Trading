"""Cold-start the AI analyst: strict point-in-time 90-day walk-forward.

For each past trading day (oldest→newest): predict (bootstrap mode, no live
search), grade open→close, and every week-end rewrite the playbook from that
week's graded results. Idempotent/resumable — days already predicted are
skipped. Run: .venv/bin/python -m scripts.bootstrap_ai_analyst [--days 90]
"""
from __future__ import annotations

import argparse
import logging

from api.services import analyst_playbook
from api.services.analyst_predictor import predict_for_date
from api.services.predictions_service import (
    get_accuracy_window,
    record_actuals_for_date,
    _load_history_with_context,
)
from src.utils.db import get_connection, init_db

logger = logging.getLogger(__name__)


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


def run(days: int = 90) -> dict:
    init_db()
    predicted = graded = 0
    for d in _trading_days(days):
        if _already_predicted(d):
            continue
        predict_for_date(d, mode="bootstrap")
        predicted += 1
        record_actuals_for_date(d)
        graded += 1
        if _is_week_end(d):
            _rewrite_playbook_window(d)
    acc = get_accuracy_window(window_days=days, hit_threshold_pct=15)
    logger.info("bootstrap done: predicted=%d graded=%d hit_rate=%s",
                predicted, graded, acc.get("hit_rate"))
    return {"predicted": predicted, "graded": graded, "accuracy": acc}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    print(run(parser.parse_args().days))
