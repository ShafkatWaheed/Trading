"""Sector-level informed-flow tapes — 13F + Congress aggregates by sector.

These feed the market pulse page ("Institutional & political flows" section)
and brief Phase A. Both responses are cached 6h.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from api.schemas import SectorTapeResponse
from api.services import smart_money_service, congress_signal_service

router = APIRouter(prefix="", tags=["flows"])


@router.get("/smart-money/sector-tape", response_model=SectorTapeResponse)
def smart_money_sector_tape(
    window: int = Query(180, description="Trailing window in days. 90, 180, or 365."),
    force: bool = Query(False, description="Bypass cache."),
):
    """13F net dollar flow per sector over the trailing window.

    Source: `institution_holdings` table. Needs 2+ sequential 13F snapshots per
    institution within the window to compute deltas — falls back to a
    coverage_note when data is insufficient.
    """
    return smart_money_service.get_sector_tape(window, force=force)


@router.get("/congress/sector-tape", response_model=SectorTapeResponse)
def congress_sector_tape(
    window: int = Query(180, description="Trailing window in days. 90, 180, or 365."),
    force: bool = Query(False, description="Bypass cache."),
):
    """Congressional trade counts per sector over the trailing window.

    Source: Capitol Trades scrape via `CongressDataProvider`. Top ~20 traded
    symbols → per-symbol summaries → sector rollup. 45-day STOCK Act
    disclosure lag applies.
    """
    return congress_signal_service.get_sector_tape(window, force=force)
