"""Discover routes."""
from fastapi import APIRouter, Query

from api.schemas import DiscoverResponse
from api.services import discover_service, watchlist_service

router = APIRouter(prefix="/discover", tags=["discover"])


@router.get("", response_model=DiscoverResponse)
def discover(
    min_score: float = Query(0, ge=0, le=100),
    limit: int = Query(30, ge=1, le=100),
    sector: str | None = Query(None),
    period: str = Query("1M", regex="^(1D|1W|1M|3M|6M|1Y)$"),
    only_watchlist: bool = Query(True),
) -> dict:
    """If only_watchlist=true (default), restrict to user's watchlist symbols."""
    syms = None
    if only_watchlist:
        watch = watchlist_service.list_watchlist()
        syms = [w["symbol"] for w in watch]
    return discover_service.get_opportunities(
        min_score=min_score, limit=limit, sector=sector, period=period, symbols=syms,
    )
