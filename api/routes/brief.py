"""Brief route — daily narrative + ranked picks.

GET /brief                          — cached (60min); cold cache returns
                                       {status: "computing"} + kicks generation
                                       in background. Frontend polls until ready.
GET /brief?force=true               — bypass cache and regenerate synchronously
                                       (user explicitly asked, accepts the wait)
GET /brief?diversity=true           — enforce max-2-per-sector cap on actionable picks
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from api.schemas import BriefResponse
from api.services import brief_service
from api.services._background_jobs import kick
from src.utils.db import cache_get


router = APIRouter(prefix="/brief", tags=["brief"])


def _stub_computing() -> dict:
    """Minimal valid BriefResponse payload returned while generation runs in
    the background. Frontend polls `status` to know when to swap in the real
    payload. Every required-field default must satisfy the schema."""
    from datetime import datetime
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "regime": "unclear",
        "regime_explanation": "Brief is being generated — Claude is composing the lens, picks, and narrative. Polling will update automatically.",
        "market_story": {"headline": "Generating brief...", "paragraphs": [], "investment_angles": []},
        "chapters": [],
        "lens": None,
        "picks": [],
        "closing": "",
        "meta": {
            "candidates_considered": 0,
            "sectors_in_focus": [],
            "themes_in_focus": [],
            "pulse_period": "1M",
            "lens_fallback_used": False,
        },
        "status": "computing",
    }


@router.get("", response_model=BriefResponse)
def get_brief(
    force: bool = Query(False),
    diversity: bool = Query(False, description="Enforce max-2-per-sector cap on actionable picks."),
) -> dict:
    # force=True is the "user clicked Regenerate" path — run synchronously so
    # they get the new brief on this exact request.
    if force:
        out = brief_service.get_brief(force=True, diversity=diversity)
        if isinstance(out, dict):
            out["status"] = "ready"
        return out

    # Cached path: return cached if present, otherwise return a "computing"
    # stub instantly and kick generation in the background. Next poll will
    # pick up the populated cache.
    cached = cache_get(brief_service._CACHE_KEY)
    if cached:
        cached["status"] = "ready"
        return cached
    kick(
        f"brief:{brief_service._CACHE_KEY}",
        brief_service.get_brief,
        force=False, diversity=diversity,
    )
    return _stub_computing()
