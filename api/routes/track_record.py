"""AI Track Record routes (Phase 2.2).

Endpoints:
  GET  /ai/track-record           — accuracy stats with optional source/symbol/days filters
  GET  /ai/decisions/recent       — paginated decision log with status (pending/correct/incorrect)
  GET  /ai/decisions/top          — top wins + losses, sortable by return
  POST /ai/decisions/evaluate-now — manual evaluator kick (also runs on daily cron)
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from api.schemas import (
    TrackRecordResponse, DecisionsRecentResponse,
    EvaluatorRunResponse, TopWinsLossesResponse,
)
from api.services import decisions_outcome_service

router = APIRouter(prefix="/ai", tags=["ai-track-record"])


@router.get("/track-record", response_model=TrackRecordResponse)
def track_record(
    source: str | None = Query(None, pattern="^(recommendation|ai_analyst|bubble_score)$"),
    symbol: str | None = None,
    days: int | None = Query(90, ge=1, le=3650),
) -> dict:
    return decisions_outcome_service.get_track_record(source=source, symbol=symbol, days=days)


@router.get("/decisions/recent", response_model=DecisionsRecentResponse)
def decisions_recent(
    source: str | None = Query(None, pattern="^(recommendation|ai_analyst|bubble_score)$"),
    symbol: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    return decisions_outcome_service.recent_decisions(source=source, symbol=symbol, limit=limit)


@router.get("/decisions/top", response_model=TopWinsLossesResponse)
def decisions_top(
    limit: int = Query(10, ge=1, le=100),
    days: int | None = Query(90, ge=1, le=3650),
) -> dict:
    return decisions_outcome_service.top_wins_and_losses(limit=limit, days=days)


@router.post("/decisions/evaluate-now", response_model=EvaluatorRunResponse)
def evaluate_now() -> dict:
    """Run the outcome evaluator on demand. The daily cron does this automatically."""
    return decisions_outcome_service.evaluate_pending_decisions()
