"""Data Sources routes — surface API rate-limit status to the React frontend."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from api.schemas import DataSourcesResponse
from src.utils.rate_limit import get_rate_limit_status

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


@router.get("/rate-limits", response_model=DataSourcesResponse)
def rate_limits() -> dict:
    statuses = get_rate_limit_status()
    return {
        "sources": [asdict(s) for s in statuses],
        "any_limited": any(s.is_limited for s in statuses),
    }
