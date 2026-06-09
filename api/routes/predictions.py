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


@router.get("/strategies")
def strategies() -> dict:
    """All strategies (active + retired) in version order."""
    return {"strategies": predictions_service.list_strategies()}


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
