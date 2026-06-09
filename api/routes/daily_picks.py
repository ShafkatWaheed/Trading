"""Daily Picks route — what to buy today, from 8 specialized agents.

GET  /daily-picks               — cached 8h; cold cache returns "computing"
                                  stub + kicks generation in background.
                                  Frontend polls until ready (same pattern
                                  as /brief).
GET  /daily-picks?force=true    — bypass cache and regenerate synchronously
                                  (user explicitly clicked Refresh)
POST /daily-picks/restart       — cancel stuck job + start fresh
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Query

from api.services import daily_picks_service
from api.services._background_jobs import force_restart, get_job_status, kick
from src.utils.db import cache_get


router = APIRouter(prefix="/daily-picks", tags=["daily-picks"])


def _job_key() -> str:
    """One key per calendar day — picks reset overnight anyway."""
    return f"daily_picks:{date.today().isoformat()}"


def _stub_computing() -> dict:
    """Minimal payload returned while generation runs in the background.

    Frontend polls; same status-string contract as /brief.
    """
    jk = _job_key()
    job = get_job_status(jk)
    current_phase = None
    progress_pct = 0
    elapsed_s = 0
    started_at = None
    job_status_str = "computing"
    job_error = None
    if job:
        if job["status"] == "running":
            current_phase = job["current_phase"]
            progress_pct = job["progress_pct"] or 0
            elapsed_s = job["elapsed_s"]
            started_at = job["started_at"]
        elif job["status"] == "failed":
            job_status_str = "failed"
            job_error = job["error"]
            elapsed_s = job["elapsed_s"]

    return {
        "status":         "computing",
        "as_of_date":     date.today().isoformat(),
        "generated_at":   datetime.utcnow().isoformat() + "Z",
        "market_context": {},
        "agents":         [],
        "consensus":      [],
        "contrarians":    [],
        "from_cache":     False,
        # Progress fields surfaced to the UI for live phase + percentage
        "current_phase":  current_phase,
        "progress_pct":   progress_pct,
        "elapsed_s":      elapsed_s,
        "started_at":     started_at,
        "job_status":     job_status_str,
        "job_error":      job_error,
    }


@router.get("")
def get_daily_picks(
    force: bool = Query(False, description="Bypass the 8-hour cache and regenerate"),
) -> dict:
    """8 agent personalities run in parallel, each picks 5 stocks.

    Returns:
      - status: "ready" or "computing" (only on cold cache)
      - consensus: stocks 3+ agents independently picked
      - contrarians: each agent's top pick that no other agent chose
      - agents: full per-agent picks
    """
    if force:
        out = daily_picks_service.get_daily_picks(force=True)
        if isinstance(out, dict):
            out["status"] = "ready"
        return out

    today = date.today().isoformat()
    cache_key = f"daily_picks:v1:{today}"
    cached = cache_get(cache_key)
    if cached:
        cached["status"] = "ready"
        return cached

    jk = _job_key()
    kick(jk, daily_picks_service.get_daily_picks, force=False, job_key=jk)
    return _stub_computing()


@router.post("/restart")
def restart_daily_picks() -> dict:
    """Cancel the in-flight job. The next GET kicks a fresh background job."""
    jk = _job_key()
    force_restart(jk)
    return {"restarted": True, "job_key": jk}
