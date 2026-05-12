"""Backtest routes."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api.schemas import (
    BacktestRequest, BacktestResponse,
    SignalCatalogResponse, AllSignalsResponse, SingleBacktestResponse,
    MultiStockResponse,
    PortfolioSimRequest, PortfolioSimResponse,
    AiAnalystRequest, AiAnalystResponse,
    AiAnalystMultiRequest, AiAnalystMultiResponse,
)
from api.services import backtest_service, portfolio_sim_service, ai_analyst_service

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/signals", response_model=SignalCatalogResponse)
def signals_catalog() -> dict:
    return backtest_service.list_signals()


@router.post("", response_model=BacktestResponse)
def run_backtest(req: BacktestRequest) -> dict:
    try:
        return backtest_service.run_signal_backtest(req.symbol, req.signal, req.hold_days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")


@router.get("/all", response_model=AllSignalsResponse)
def backtest_all(
    symbol: str = Query(..., min_length=1, max_length=10),
    period: str = Query("1M", regex="^(1D|1W|1M|3M|6M|1Y)$"),
    category: str = Query("All Signals"),
) -> dict:
    try:
        return backtest_service.run_all_signals(symbol, period=period, category=category)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")


@router.get("/single", response_model=SingleBacktestResponse)
def backtest_single(
    symbol: str = Query(..., min_length=1, max_length=10),
    signal: str = Query(...),
    period: str = Query("1M", regex="^(1D|1W|1M|3M|6M|1Y)$"),
) -> dict:
    try:
        return backtest_service.run_single(symbol, signal, period=period)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")


class MultiStockRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=8)
    signal: str
    period: str = Field("1M", pattern="^(1D|1W|1M|3M|6M|1Y)$")


@router.post("/multi-stock", response_model=MultiStockResponse)
def backtest_multi(req: MultiStockRequest) -> dict:
    try:
        return backtest_service.run_multi_stock(req.symbols, req.signal, period=req.period)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")


@router.post("/portfolio", response_model=PortfolioSimResponse)
def portfolio_sim(req: PortfolioSimRequest) -> dict:
    try:
        return portfolio_sim_service.run_portfolio_simulation(
            req.symbols, req.strategy,
            initial_capital=req.initial_capital,
            position_size_pct=req.position_size_pct,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Portfolio sim failed: {e}")


@router.post("/ai-analyst", response_model=AiAnalystResponse)
def ai_analyst(req: AiAnalystRequest) -> dict:
    try:
        return ai_analyst_service.run_ai_backtest(
            req.symbol, period=req.period, cycles=req.cycles, mode=req.mode,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI backtest failed: {e}")


@router.post("/ai-analyst-multi", response_model=AiAnalystMultiResponse)
def ai_analyst_multi(req: AiAnalystMultiRequest) -> dict:
    try:
        return ai_analyst_service.run_ai_backtest_multi(
            req.symbols, period=req.period, cycles=req.cycles, mode=req.mode,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI multi backtest failed: {e}")
