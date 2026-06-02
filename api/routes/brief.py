"""Brief route — daily narrative + ranked picks.

GET /brief             — assembled chapters (cached 60min)
GET /brief?force=true  — bypass cache and regenerate
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from api.schemas import BriefResponse
from api.services import brief_service


router = APIRouter(prefix="/brief", tags=["brief"])


@router.get("", response_model=BriefResponse)
def get_brief(force: bool = Query(False)) -> dict:
    return brief_service.get_brief(force=force)
