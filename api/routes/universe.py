"""Universe routes — query the 4,800-stock universe by tier / industry / sector."""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.schemas import UniverseResponse
from api.services import universe_service

router = APIRouter(prefix="/universe", tags=["universe"])


@router.get("", response_model=UniverseResponse)
def get_universe_endpoint(
    tier: str | None = Query(None, description="Comma-separated tiers (A,B,C,D)"),
    industry: str | None = Query(None, description="yfinance industry code"),
    sector: str | None = Query(None, description="GICS-style sector"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
) -> dict:
    tiers = [t.strip().upper() for t in tier.split(",")] if tier else None
    return universe_service.get_universe(
        tier=tiers,
        industry=industry,
        sector=sector,
        limit=limit,
        offset=offset,
    )
