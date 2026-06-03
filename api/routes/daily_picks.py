"""Daily Picks route — what to buy today, from 8 specialized agents.

GET /daily-picks               — cached 8h by date; first call of the day runs
                                 all 8 personalities in parallel (~90s)
GET /daily-picks?force=true    — bypass cache and regenerate
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from api.services import daily_picks_service


router = APIRouter(prefix="/daily-picks", tags=["daily-picks"])


@router.get("")
def get_daily_picks(
    force: bool = Query(False, description="Bypass the 8-hour cache and regenerate"),
) -> dict:
    """8 agent personalities run in parallel, each picks 5 stocks.

    Returns:
      - consensus: stocks 3+ agents independently picked (high conviction)
      - contrarians: each agent's top pick that no other agent chose
      - agents: full per-agent picks (8 columns × 5 picks)
    """
    return daily_picks_service.get_daily_picks(force=force)
