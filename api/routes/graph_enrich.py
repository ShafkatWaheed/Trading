"""On-demand graph enrichment endpoints.

POST /graph/enrich/{symbol}          — kick a 10-K-mining job for one symbol
GET  /graph/enrich/{symbol}/status   — poll for progress / completion

Used by the Deep Dive page's "Build connections" button when the
neighborhood section is sparse (few suppliers/customers/peers).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.services import graph_enrich_service


router = APIRouter(prefix="/graph/enrich", tags=["graph"])


def _check_symbol(symbol: str) -> str:
    """Reject obviously bad symbols early."""
    s = symbol.strip().upper()
    if not s or len(s) > 8 or not s.replace("-", "").replace(".", "").isalnum():
        raise HTTPException(status_code=400, detail="invalid symbol")
    return s


@router.post("/{symbol}")
def kick_enrich(symbol: str) -> dict:
    return graph_enrich_service.kick_enrichment(_check_symbol(symbol))


@router.get("/{symbol}/status")
def status(symbol: str) -> dict:
    return graph_enrich_service.get_enrichment_status(_check_symbol(symbol))
