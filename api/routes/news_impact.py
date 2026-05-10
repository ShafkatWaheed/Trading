"""News-impact endpoint — POST a headline, get ranked stocks back."""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas import NewsImpactRequest, NewsImpactResponse
from api.services import news_impact_service

router = APIRouter(prefix="/news-impact", tags=["news-impact"])


@router.post("", response_model=NewsImpactResponse)
def analyze(req: NewsImpactRequest) -> dict:
    return news_impact_service.analyze_news(req.text)
