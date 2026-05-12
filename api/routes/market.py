"""Market routes."""
from fastapi import APIRouter, Query

from api.schemas import (
    MarketPulseResponse, CalendarResponse, GeopoliticalResponse, DisruptionResponse,
    MarketDashboardResponse, MarketTakeawayResponse, MarketNewsResponse,
)
from api.services import (
    market_service, calendar_service, events_service, disruption_service,
    market_dashboard_service, market_takeaway_service, market_news_service,
)

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/pulse", response_model=MarketPulseResponse)
def market_pulse(period: str = Query("1M", regex="^(1D|1W|1M|3M|6M|1Y)$")) -> dict:
    return market_service.get_pulse(period=period)


@router.get("/calendar", response_model=CalendarResponse)
def market_calendar(
    days: int = Query(60, ge=7, le=180),
    limit: int = Query(12, ge=1, le=30),
) -> dict:
    return calendar_service.get_economic_calendar(days_window=days, limit=limit)


@router.get("/geopolitical", response_model=GeopoliticalResponse)
def market_geopolitical() -> dict:
    return events_service.get_geopolitical_events()


@router.get("/disruption", response_model=DisruptionResponse)
def market_disruption() -> dict:
    return disruption_service.get_disruption_themes()


@router.get("/dashboard", response_model=MarketDashboardResponse)
def market_dashboard(force: bool = Query(False)) -> dict:
    return market_dashboard_service.get_market_dashboard(force=force)


@router.get("/takeaway", response_model=MarketTakeawayResponse)
def market_takeaway(force: bool = Query(False)) -> dict:
    return market_takeaway_service.get_market_takeaway(force=force)


@router.get("/news", response_model=MarketNewsResponse)
def market_news(force: bool = Query(False)) -> dict:
    return market_news_service.get_market_news(force=force)
