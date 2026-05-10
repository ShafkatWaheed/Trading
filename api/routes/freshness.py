"""Freshness queue routes (Phase 7B).

GET  /freshness/queue          — list all stocks flagged 'needs_review'
POST /freshness/acknowledge    — apply user action: re_extract|skip_30d|pin_current
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from api.schemas import FreshnessQueueResponse
from api.services import freshness_service

router = APIRouter(prefix="/freshness", tags=["freshness"])


class AcknowledgeRequest(BaseModel):
    symbol: str
    action: str    # 're_extract' | 'skip_30d' | 'pin_current'


@router.get("/queue", response_model=FreshnessQueueResponse)
def get_queue() -> dict:
    return freshness_service.get_queue()


@router.post("/acknowledge")
def acknowledge(req: AcknowledgeRequest) -> dict:
    return freshness_service.acknowledge(req.symbol, req.action)
