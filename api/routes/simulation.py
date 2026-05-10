"""Simulation replay routes."""
from fastapi import APIRouter, Query, HTTPException

from api.services import simulation_service, portfolio_sim_agent_service
from api.schemas import PortfolioSimRequest, PortfolioSimResponse

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.post("/portfolio-agent", response_model=PortfolioSimResponse)
def portfolio_agent(req: PortfolioSimRequest) -> dict:
    return portfolio_sim_agent_service.run_walk_forward(
        start_date=req.start_date,
        end_date=req.end_date,
        cycle_days=req.cycle_days,
        initial_capital=req.initial_capital,
        max_positions=req.max_positions,
        min_agents=req.min_agents,
        top_n=req.top_n,
        position_size_pct=req.position_size_pct,
    )


@router.get("/runs")
def list_runs() -> dict:
    return {"runs": simulation_service.list_runs()}


@router.get("/cycles")
def list_cycles(run_id: str = Query(..., min_length=1)) -> dict:
    return {"cycles": simulation_service.list_cycles(run_id)}


@router.get("/step")
def get_step(
    run_id: str = Query(..., min_length=1),
    cycle_date: str = Query(..., min_length=1),
    step: str = Query(..., regex="^(market_pulse|discover|deep_dive|trades|ai_decision)$"),
) -> dict:
    data = simulation_service.get_step(run_id, cycle_date, step)
    if data is None:
        raise HTTPException(status_code=404, detail="No data for this step")
    return {"data": data}
