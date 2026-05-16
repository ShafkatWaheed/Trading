"""Context Search route — free-text → ranked stocks (Tier 1).

POST /context-search { "text": "...", "limit": 40 }
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.services import context_search_service

router = APIRouter(prefix="/context-search", tags=["context-search"])


class ContextSearchRequest(BaseModel):
    text: str = Field(..., min_length=2, max_length=2000)
    limit: int = Field(40, ge=1, le=200)


@router.post("")
def search(req: ContextSearchRequest) -> dict:
    return context_search_service.search(req.text, limit=req.limit)
