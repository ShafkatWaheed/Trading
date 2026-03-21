"""Tests for sentiment scoring."""

from decimal import Decimal

from src.sentiment.analyzer import score_headline, SentimentResult, NewsArticle


def test_bullish_headline():
    sentiment, score = score_headline("Apple beats earnings expectations, stock surges")
    assert sentiment == "positive"
    assert score > 0


def test_bearish_headline():
    sentiment, score = score_headline("Company reports loss, announces layoffs amid declining revenue")
    assert sentiment == "negative"
    assert score < 0


def test_neutral_headline():
    sentiment, score = score_headline("Company announces new office location")
    assert sentiment == "neutral"
    assert score == Decimal("0")


def test_sentiment_result_overall():
    result = SentimentResult(symbol="TEST")
    result.articles = [
        NewsArticle("Good news", "Source", "", "", "positive", Decimal("0.5"), ""),
        NewsArticle("Bad news", "Source", "", "", "negative", Decimal("-0.3"), ""),
        NewsArticle("Great news", "Source", "", "", "positive", Decimal("0.7"), ""),
    ]
    result.compute_overall()
    assert result.overall_score > 0
    assert result.overall_sentiment == "positive"
