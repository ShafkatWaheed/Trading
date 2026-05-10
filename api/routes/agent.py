"""Agent routes."""
from fastapi import APIRouter, Query

from api.schemas import (
    AgentStatus, AgentDecision, AgentConfig, AgentConfigUpdate, AgentResetRequest,
    AgentPersonalitiesResponse, AgentPosition, AgentEquityResponse,
    AgentCycleResult, MultiAgentResult, MultiAgentRunRequest,
    CotResponse, AgentLifecycle,
    PortfolioAgentRequest, PortfolioAgentResponse,
    PortfolioExecuteRequest, PortfolioExecuteResponse,
)
from api.services import agent_service, portfolio_agent_service

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/status", response_model=AgentStatus)
def status() -> dict:
    return agent_service.get_status()


@router.get("/decisions", response_model=list[AgentDecision])
def decisions(limit: int = Query(30, ge=1, le=200)) -> list[dict]:
    return agent_service.get_recent_decisions(limit=limit)


@router.get("/config", response_model=AgentConfig)
def get_config() -> dict:
    return agent_service.get_config()


@router.patch("/config", response_model=AgentConfig)
def update_config(update: AgentConfigUpdate) -> dict:
    return agent_service.update_config(**update.model_dump(exclude_none=True))


@router.post("/reset", response_model=AgentConfig)
def reset(req: AgentResetRequest) -> dict:
    return agent_service.reset(**req.model_dump())


@router.get("/personalities", response_model=AgentPersonalitiesResponse)
def personalities() -> dict:
    return agent_service.get_personalities()


@router.get("/positions", response_model=list[AgentPosition])
def positions() -> list[dict]:
    return agent_service.list_open_positions()


@router.get("/equity", response_model=AgentEquityResponse)
def equity() -> dict:
    return agent_service.get_equity_curve()


@router.post("/run/single", response_model=AgentCycleResult)
def run_single() -> dict:
    return agent_service.run_single_cycle()


@router.post("/run/multi", response_model=MultiAgentResult)
def run_multi(req: MultiAgentRunRequest) -> dict:
    return agent_service.run_multi_cycle(rm_picks=req.rm_picks, min_score=req.min_score)


@router.get("/chain-of-thought", response_model=CotResponse)
def chain_of_thought(limit_runs: int = Query(5, ge=1, le=20)) -> dict:
    return agent_service.get_chain_of_thought(limit_runs=limit_runs)


@router.post("/stop", response_model=AgentLifecycle)
def stop() -> dict:
    return agent_service.stop_agent()


@router.post("/resume", response_model=AgentLifecycle)
def resume() -> dict:
    return agent_service.resume_agent()


@router.post("/portfolio-pick", response_model=PortfolioAgentResponse)
def portfolio_pick(req: PortfolioAgentRequest = PortfolioAgentRequest()) -> dict:
    return portfolio_agent_service.run_portfolio_pick(
        top_n=req.top_n, min_agents=req.min_agents,
    )


@router.post("/portfolio-pick/execute", response_model=PortfolioExecuteResponse)
def portfolio_pick_execute(req: PortfolioExecuteRequest) -> dict:
    return portfolio_agent_service.execute_picks(
        symbols=req.symbols, reasons_by_symbol=req.reasons,
    )
