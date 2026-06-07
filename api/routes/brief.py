"""Brief route — daily narrative + ranked picks.

GET  /brief                          — cached (60min); cold cache returns
                                       {status: "computing"} + kicks generation
                                       in background. Frontend polls until ready.
GET  /brief?force=true               — bypass cache and regenerate synchronously
                                       (user explicitly asked, accepts the wait)
GET  /brief?diversity=true           — enforce max-2-per-sector cap on actionable picks
POST /brief/restart                  — cancel the in-flight brief job and wipe
                                       phase checkpoints; next GET kicks fresh.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from api.schemas import BriefResponse
from api.services import _phase_cache, _profiler, brief_service
from api.services._background_jobs import force_restart, get_job_status, kick
from src.utils.db import cache_get


router = APIRouter(prefix="/brief", tags=["brief"])


def _job_key_for(diversity: bool) -> str:
    """The kick/heartbeat key used for THIS variant of the brief.

    Mirrors the cache key shape so the on/off variants get separate job
    rows and don't dedupe each other.
    """
    cache_key = f"{brief_service._CACHE_KEY}:div={int(bool(diversity))}"
    return f"brief:{cache_key}"


def _stub_computing(diversity: bool) -> dict:
    """Minimal valid BriefResponse payload returned while generation runs in
    the background. Frontend polls `status` to know when to swap in the real
    payload. Every required-field default must satisfy the schema.

    When a `background_jobs` row exists, surface its `current_phase`,
    `progress_pct`, and `elapsed_s` so the UI can render a live progress bar
    instead of a static spinner. Status string stays `"computing"` while the
    job is running so the existing polling logic keeps working.
    """
    from datetime import datetime

    job_key = _job_key_for(diversity)
    job = get_job_status(job_key)

    # Defaults — used when no job row yet (about to be kicked) or when the
    # row is stale/failed in an unexpected way.
    current_phase: str | None = None
    progress_pct: int = 0
    elapsed_s: int = 0
    started_at: str | None = None
    job_error: str | None = None
    job_status_str = "computing"

    if job:
        if job["status"] == "running":
            current_phase = job["current_phase"]
            progress_pct = job["progress_pct"] or 0
            elapsed_s = job["elapsed_s"]
            started_at = job["started_at"]
        elif job["status"] == "failed":
            # Surface the failure so the UI can show a "regenerate" prompt
            # rather than spinning forever. Frontend reads `job_status` to
            # branch (we don't change the top-level `status` so old clients
            # that only check `status === "computing"` still poll and then
            # the next kick will produce a real brief).
            job_status_str = "failed"
            job_error = job["error"]
            elapsed_s = job["elapsed_s"]

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
        # New progress fields — additive so the existing UI keeps working.
        "current_phase": current_phase,
        "progress_pct": progress_pct,
        "elapsed_s": elapsed_s,
        "started_at": started_at,
        "job_status": job_status_str,
        "job_error": job_error,
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
    #
    # The cache key MUST mirror the one the service writes (see
    # brief_service.get_brief): per-diversity-flag so on/off variants don't
    # share state. Same naming convention used for kick() so duplicate
    # background generations across polls dedupe correctly.
    cache_key = f"{brief_service._CACHE_KEY}:div={int(bool(diversity))}"
    cached = cache_get(cache_key)
    if cached:
        cached["status"] = "ready"
        return cached
    job_key = _job_key_for(diversity)
    kick(
        job_key,
        brief_service.get_brief,
        force=False, diversity=diversity, job_key=job_key,
    )
    return _stub_computing(diversity)


@router.post("/restart")
def restart_brief(
    diversity: bool = Query(False, description="Which variant to restart (must match the brief being viewed)."),
) -> dict:
    """Cancel the in-flight brief job and wipe its phase checkpoints.

    Does NOT kill the underlying Claude subprocess (Python can't forcibly
    cancel threads) — but a new GET /brief will start a fresh job and the
    user gets a fresh stub immediately. The cached completed-brief row (if
    any) is left alone; only the in-flight state and phase checkpoints are
    cleared.
    """
    job_key = _job_key_for(diversity)
    force_restart(job_key)
    wiped = _phase_cache.invalidate("MARKET")
    return {"restarted": True, "job_key": job_key, "phases_invalidated": wiped}


@router.get("/timings")
def brief_timings(
    limit: int = Query(20, ge=1, le=100, description="Number of recent runs to return."),
) -> dict:
    """Per-run phase breakdowns from the profiler.

    Use this to see where the brief actually spends its time before
    investing in pool/parallelize/cache work. Each run shows total
    wall-clock plus per-phase durations.
    """
    runs = _profiler.get_recent_runs(limit=limit, label_prefix="brief")
    return {"runs": runs, "count": len(runs)}
