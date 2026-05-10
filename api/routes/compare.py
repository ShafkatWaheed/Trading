"""Multi-stock comparison route."""
from fastapi import APIRouter, HTTPException, Query

from api.schemas import CompareResponse
from api.services import compare_service

router = APIRouter(prefix="/compare", tags=["compare"])


@router.get("", response_model=CompareResponse)
def compare(
    symbols: str = Query(..., description="Comma-separated tickers, e.g. AAPL,MSFT,NVDA"),
    period: str = Query("3M", regex="^(1D|1W|1M|3M|6M|1Y)$"),
    force: bool = Query(False, description="Bypass the 24h per-symbol cache"),
) -> dict:
    syms = [s for s in (symbols or "").split(",") if s.strip()]
    if not syms:
        raise HTTPException(status_code=400, detail="Provide at least one ticker")
    if len(syms) > 6:
        raise HTTPException(status_code=400, detail="Compare up to 6 tickers at a time")
    return compare_service.compare(syms, period=period, force=force)
