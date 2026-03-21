"""Report builder: combines all analysis into a structured report."""

from datetime import datetime
from decimal import Decimal

from src.models.report import Report, ReportSection, RiskRating, Verdict
from src.models.stock import Stock
from src.models.indicator import TechnicalIndicators
from src.analysis.fundamental import FundamentalScore
from src.sentiment.analyzer import SentimentResult
from src.utils.db import save_report


def build_report(
    stock: Stock,
    technicals: TechnicalIndicators,
    fundamentals_score: FundamentalScore,
    sentiment: SentimentResult,
) -> Report:
    """Build a complete analysis report from all data sources."""
    sections = [
        _overview_section(stock),
        _technical_section(technicals),
        _fundamental_section(fundamentals_score),
        _sentiment_section(sentiment),
    ]

    risk = _assess_risk(stock, technicals, fundamentals_score, sentiment)
    verdict, confidence, reasoning = _determine_verdict(
        technicals, fundamentals_score, sentiment
    )

    report = Report(
        symbol=stock.symbol,
        name=stock.name,
        generated_at=datetime.utcnow(),
        verdict=verdict,
        confidence=confidence,
        risk_rating=risk,
        current_price=stock.quote.price if stock.quote else Decimal("0"),
        sentiment_score=sentiment.overall_score,
        sections=sections,
        risks=_identify_risks(stock, technicals, fundamentals_score),
        reasoning=reasoning,
    )

    # Persist to database
    save_report(
        symbol=report.symbol,
        report_type="full",
        content=str(report),
        verdict=report.verdict.value,
        risk_rating=report.risk_rating.value,
        sentiment_score=float(report.sentiment_score),
    )

    return report


def _overview_section(stock: Stock) -> ReportSection:
    data = {}
    if stock.quote:
        data["price"] = str(stock.quote.price)
        data["change"] = str(stock.quote.change)
        data["change_percent"] = f"{stock.quote.change_percent:.2f}%"
        data["volume"] = stock.quote.volume
    if stock.fundamentals:
        data["market_cap"] = str(stock.fundamentals.market_cap)
        data["sector"] = stock.fundamentals.sector
        data["industry"] = stock.fundamentals.industry
        data["52w_high"] = str(stock.fundamentals.week_52_high)
        data["52w_low"] = str(stock.fundamentals.week_52_low)

    return ReportSection(title="Company Overview", content=stock.fundamentals.description if stock.fundamentals else "", data=data)


def _technical_section(tech: TechnicalIndicators) -> ReportSection:
    data = {
        "trend": tech.trend,
        "rsi": str(tech.rsi_14),
        "macd": str(tech.macd),
        "sma_50": str(tech.sma_50),
        "sma_200": str(tech.sma_200),
        "support": str(tech.support),
        "resistance": str(tech.resistance),
        "signal": tech.overall_signal,
        "bullish_signals": tech.bullish_count,
        "bearish_signals": tech.bearish_count,
    }
    return ReportSection(title="Technical Analysis", content=f"Trend: {tech.trend} | Signal: {tech.overall_signal}", data=data)


def _fundamental_section(score: FundamentalScore) -> ReportSection:
    data = {
        "valuation": score.valuation_score,
        "growth": score.growth_score,
        "profitability": score.profitability_score,
        "health": score.health_score,
        "overall": score.overall_score,
        "strengths": score.strengths,
        "weaknesses": score.weaknesses,
    }
    return ReportSection(title="Fundamental Analysis", content=f"Overall Score: {score.overall_score}/5", data=data)


def _sentiment_section(sentiment: SentimentResult) -> ReportSection:
    data = {
        "score": str(sentiment.overall_score),
        "sentiment": sentiment.overall_sentiment,
        "article_count": len(sentiment.articles),
    }
    return ReportSection(title="News Sentiment", content=sentiment.summary, data=data)


def _assess_risk(stock: Stock, tech: TechnicalIndicators, fund: FundamentalScore, sent: SentimentResult) -> RiskRating:
    risk_score = 3  # moderate default

    if tech.rsi_14 and (tech.rsi_14 > 75 or tech.rsi_14 < 25):
        risk_score += 1

    if fund.health_score <= 2:
        risk_score += 1
    elif fund.health_score >= 4:
        risk_score -= 1

    if sent.overall_score < Decimal("-0.3"):
        risk_score += 1
    elif sent.overall_score > Decimal("0.3"):
        risk_score -= 1

    if stock.fundamentals and stock.fundamentals.beta:
        if stock.fundamentals.beta > Decimal("1.5"):
            risk_score += 1

    risk_score = max(1, min(5, risk_score))
    return RiskRating(risk_score)


def _determine_verdict(tech: TechnicalIndicators, fund: FundamentalScore, sent: SentimentResult) -> tuple[Verdict, str, list[str]]:
    reasoning: list[str] = []
    score = 0

    # Technical signal
    signal = tech.overall_signal
    if signal == "Strong Buy":
        score += 2
        reasoning.append(f"Strong technical signals ({tech.bullish_count} bullish vs {tech.bearish_count} bearish)")
    elif signal == "Buy":
        score += 1
        reasoning.append(f"Positive technical signals ({tech.bullish_count} bullish vs {tech.bearish_count} bearish)")
    elif signal == "Sell":
        score -= 1
        reasoning.append(f"Weak technical signals ({tech.bearish_count} bearish vs {tech.bullish_count} bullish)")
    elif signal == "Strong Sell":
        score -= 2
        reasoning.append(f"Strong bearish technical signals")

    # Fundamental score
    if fund.overall_score >= 4:
        score += 2
        reasoning.append(f"Strong fundamentals (score: {fund.overall_score}/5)")
    elif fund.overall_score >= 3:
        score += 1
        reasoning.append(f"Decent fundamentals (score: {fund.overall_score}/5)")
    elif fund.overall_score <= 2:
        score -= 1
        reasoning.append(f"Weak fundamentals (score: {fund.overall_score}/5)")

    # Sentiment
    if sent.overall_score > Decimal("0.3"):
        score += 1
        reasoning.append(f"Positive news sentiment ({sent.overall_sentiment})")
    elif sent.overall_score < Decimal("-0.3"):
        score -= 1
        reasoning.append(f"Negative news sentiment ({sent.overall_sentiment})")

    # Map score to verdict
    if score >= 4:
        verdict = Verdict.STRONG_BUY
    elif score >= 2:
        verdict = Verdict.BUY
    elif score <= -4:
        verdict = Verdict.STRONG_SELL
    elif score <= -2:
        verdict = Verdict.SELL
    else:
        verdict = Verdict.HOLD

    # Confidence
    if abs(score) >= 4:
        confidence = "High"
    elif abs(score) >= 2:
        confidence = "Medium"
    else:
        confidence = "Low"

    return verdict, confidence, reasoning
