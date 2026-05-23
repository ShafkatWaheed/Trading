"""Stock routes — deep dive + search."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from api.schemas import (
    AnalystConsensusResponse, BenchmarksResponse, BubbleScoreResponse,
    BullNarrativeResponse, CatalystCalendarResponse, DeepDiveBundleResponse,
    DeepDiveResponse, EntityMatchesResponse, NewsFeedResponse,
    PeerValuationResponse, RecommendationResponse, RiskNarrativeResponse,
    SignalEvidenceResponse, SmartMoneyResponse, StockInformationResponse,
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


@router.get("/{ticker}/deep-dive-bundle", response_model=DeepDiveBundleResponse)
def deep_dive_bundle(
    ticker: str,
    period: str = Query("3M", regex="^(1D|1W|1M|3M|6M|1Y)$"),
    signal_filter: str = Query("all", regex="^(all|buy|sell|strong)$"),
    account_size: float = Query(10000, ge=100, le=10000000),
    risk_pct: float = Query(2, ge=0.1, le=10),
    force: bool = Query(False, description="Bypass caches and recompute everything"),
) -> dict:
    """Fetch deep-dive + 4 core sidecar payloads in a single request.

    The 5 services run concurrently. The deep-dive itself is the slowest;
    bubble/peer/analyst/benchmarks each take a few hundred ms, so concurrency
    means the bundle effectively costs the deep-dive call alone.

    Each sidecar is wrapped in try/except — a single failure surfaces in
    `errors[<name>]` and the rest still come back. The frontend uses this to
    prime the React Query cache for each child query.
    """
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")

    # The deep-dive is the largest payload and the prerequisite of useful page
    # render — run it inline and bail if it fails.
    try:
        dd = deep_dive_service.get_deep_dive(
            ticker, period=period, signal_filter=signal_filter,
            account_size=account_size, risk_pct=risk_pct, force=force,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    errors: dict[str, str] = {}

    def _safe(name: str, fn):
        try:
            return fn()
        except Exception as e:
            errors[name] = str(e)
            return None

    jobs = {
        "bubble_score":      lambda: bubble_score_service.get_bubble_score(ticker, force=force),
        "peer_valuation":    lambda: peer_valuation_service.get_peer_valuation(ticker, force=force),
        "analyst_consensus": lambda: analyst_consensus_service.get_analyst_consensus(ticker, force=force),
        "benchmarks":        lambda: benchmarks_service.get_benchmarks(ticker, period=period, force=force),
    }

    results: dict[str, dict | None] = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {name: pool.submit(_safe, name, fn) for name, fn in jobs.items()}
        for name, fut in futures.items():
            results[name] = fut.result()

    return {
        "deep_dive": dd,
        "bubble_score":      results["bubble_score"],
        "peer_valuation":    results["peer_valuation"],
        "analyst_consensus": results["analyst_consensus"],
        "benchmarks":        results["benchmarks"],
        "period":            period,
        "last_updated":      datetime.utcnow().isoformat() + "Z",
        "errors":            errors,
    }


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


@router.get("/{ticker}/fda-catalysts", response_model=StockInformationResponse)
def get_fda_catalysts(ticker: str) -> dict:
    """Wave 2 Phase D: FDA Catalysts card — openFDA drug applications by sponsor."""
    from api.services.fda_catalysts_service import get_fda_catalysts_for_ticker
    return get_fda_catalysts_for_ticker(ticker.upper())


@router.get("/{ticker}/backlog", response_model=StockInformationResponse)
def get_backlog(ticker: str) -> dict:
    """Wave 2 Phase E: Backlog card — USAspending government contracts by UEI."""
    from api.services.backlog_service import get_backlog_for_ticker
    return get_backlog_for_ticker(ticker.upper())


@router.get("/{ticker}/litigation", response_model=StockInformationResponse)
def get_litigation(ticker: str) -> dict:
    """Wave 2 Phase F: Litigation card — ITC §337 investigations by party name."""
    from api.services.litigation_service import get_litigation_for_ticker
    return get_litigation_for_ticker(ticker.upper())


@router.get("/{ticker}/exec-changes", response_model=StockInformationResponse)
def get_exec_changes(ticker: str) -> dict:
    """Wave 2 Phase G: Executive Changes card — 8-K Item 5.02 events."""
    from api.services.exec_changes_service import get_exec_changes_for_ticker
    return get_exec_changes_for_ticker(ticker.upper())


@router.get("/{ticker}/entity-matches", response_model=EntityMatchesResponse)
def get_entity_matches(ticker: str) -> dict:
    """Wave 2 debug card: show how each data source resolved its names to this ticker."""
    from api.services.entity_matches_service import get_matches_for_ticker
    return get_matches_for_ticker(ticker.upper())
