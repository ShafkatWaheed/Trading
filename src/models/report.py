from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class RiskRating(Enum):
    LOW = 1
    LOW_MODERATE = 2
    MODERATE = 3
    MODERATE_HIGH = 4
    HIGH = 5


class Verdict(Enum):
    STRONG_BUY = "Strong Buy"
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"
    STRONG_SELL = "Strong Sell"


class ReportSection(BaseModel):
    title: str
    content: str
    data: dict = Field(default_factory=dict)


class Report(BaseModel):
    symbol: str
    name: str
    generated_at: datetime
    verdict: Verdict
    confidence: str
    risk_rating: RiskRating
    current_price: Decimal
    sentiment_score: Decimal
    sections: list[ReportSection] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)

    DISCLAIMER: str = (
        "This is AI-generated analysis for informational purposes only. "
        "Not financial advice."
    )
