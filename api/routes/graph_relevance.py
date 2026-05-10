"""Graph-relevance endpoint (Phase 8).

POST /graph/relevance
    Request: {"active_themes": [...], "tier": ["A","B"], "bullish_only": false, "limit": 50}
    Response: {"active_themes": [...], "relevance": [...], "total": N}
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.services import graph_relevance_service

router = APIRouter(prefix="/graph", tags=["graph"])


class ActiveThemeIn(BaseModel):
    commodity_code: str | None = None
    direction: str = "up"          # 'up' | 'down'
    target_stock: str | None = None
    intensity: float = 1.0


class RelevanceRequest(BaseModel):
    active_themes: list[ActiveThemeIn] = Field(..., min_length=1)
    tier: list[str] | None = None
    bullish_only: bool = False
    limit: int = Field(50, ge=1, le=500)


@router.post("/relevance")
def compute_relevance(req: RelevanceRequest) -> dict:
    return graph_relevance_service.compute_relevance(
        [t.model_dump() for t in req.active_themes],
        tier=req.tier,
        bullish_only=req.bullish_only,
        limit=req.limit,
    )
