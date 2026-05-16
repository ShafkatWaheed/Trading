"""Refresh routes — manual pipeline triggers with progress bars."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from api.services import refresh_service

router = APIRouter(prefix="/refresh", tags=["refresh"])


class StartJobResponse(BaseModel):
    id: int
    kind: str
    status: str


@router.get("/kinds")
def get_kinds() -> dict:
    return {"kinds": refresh_service.list_kinds()}


@router.get("/jobs")
def get_jobs(
    kind: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
) -> dict:
    return {"jobs": refresh_service.list_jobs(kind=kind, limit=limit)}


@router.get("/jobs/{job_id}")
def get_job(job_id: int = Path(..., ge=1)) -> dict:
    job = refresh_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.get("/latest")
def get_latest_per_kind() -> dict:
    return refresh_service.latest_per_kind()


@router.get("/quality")
def get_quality() -> dict:
    return refresh_service.quality_snapshot()


@router.post("/{kind}", response_model=StartJobResponse)
def start_job(kind: str) -> dict:
    try:
        return refresh_service.start_job(kind)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except refresh_service.KindAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc))
