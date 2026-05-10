"""Watchlist routes."""
from fastapi import APIRouter

from api.services import watchlist_service
from pydantic import BaseModel, Field

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class AddBody(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10)


@router.get("")
def list_watchlist() -> list[dict]:
    return watchlist_service.list_watchlist()


@router.post("")
def add(body: AddBody) -> dict:
    return watchlist_service.add(body.symbol)


@router.delete("/{symbol}")
def delete(symbol: str) -> dict:
    return watchlist_service.remove(symbol)


@router.post("/top5")
def add_top5() -> dict:
    from api.services.discover_service import POPULAR_TOP5
    return watchlist_service.add_top5(POPULAR_TOP5)
