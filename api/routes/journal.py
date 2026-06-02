"""Trade Journal routes — log buys/sells, list positions, current holdings,
performance stats, and the Gap Finder AI recommendation.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.schemas import (
    GapFinderResponse,
    JournalCloseRequest,
    JournalHoldingsResponse,
    JournalOpenRequest,
    JournalPosition,
    JournalPositionsResponse,
)
from api.services import gap_finder_service, journal_service

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("/positions", response_model=JournalPositionsResponse)
def list_positions(
    status: str | None = Query(None, pattern="^(open|closed)$"),
    symbol: str | None = Query(None, min_length=1, max_length=10),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    return journal_service.list_positions(status=status, symbol=symbol, limit=limit)


@router.post("/positions", response_model=JournalPosition)
def open_position(body: JournalOpenRequest) -> dict:
    try:
        return journal_service.open_position(
            symbol=body.symbol,
            entry_price=body.entry_price,
            shares=body.shares,
            direction=body.direction,
            thesis=body.thesis,
            report_verdict=body.report_verdict,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/positions/{position_id}/close", response_model=JournalPosition)
def close_position(position_id: int, body: JournalCloseRequest) -> dict:
    try:
        return journal_service.close_position(
            position_id=position_id,
            exit_price=body.exit_price,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/holdings", response_model=JournalHoldingsResponse)
def current_holdings() -> dict:
    return journal_service.current_holdings()


@router.get("/stats")
def stats() -> dict:
    return journal_service.get_stats()


# ── Gap Finder agent ────────────────────────────────────────────────


@router.get("/gap-finder", response_model=GapFinderResponse)
def gap_finder(
    force: bool = Query(False, description="Bypass the 6h cache and re-judge"),
) -> dict:
    """AI portfolio adviser: SELL / HOLD recs for your positions + BUY recs
    for adjacent stocks you don't own. Each pick is Claude-judged with
    WebSearch/WebFetch enabled for fresh context.
    """
    try:
        return gap_finder_service.get_gap_finder(force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gap finder failed: {e}")
