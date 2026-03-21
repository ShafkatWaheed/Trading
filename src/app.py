"""FastAPI app: REST API for stock analysis and reports."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.utils.db import init_db, get_reports

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


@app.get("/reports/{report_id}")
def get_report(report_id: int) -> dict:
    from src.utils.db import get_connection
    conn = get_connection()
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return dict(row)


# --- Watchlist ---

@app.get("/watchlist")
def get_watchlist() -> list[dict]:
    from src.utils.db import get_connection
    conn = get_connection()
    rows = conn.execute("SELECT * FROM watchlist ORDER BY added_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


class WatchlistItem(BaseModel):
    symbol: str
    name: str = ""


@app.post("/watchlist")
def add_to_watchlist(item: WatchlistItem) -> dict:
    from datetime import datetime
    from src.utils.db import get_connection
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO watchlist (symbol, name, added_at) VALUES (?, ?, ?)",
        (item.symbol.upper(), item.name, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return {"status": "added", "symbol": item.symbol.upper()}


@app.delete("/watchlist/{symbol}")
def remove_from_watchlist(symbol: str) -> dict:
    from src.utils.db import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper(),))
    conn.commit()
    conn.close()
    return {"status": "removed", "symbol": symbol.upper()}
