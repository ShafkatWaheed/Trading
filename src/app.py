"""FastAPI app: REST API for stock analysis and reports."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.utils.db import (
    init_db, get_reports, get_report_by_id,
    get_watchlist, add_watchlist_item, remove_watchlist_item,
    get_alerts,
)
from src.orchestrator import analyze_stock

app = FastAPI(
    title="Trading Analysis API",
    description="Stock research and analysis tool for generating trading reports",
    version="0.1.0",
)


@app.on_event("startup")
def startup() -> None:
    init_db()


# --- Health ---

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# --- Reports ---

@app.get("/reports")
def list_reports(symbol: str | None = None, report_type: str | None = None, limit: int = 20) -> list[dict]:
    return get_reports(symbol=symbol, report_type=report_type, limit=limit)


@app.post("/analyze/{symbol}")
def run_analysis(symbol: str) -> dict:
    report = analyze_stock(symbol.upper(), export=True)
    return {
        "symbol": report.symbol,
        "name": report.name,
        "verdict": report.verdict.value,
        "confidence": report.confidence,
        "risk_rating": report.risk_rating.value,
        "current_price": str(report.current_price),
        "sentiment_score": str(report.sentiment_score),
        "reasoning": report.reasoning,
        "risks": report.risks,
        "sections": [
            {"title": s.title, "content": s.content, "data": s.data}
            for s in report.sections
        ],
        "disclaimer": report.DISCLAIMER,
    }


@app.get("/reports/{report_id}")
def get_report(report_id: int) -> dict:
    report = get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


# --- Watchlist ---

@app.get("/watchlist")
def list_watchlist() -> list[dict]:
    return get_watchlist()


class WatchlistItem(BaseModel):
    symbol: str
    name: str = ""


@app.post("/watchlist")
def add_to_watchlist(item: WatchlistItem) -> dict:
    add_watchlist_item(item.symbol, item.name)
    return {"status": "added", "symbol": item.symbol.upper()}


@app.delete("/watchlist/{symbol}")
def remove_from_watchlist(symbol: str) -> dict:
    remove_watchlist_item(symbol)
    return {"status": "removed", "symbol": symbol.upper()}


@app.get("/alerts")
def list_alerts(symbol: str | None = None, limit: int = 50) -> list[dict]:
    return get_alerts(symbol=symbol, limit=limit)


@app.post("/scan")
def trigger_scan() -> dict:
    from src.scheduler import run_watchlist_scan
    return run_watchlist_scan()
