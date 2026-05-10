"""Earnings report explainer route."""
from fastapi import APIRouter, HTTPException

from api.schemas import EarningsExplainRequest, EarningsExplainResponse
from api.services import earnings_explainer_service

router = APIRouter(prefix="/earnings", tags=["earnings"])


@router.post("/explain", response_model=EarningsExplainResponse)
def explain(req: EarningsExplainRequest) -> dict:
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Empty report text")
    try:
        return earnings_explainer_service.explain_earnings(req.symbol, req.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Explainer failed: {e}")
