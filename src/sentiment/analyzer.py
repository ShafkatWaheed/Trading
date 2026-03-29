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


def score_headlines_batch(headlines: list[str]) -> list[tuple[str, Decimal]]:
    """Score multiple headlines in a single Claude call. Much faster than one-by-one."""
    if not headlines:
        return []

    batch_result = _score_batch_with_claude(headlines)
    if batch_result and len(batch_result) == len(headlines):
        return batch_result

    # Fallback: keyword scoring for all
    return [_score_with_keywords(h) for h in headlines]


def score_headline(headline: str) -> tuple[str, Decimal]:
    """Score single headline. Uses Claude AI with keyword fallback."""
    ai_result = _score_with_claude(headline)
    if ai_result:
        return ai_result
    return _score_with_keywords(headline)


def _score_batch_with_claude(headlines: list[str]) -> list[tuple[str, Decimal]] | None:
    """Score all headlines in one Claude call. Returns list of (label, score) or None."""
    import subprocess
    import os
    import json

    try:
        numbered = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines))

        prompt = f"""Score each financial news headline for stock trading sentiment.

{numbered}

For each headline, determine:
- Is this good or bad for the stock price?
- How strong is the signal? Use the FULL range from -1.0 to +1.0
- Score 0.00 only for truly neutral headlines (routine meetings, no-impact updates)

Respond with ONLY a JSON array, one object per headline, in order:
[
  {{"sentiment": "positive", "score": 0.65}},
  {{"sentiment": "negative", "score": -0.40}},
  {{"sentiment": "neutral", "score": 0.00}}
]

Score guide: earnings beat +0.5 to +0.8, CEO fired -0.6 to -0.8, analyst upgrade +0.3 to +0.5, routine update 0.0, guidance raise +0.4 to +0.7, layoffs -0.3 to -0.6"""

        env = dict(os.environ)
        env.pop("CLAUDECODE", None)

        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", "haiku"],
            capture_output=True, text=True, timeout=30, env=env,
        )
        response = proc.stdout.strip()

        # Parse JSON array
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            data = json.loads(response[start:end])
            results = []
            for item in data:
                sentiment = item.get("sentiment", "neutral")
                score = float(item.get("score", 0))
                score = max(-1.0, min(1.0, score))
                results.append((sentiment, Decimal(str(round(score, 5)))))
            return results

    except Exception:
        pass

    return None


def _score_with_claude(headline: str) -> tuple[str, Decimal] | None:
    """Score a headline using Claude CLI. Returns None on failure."""
    import subprocess
    import os
    import json

    try:
        prompt = f"""Score this financial news headline for stock trading sentiment.

Headline: "{headline}"

Consider:
- Is this good or bad for the stock price?
- How strong is the sentiment? (major event vs minor update)
- Would a trader react to this?

Respond in EXACTLY this JSON format (no other text):
{{"sentiment": "positive" or "negative" or "neutral", "score": 0.00, "reason": "5 words max"}}

Score range: -1.0 (extremely bearish) to +1.0 (extremely bullish). Use the full range.
Examples: earnings beat +0.65, CEO resigns -0.70, stock split announced +0.30, routine meeting 0.00"""

        env = dict(os.environ)
        env.pop("CLAUDECODE", None)

        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", "haiku"],
            capture_output=True, text=True, timeout=15, env=env,
        )
        response = proc.stdout.strip()

        # Parse JSON
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(response[start:end])
            sentiment = data.get("sentiment", "neutral")
            score = float(data.get("score", 0))
            score = max(-1.0, min(1.0, score))
            return sentiment, Decimal(str(round(score, 5)))

    except Exception:
        pass

    return None


def _score_with_keywords(headline: str) -> tuple[str, Decimal]:
    """Fallback keyword-based sentiment scoring."""
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
    total_words = len(headline_lower.split())

    if bull_count > bear_count:
        intensity = bull_count / max(total_words, 1)
        base = min(bull_count * 0.15, 0.8)
        score = round(base + intensity * 0.2, 5)
        return "positive", Decimal(str(min(score, 1.0)))
    elif bear_count > bull_count:
        intensity = bear_count / max(total_words, 1)
        base = min(bear_count * 0.15, 0.8)
        score = round(-(base + intensity * 0.2), 5)
        return "negative", Decimal(str(max(score, -1.0)))
    return "neutral", Decimal("0")
