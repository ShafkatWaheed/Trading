"""Daily top-10 gainers predictions.

GET  /predictions/today                       — picks for today (auto-generates on first call)
GET  /predictions/{date}                      — picks for a specific YYYY-MM-DD
GET  /predictions/{date}/with-actuals         — picks + open/close/rank if recorded
GET  /predictions/accuracy?window_days=30     — rolling hit-rate over last N days
GET  /predictions/strategy/active             — current scoring strategy + config
POST /predictions/generate?date=YYYY-MM-DD    — manually trigger a generation
POST /predictions/record-actuals?date=...     — manually trigger actuals recording
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query

from api.services import predictions_service


router = APIRouter(prefix="/predictions", tags=["predictions"])


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_date(date: str) -> None:
    if not _DATE_RE.match(date):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")


@router.get("/analyst/playbook")
def analyst_playbook_route() -> dict:
    """The AI analyst's current accumulated playbook (markdown)."""
    from api.services import analyst_playbook
    return {"playbook": analyst_playbook.read()}


@router.post("/analyst/playbook/refresh")
def refresh_analyst_playbook(
    window_days: int = Query(
        30, ge=2, le=400,
        description="Rewrite the playbook from graded predictions in this many days "
                    "(default 30 ≈ all recent graded data; wider than the weekly 7-day job)",
    ),
) -> dict:
    """Rewrite the AI-analyst playbook now from graded predictions in the window.

    Unlike the weekly job (7-day window), this defaults to a wide window so a
    manual refresh learns from every graded pick available. Long Opus call.
    """
    from api.services import analyst_playbook
    from api.services.predictions_service import (
        _load_history_with_context, get_accuracy_window,
    )
    history = _load_history_with_context(window_days=window_days)
    accuracy = get_accuracy_window(window_days=window_days, hit_threshold_pct=15)
    res = analyst_playbook.rewrite(history=history, accuracy=accuracy)
    res["history_rows"] = len(history)
    return res


@router.get("/bootstrap/status")
def bootstrap_status() -> dict:
    """Cold-start progress: number of bootstrap-mode days predicted + rolling hit rate."""
    from api.services.predictions_service import get_accuracy_window
    from src.utils.db import get_connection, init_db
    init_db()
    conn = get_connection()
    try:
        n = conn.execute(
            "SELECT COUNT(DISTINCT prediction_date) c FROM daily_predictions WHERE mode='bootstrap'"
        ).fetchone()["c"]
    finally:
        conn.close()
    acc = get_accuracy_window(window_days=90, hit_threshold_pct=15)
    return {"predicted_days": n, "hit_rate": acc.get("hit_rate"),
            "days_evaluated": acc.get("days_evaluated")}


@router.get("/today")
def predictions_today() -> dict:
    return predictions_service.get_predictions_today()


@router.get("/strategy/active")
def active_strategy() -> dict:
    return predictions_service.get_active_strategy()


@router.get("/accuracy")
def accuracy(
    window_days: int = Query(30, ge=1, le=365),
    hit_threshold: int = Query(25, ge=1, le=500),
) -> dict:
    """Rolling hit rate over the last `window_days` of completed predictions.

    `hit_threshold` = a pick counts as a hit if its actual universe rank
    that day was <= this value. Default 25 (top 5% of Tier A ≈ 500 names).
    """
    return predictions_service.get_accuracy_window(
        window_days=window_days, hit_threshold=hit_threshold
    )


# Literal GET routes MUST be declared before the parametric /{date} route below,
# or FastAPI matches them as a date (e.g. /strategies -> {date}="strategies") and
# rejects them with "date must be YYYY-MM-DD".
@router.get("/strategies")
def strategies() -> dict:
    """All strategies (active + retired) in version order."""
    return {"strategies": predictions_service.list_strategies()}


@router.get("/skills")
def get_skills() -> dict:
    """Current prediction playbook (markdown) + last-updated timestamp."""
    return predictions_service.get_skills()


@router.get("/{date}/with-actuals")
def predictions_with_actuals(date: str) -> dict:
    _check_date(date)
    return predictions_service.get_predictions_with_actuals(date)


@router.get("/{date}")
def predictions_for_date(date: str) -> dict:
    _check_date(date)
    return predictions_service.get_predictions_for_date(date)


@router.post("/generate")
def generate(
    date: str = Query(..., description="YYYY-MM-DD to generate predictions for"),
    force: bool = Query(False, description="Overwrite existing predictions for this date"),
) -> dict:
    _check_date(date)
    return predictions_service.generate_predictions_for_date(date, force=force)


@router.post("/record-actuals")
def record_actuals(
    date: str = Query(..., description="YYYY-MM-DD to record actuals for (must be after market close)"),
) -> dict:
    _check_date(date)
    return predictions_service.record_actuals_for_date(date)


# ── Strategy adaptation ────────────────────────────────────────────────


@router.post("/strategy/review")
def review_strategy(
    window_days: int = Query(14, ge=2, le=90),
    force: bool = Query(False, description="Run even if no completed predictions exist yet"),
) -> dict:
    """Claude reviews recent predictions and proposes a new strategy.

    The proposal is saved as a DEACTIVATED row; activate it via
    POST /predictions/strategy/activate?version=N once you've vetted it.
    """
    return predictions_service.review_and_propose_strategy(
        window_days=window_days, force=force,
    )


@router.post("/strategy/activate")
def activate_strategy(
    version: int = Query(..., ge=1, description="Strategy version to activate"),
) -> dict:
    """Activate a strategy by version. Deactivates whatever was active."""
    return predictions_service.activate_strategy(version)


# ── Playbook (Phase 6) ────────────────────────────────────────────────


@router.post("/strategy/backtest")
def backtest_strategy(
    version: int | None = Query(None, ge=1, description="Saved strategy version to backtest"),
    days: int = Query(30, ge=5, le=180, description="How many trading days to evaluate"),
    hit_threshold: int = Query(25, ge=1, le=500),
    top_n: int = Query(10, ge=1, le=50),
) -> dict:
    """Backtest a saved strategy version against the last N trading days.

    IMPORTANT: This is a SIGNAL-FROZEN backtest. Only momentum is
    point-in-time correct; all other signals reflect TODAY's cached
    values. Use for relative weight comparison between strategies, NOT
    as a forecast of future returns. The response carries a `caveat`
    field with the same warning so callers can surface it.
    """
    from api.services import predictions_backtest_service
    return predictions_backtest_service.backtest_strategy(
        version=version, days=days, hit_threshold=hit_threshold, top_n=top_n,
    )


@router.post("/skills/update")
def update_skills(
    window_days: int = Query(30, ge=7, le=90),
    force: bool = Query(False),
) -> dict:
    """Ask Claude to rewrite the playbook from the last `window_days` of
    completed predictions. Skips when no completed predictions exist
    unless force=True (mostly for manual testing).
    """
    return predictions_service.update_prediction_skills(
        window_days=window_days, force=force,
    )
