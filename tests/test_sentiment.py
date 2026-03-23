"""Unit tests for sentiment analysis module."""

from decimal import Decimal

from src.sentiment.analyzer import score_headline, NewsArticle, SentimentResult


def _make_article(headline: str) -> NewsArticle:
    """Build a NewsArticle from a headline, auto-scoring it."""
    label, score = score_headline(headline)
    return NewsArticle(
        headline=headline,
        source="TestSource",
        url="https://example.com/article",
        published="2026-03-22T12:00:00Z",
        sentiment=label,
        sentiment_score=score,
        takeaway=headline,
    )


def test_bullish_headlines() -> None:
    """Headlines with bullish keywords should produce a positive score."""
    headlines = [
        "Stock surges after record earnings beat",
        "Company earnings beat expectations, profit soars",
        "Analysts upgrade stock as growth accelerates",
    ]
    for headline in headlines:
        label, score = score_headline(headline)
        assert label == "positive", (
            f"Expected positive for '{headline}', got {label}"
        )
        assert score > Decimal("0"), (
            f"Expected positive score for '{headline}', got {score}"
        )


def test_bearish_headlines() -> None:
    """Headlines with bearish keywords should produce a negative score."""
    headlines = [
        "Stock crashes after missed earnings",
        "Company announces massive layoff amid declining sales",
        "Analysts downgrade stock, warning of debt risk",
    ]
    for headline in headlines:
        label, score = score_headline(headline)
        assert label == "negative", (
            f"Expected negative for '{headline}', got {label}"
        )
        assert score < Decimal("0"), (
            f"Expected negative score for '{headline}', got {score}"
        )


def test_neutral_headlines() -> None:
    """Headlines with no strong sentiment keywords should score near zero."""
    headlines = [
        "Company announces annual shareholder meeting",
        "CEO to present at upcoming conference",
        "Quarterly report scheduled for next month",
    ]
    for headline in headlines:
        label, score = score_headline(headline)
        assert label == "neutral", (
            f"Expected neutral for '{headline}', got {label}"
        )
        assert score == Decimal("0"), (
            f"Expected zero score for '{headline}', got {score}"
        )


def test_empty_articles() -> None:
    """SentimentResult with no articles should produce neutral overall."""
    result = SentimentResult(symbol="TEST")
    result.compute_overall()

    assert result.overall_score == Decimal("0"), (
        f"Empty articles should give score 0, got {result.overall_score}"
    )
    assert result.overall_sentiment == "neutral", (
        f"Empty articles should be neutral, got {result.overall_sentiment}"
    )


def test_overall_positive_sentiment() -> None:
    """Multiple bullish articles should produce positive overall sentiment."""
    articles = [
        _make_article("Stock surges on strong earnings beat"),
        _make_article("Revenue growth exceeds expectations"),
        _make_article("Analysts raise price targets after bullish outlook"),
    ]
    result = SentimentResult(symbol="BULL", articles=articles)
    result.compute_overall()

    assert result.overall_score > Decimal("0.2"), (
        f"Bullish articles should give positive overall, got {result.overall_score}"
    )
    assert result.overall_sentiment == "positive", (
        f"Expected positive sentiment, got {result.overall_sentiment}"
    )


def test_overall_negative_sentiment() -> None:
    """Multiple bearish articles should produce negative overall sentiment."""
    articles = [
        _make_article("Stock crashes on missed earnings"),
        _make_article("Company announces layoff and cost cut"),
        _make_article("Downgrade warning as debt risk rises"),
    ]
    result = SentimentResult(symbol="BEAR", articles=articles)
    result.compute_overall()

    assert result.overall_score < Decimal("-0.2"), (
        f"Bearish articles should give negative overall, got {result.overall_score}"
    )
    assert result.overall_sentiment == "negative", (
        f"Expected negative sentiment, got {result.overall_sentiment}"
    )
