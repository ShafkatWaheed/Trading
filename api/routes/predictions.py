"""Daily top-10 gainers predictions.

GET  /predictions/today                — picks for today (auto-generates on first call)
GET  /predictions/{date}               — picks for a specific YYYY-MM-DD
GET  /predictions/strategy/active      — current scoring strategy + config
POST /predictions/generate?date=YYYY-MM-DD  — manually trigger a generation
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query

from api.services import predictions_service


router = APIRouter(prefix="/predictions", tags=["predictions"])


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("/today")
def predictions_today() -> dict:
    return predictions_service.get_predictions_today()


@router.get("/strategy/active")
def active_strategy() -> dict:
    return predictions_service.get_active_strategy()


@router.get("/{date}")
def predictions_for_date(date: str) -> dict:
    if not _DATE_RE.match(date):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    return predictions_service.get_predictions_for_date(date)


@router.post("/generate")
def generate(
    date: str = Query(..., description="YYYY-MM-DD to generate predictions for"),
    force: bool = Query(False, description="Overwrite existing predictions for this date"),
) -> dict:
    if not _DATE_RE.match(date):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    return predictions_service.generate_predictions_for_date(date, force=force)
