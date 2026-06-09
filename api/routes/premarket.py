"""Pre-market top movers + prediction overlay.

GET /premarket?top_n=20  — top N gainers + losers from Tier A, with
                            today's predicted picks overlaid as chips
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from api.services import premarket_service


router = APIRouter(prefix="/premarket", tags=["premarket"])


@router.get("")
def get_premarket(
    top_n: int = Query(20, ge=5, le=100),
) -> dict:
    return premarket_service.get_premarket_movers(top_n=top_n)
