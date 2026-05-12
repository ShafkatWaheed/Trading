"""Stock routes — deep dive + search."""
from fastapi import APIRouter, HTTPException, Query

from api.schemas import (
    AnalystConsensusResponse, BenchmarksResponse, BubbleScoreResponse,
    BullNarrativeResponse, CatalystCalendarResponse, DeepDiveResponse,
    NewsFeedResponse, PeerValuationResponse, RecommendationResponse,
    RiskNarrativeResponse, SignalEvidenceResponse, SmartMoneyResponse,
    StockSearchResult,
)
from api.services import (
    analyst_consensus_service, benchmarks_service, bubble_score_service,
    bull_narrative_service, catalyst_calendar_service, deep_dive_service,
    discover_service, news_feed_service, peer_valuation_service,
    recommendation_service, risk_narrative_service, signal_evidence_service,
    smart_money_service,
)

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


@router.get("/{ticker}/bubble-score", response_model=BubbleScoreResponse)
def bubble_score(
    ticker: str,
    force: bool = Query(False, description="Bypass the 6h cache and recompute"),
) -> dict:
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    try:
        return bubble_score_service.get_bubble_score(ticker, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bubble score failed: {e}")


@router.get("/{ticker}/bull-narrative", response_model=BullNarrativeResponse)
def bull_narrative(
    ticker: str,
    force: bool = Query(False, description="Bypass the 24h cache and regenerate"),
) -> dict:
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    try:
        return bull_narrative_service.get_bull_narrative(ticker, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bull narrative failed: {e}")


@router.get("/{ticker}/analyst-consensus", response_model=AnalystConsensusResponse)
def analyst_consensus(
    ticker: str,
    force: bool = Query(False, description="Bypass the 12h cache and refetch"),
) -> dict:
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    try:
        return analyst_consensus_service.get_analyst_consensus(ticker, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analyst consensus failed: {e}")


@router.get("/{ticker}/peer-valuation", response_model=PeerValuationResponse)
def peer_valuation(
    ticker: str,
    force: bool = Query(False, description="Bypass the 6h cache and recompute"),
) -> dict:
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    try:
        return peer_valuation_service.get_peer_valuation(ticker, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Peer valuation failed: {e}")


@router.get("/{ticker}/smart-money", response_model=SmartMoneyResponse)
def smart_money(
    ticker: str,
    force: bool = Query(False, description="Bypass the 6h cache and recompute"),
) -> dict:
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    try:
        return smart_money_service.get_smart_money(ticker, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Smart money failed: {e}")


@router.get("/{ticker}/news-feed", response_model=NewsFeedResponse)
def news_feed(
    ticker: str,
    force: bool = Query(False, description="Bypass the 30m cache"),
) -> dict:
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    try:
        return news_feed_service.get_news_feed(ticker, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"News feed failed: {e}")


@router.get("/{ticker}/catalyst-calendar", response_model=CatalystCalendarResponse)
def catalyst_calendar(
    ticker: str,
    force: bool = Query(False, description="Bypass the 6h cache"),
) -> dict:
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    try:
        return catalyst_calendar_service.get_catalyst_calendar(ticker, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Catalyst calendar failed: {e}")


@router.get("/{ticker}/benchmarks", response_model=BenchmarksResponse)
def benchmarks(
    ticker: str,
    period: str = Query("3M", regex="^(1D|1W|1M|3M|6M|1Y)$"),
    force: bool = Query(False),
) -> dict:
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    try:
        return benchmarks_service.get_benchmarks(ticker, period=period, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Benchmarks failed: {e}")


@router.get("/{ticker}/recommendation", response_model=RecommendationResponse)
def recommendation(
    ticker: str,
    force: bool = Query(False, description="Bypass cache and resynthesize"),
) -> dict:
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    try:
        return recommendation_service.get_recommendation(ticker, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recommendation failed: {e}")


@router.get("/{ticker}/signal-evidence", response_model=SignalEvidenceResponse)
def signal_evidence(
    ticker: str,
    force: bool = Query(False, description="Bypass the 24h cache"),
) -> dict:
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    try:
        return signal_evidence_service.get_signal_evidence(ticker, force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Signal evidence failed: {e}")
