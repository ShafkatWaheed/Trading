"""FastAPI entry point.

Run with:  uvicorn api.main:app --port 8000 --reload
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import HealthResponse
from api.routes import (
    market, discover, stocks, backtest, agent, watchlist, compare, alerts, simulation,
    data_sources, universe, news_impact, graph, freshness, earnings, graph_relevance,
)

app = FastAPI(
    title="Trading Analysis API",
    version="0.1.0",
    description="Stock research and analysis. Backend for the Next.js frontend.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router)
app.include_router(discover.router)
app.include_router(stocks.router)
app.include_router(backtest.router)
app.include_router(agent.router)
app.include_router(watchlist.router)
app.include_router(compare.router)
app.include_router(alerts.router)
app.include_router(simulation.router)
app.include_router(data_sources.router)
app.include_router(universe.router)
app.include_router(news_impact.router)
app.include_router(graph.router)
app.include_router(freshness.router)
app.include_router(earnings.router)
app.include_router(graph_relevance.router)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> dict:
    return {"status": "ok", "service": "trading-api", "version": "0.1.0"}


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "Trading Analysis API",
        "docs": "/docs",
        "health": "/health",
    }
