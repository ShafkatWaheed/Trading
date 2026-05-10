"""Stock routes — deep dive + search."""
from fastapi import APIRouter, HTTPException, Query

from api.schemas import DeepDiveResponse, RiskNarrativeResponse, StockSearchResult
from api.services import deep_dive_service, discover_service, risk_narrative_service

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/search", response_model=list[StockSearchResult])
def search(q: str = Query(..., min_length=1)) -> list[dict]:
    """Search known stocks by ticker or name fragment."""
    meta = discover_service._load_stock_meta()
    q_upper = q.upper()
    q_lower = q.lower()
    results = []
    for sym, info in meta.items():
        if q_upper in sym or q_lower in (info.get("name") or "").lower():
            results.append({"symbol": sym, **info})
            if len(results) >= 20:
                break
    return results


@router.get("/{ticker}/deep-dive", response_model=DeepDiveResponse)
def deep_dive(
    ticker: str,
    period: str = Query("3M", regex="^(1D|1W|1M|3M|6M|1Y)$"),
    signal_filter: str = Query("all", regex="^(all|buy|sell|strong)$"),
    account_size: float = Query(10000, ge=100, le=10000000),
    risk_pct: float = Query(2, ge=0.1, le=10),
    force: bool = Query(False, description="Bypass the 24h cache and recompute"),
) -> dict:
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    try:
        return deep_dive_service.get_deep_dive(
            ticker, period=period, signal_filter=signal_filter,
            account_size=account_size, risk_pct=risk_pct, force=force,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.get("/{ticker}/risk-narrative", response_model=RiskNarrativeResponse)
def risk_narrative(
    ticker: str,
    force: bool = Query(False, description="Bypass the 24h cache and regenerate"),
) -> dict:
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    try:
        return risk_narrative_service.get_risk_narrative(ticker, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Risk narrative failed: {e}")
