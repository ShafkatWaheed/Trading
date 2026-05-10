"""Alerts routes."""
from fastapi import APIRouter, Query

from api.schemas import AlertItem, AlertSummary
from api.services import alerts_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertItem])
def list_alerts(
    symbol: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    return alerts_service.list_alerts(symbol=symbol, limit=limit)


@router.get("/summary", response_model=AlertSummary)
def alert_summary() -> dict:
    return alerts_service.get_summary()


@router.delete("")
def clear_all() -> dict:
    return alerts_service.clear_all()
