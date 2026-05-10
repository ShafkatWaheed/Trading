"""Graph routes — peer / supply-chain / neighborhood / ownership queries.

Phase 3 shipped: GET /graph/stock/{sym}/peers
Phase 4 shipped: GET /graph/stock/{sym}/neighborhood
Phase 7 ships:   GET /graph/stock/{sym}/holders
                 GET /graph/institution/{cik}/holdings
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.schemas import (
    InstitutionHoldingsResponse,
    NeighborhoodResponse,
    PeerListResponse,
    TopHoldersResponse,
)
from api.services import neighborhood_service, ownership_service, peer_service

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/stock/{symbol}/peers", response_model=PeerListResponse)
def get_peers(
    symbol: str,
    max_results: int = Query(20, ge=1, le=200),
) -> dict:
    out = peer_service.get_peers(symbol, max_results=max_results)
    if out["tier"] is None:
        return {"symbol": symbol.upper(), "name": None, "tier": None, "peers": [], "total": 0}
    return out


@router.get("/stock/{symbol}/neighborhood", response_model=NeighborhoodResponse)
def get_neighborhood(symbol: str) -> dict:
    return neighborhood_service.get_neighborhood(symbol)


@router.get("/stock/{symbol}/holders", response_model=TopHoldersResponse)
def get_top_holders(
    symbol: str,
    max_results: int = Query(20, ge=1, le=200),
) -> dict:
    return ownership_service.top_holders(symbol, max_results=max_results)


@router.get("/institution/{cik}/holdings", response_model=InstitutionHoldingsResponse)
def get_institution_holdings(
    cik: str,
    max_results: int = Query(50, ge=1, le=500),
) -> dict:
    return ownership_service.also_held(cik, max_results=max_results)
