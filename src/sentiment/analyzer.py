"""News sentiment analysis using Tavily and Exa search results."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class NewsArticle:
    headline: str
    source: str
    url: str
    published: str
    sentiment: str  # positive / neutral / negative
    sentiment_score: Decimal  # -1.0 to 1.0
    takeaway: str


@dataclass
class SentimentResult:
    symbol: str
    articles: list[NewsArticle] = field(default_factory=list)
    overall_score: Decimal = Decimal("0")
    overall_sentiment: str = "neutral"
    summary: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def compute_overall(self) -> None:
        if not self.articles:
            self.overall_score = Decimal("0")
            self.overall_sentiment = "neutral"
            return

        total = sum(a.sentiment_score for a in self.articles)
        self.overall_score = total / len(self.articles)

        if self.overall_score > Decimal("0.2"):
            self.overall_sentiment = "positive"
        elif self.overall_score < Decimal("-0.2"):
            self.overall_sentiment = "negative"
        else:
            self.overall_sentiment = "neutral"


def score_headline(headline: str) -> tuple[str, Decimal]:
    """Simple keyword-based sentiment scoring.

    Returns (sentiment_label, score).
    For production, replace with a proper NLP model.
    """
    headline_lower = headline.lower()

    bullish_words = [
        "beat", "surge", "upgrade", "rally", "growth", "record", "buy",
        "outperform", "bullish", "profit", "strong", "exceeds", "positive",
        "raise", "boost", "gain", "soar", "breakout", "dividend",
    ]
    bearish_words = [
        "miss", "drop", "downgrade", "fall", "loss", "sell", "decline",
        "bearish", "weak", "risk", "warning", "cut", "negative", "crash",
        "plunge", "layoff", "debt", "lawsuit", "investigation",
    ]

    bull_count = sum(1 for w in bullish_words if w in headline_lower)
    bear_count = sum(1 for w in bearish_words if w in headline_lower)

    if bull_count > bear_count:
        score = Decimal(str(min(bull_count * 0.25, 1.0)))
        return "positive", score
    elif bear_count > bull_count:
        score = Decimal(str(max(-bear_count * 0.25, -1.0)))
        return "negative", score
    return "neutral", Decimal("0")
