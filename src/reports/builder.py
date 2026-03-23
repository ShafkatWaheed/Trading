"""Report builder: combines ALL analysis into a structured report.

Consumes data via DataGateway and feeds it through 10 analysis modules
to produce a weighted verdict with confidence and risk rating.
"""

from datetime import datetime
from decimal import Decimal

from src.models.report import Report, ReportSection, RiskRating, Verdict
from src.models.stock import Stock
from src.models.indicator import TechnicalIndicators
from src.models.data_types import (
    MacroSnapshot, OptionsSummary, InsiderSummary,
    InstitutionalSummary, CongressTradesSummary,
)
from src.analysis.fundamental import FundamentalScore
from src.analysis.macro import MacroScore
from src.analysis.options_flow import OptionsFlowScore
from src.analysis.smart_money import SmartMoneyScore
from src.analysis.congress_signal import CongressSignalScore
from src.analysis.relative_value import RelativeValueScore
from src.analysis.confluence import ConfluenceResult, SignalInput
from src.sentiment.analyzer import SentimentResult
from src.utils.db import save_report


# ── Signal weights for verdict calculation ──────────────────────────

WEIGHTS = {
    "technical": Decimal("1.0"),
    "fundamental": Decimal("1.0"),
    "sentiment": Decimal("1.0"),
    "macro": Decimal("0.75"),
    "options": Decimal("0.75"),
    "smart_money": Decimal("1.0"),
    "congress": Decimal("0.5"),
    "relative_value": Decimal("0.75"),
}


def build_report(
    stock: Stock,
    technicals: TechnicalIndicators,
    fundamentals_score: FundamentalScore,
    sentiment: SentimentResult,
    macro_score: MacroScore | None = None,
    options_score: OptionsFlowScore | None = None,
    smart_money_score: SmartMoneyScore | None = None,
    congress_score: CongressSignalScore | None = None,
    relative_value_score: RelativeValueScore | None = None,
    confluence: ConfluenceResult | None = None,
) -> Report:
    # Build sections
    sections = [
        _overview_section(stock),
        _technical_section(technicals),
        _fundamental_section(fundamentals_score),
        _sentiment_section(sentiment),
    ]

    if macro_score:
        sections.append(_macro_section(macro_score))
    if options_score:
        sections.append(_options_section(options_score))
    if smart_money_score:
        sections.append(_smart_money_section(smart_money_score))
    if congress_score:
        sections.append(_congress_section(congress_score))
    if relative_value_score:
        sections.append(_relative_value_section(relative_value_score))
    if confluence:
        sections.append(_confluence_section(confluence))

    # Determine verdict
    risk = _assess_risk(stock, technicals, fundamentals_score, sentiment, macro_score, options_score, smart_money_score)
    verdict, confidence, reasoning = _determine_verdict(
        technicals, fundamentals_score, sentiment,
        macro_score, options_score, smart_money_score,
        congress_score, relative_value_score, confluence,
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
        risks=_identify_risks(stock, technicals, fundamentals_score, macro_score, smart_money_score),
        reasoning=reasoning,
    )

    save_report(
        symbol=report.symbol,
        report_type="full",
        content=str(report),
        verdict=report.verdict.value,
        risk_rating=report.risk_rating.value,
        sentiment_score=float(report.sentiment_score),
    )

    return report


# ── Section builders ────────────────────────────────────────────────

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
    return ReportSection(
        title="Company Overview",
        content=stock.fundamentals.description if stock.fundamentals else "",
        data=data,
    )


def _technical_section(tech: TechnicalIndicators) -> ReportSection:
    return ReportSection(
        title="Technical Analysis",
        content=f"Trend: {tech.trend} | Signal: {tech.overall_signal}",
        data={
            "trend": tech.trend, "rsi": str(tech.rsi_14), "macd": str(tech.macd),
            "sma_50": str(tech.sma_50), "sma_200": str(tech.sma_200),
            "support": str(tech.support), "resistance": str(tech.resistance),
            "signal": tech.overall_signal,
            "bullish_signals": tech.bullish_count, "bearish_signals": tech.bearish_count,
        },
    )


def _fundamental_section(score: FundamentalScore) -> ReportSection:
    return ReportSection(
        title="Fundamental Analysis",
        content=f"Overall Score: {score.overall_score}/5",
        data={
            "valuation": score.valuation_score, "growth": score.growth_score,
            "profitability": score.profitability_score, "health": score.health_score,
            "overall": score.overall_score,
            "strengths": score.strengths, "weaknesses": score.weaknesses,
        },
    )


def _sentiment_section(sentiment: SentimentResult) -> ReportSection:
    return ReportSection(
        title="News Sentiment",
        content=sentiment.summary,
        data={
            "score": str(sentiment.overall_score),
            "sentiment": sentiment.overall_sentiment,
            "article_count": len(sentiment.articles),
        },
    )


def _macro_section(macro: MacroScore) -> ReportSection:
    return ReportSection(
        title="Macro Environment",
        content=f"Regime: {macro.regime} | Impact: {macro.score:+d}",
        data={"regime": macro.regime, "score": macro.score, "factors": macro.factors},
    )


def _options_section(options: OptionsFlowScore) -> ReportSection:
    return ReportSection(
        title="Options Flow",
        content=f"Signal: {options.signal} | Score: {options.score:+d}",
        data={
            "signal": options.signal, "score": options.score,
            "put_call": options.put_call_interpretation,
            "iv": options.iv_interpretation,
            "unusual": options.unusual_activity_note,
            "factors": options.factors,
        },
    )


def _smart_money_section(sm: SmartMoneyScore) -> ReportSection:
    return ReportSection(
        title="Smart Money (Insider + Institutional)",
        content=f"Insiders: {sm.insider_signal} | Institutions: {sm.institutional_signal}",
        data={
            "score": sm.score, "insider_signal": sm.insider_signal,
            "institutional_signal": sm.institutional_signal,
            "cluster_buy": sm.cluster_buy_detected, "factors": sm.factors,
        },
    )


def _congress_section(cong: CongressSignalScore) -> ReportSection:
    return ReportSection(
        title="Congressional Trades",
        content=f"Signal: {cong.signal} | Bipartisan: {cong.bipartisan}",
        data={
            "score": cong.score, "signal": cong.signal,
            "bipartisan": cong.bipartisan, "factors": cong.factors,
            "disclaimer": cong.disclaimer,
        },
    )


def _relative_value_section(rv: RelativeValueScore) -> ReportSection:
    return ReportSection(
        title="Relative Valuation",
        content=f"Valuation: {rv.valuation} | Score: {rv.score:+d}",
        data={
            "score": rv.score, "valuation": rv.valuation,
            "comparisons": rv.comparisons, "factors": rv.factors,
        },
    )


def _confluence_section(conf: ConfluenceResult) -> ReportSection:
    return ReportSection(
        title="Signal Confluence",
        content=f"Alignment: {conf.alignment} | Confidence adj: {conf.confidence_adjustment:+d}",
        data={
            "alignment": conf.alignment,
            "confidence_adjustment": conf.confidence_adjustment,
            "agreements": conf.agreements,
            "divergences": conf.divergences,
            "warnings": conf.warnings,
        },
    )


# ── Verdict engine ──────────────────────────────────────────────────

def _determine_verdict(
    tech: TechnicalIndicators,
    fund: FundamentalScore,
    sent: SentimentResult,
    macro: MacroScore | None,
    options: OptionsFlowScore | None,
    smart_money: SmartMoneyScore | None,
    congress: CongressSignalScore | None,
    relative: RelativeValueScore | None,
    confluence: ConfluenceResult | None,
) -> tuple[Verdict, str, list[str]]:
    reasoning: list[str] = []
    total_score = Decimal("0")

    # Technical
    tech_score = _tech_to_score(tech)
    total_score += Decimal(str(tech_score)) * WEIGHTS["technical"]
    reasoning.append(f"Technical: {tech.overall_signal} ({tech.bullish_count} bullish vs {tech.bearish_count} bearish)")

    # Fundamental
    fund_score = _fund_to_score(fund)
    total_score += Decimal(str(fund_score)) * WEIGHTS["fundamental"]
    reasoning.append(f"Fundamental: score {fund.overall_score}/5 ({'+' if fund_score > 0 else ''}{fund_score})")

    # Sentiment
    sent_score = _sent_to_score(sent)
    total_score += Decimal(str(sent_score)) * WEIGHTS["sentiment"]
    reasoning.append(f"Sentiment: {sent.overall_sentiment} ({sent.overall_score})")

    # Macro
    if macro:
        total_score += Decimal(str(macro.score)) * WEIGHTS["macro"]
        reasoning.append(f"Macro: {macro.regime} ({macro.score:+d})")

    # Options
    if options:
        total_score += Decimal(str(options.score)) * WEIGHTS["options"]
        reasoning.append(f"Options: {options.signal} ({options.score:+d})")

    # Smart Money
    if smart_money:
        total_score += Decimal(str(smart_money.score)) * WEIGHTS["smart_money"]
        label = "cluster buy!" if smart_money.cluster_buy_detected else f"{smart_money.insider_signal}/{smart_money.institutional_signal}"
        reasoning.append(f"Smart Money: {label} ({smart_money.score:+d})")

    # Congress
    if congress and congress.signal != "no_data":
        total_score += Decimal(str(congress.score)) * WEIGHTS["congress"]
        reasoning.append(f"Congress: {congress.signal} ({congress.score:+d})")

    # Relative Value
    if relative:
        total_score += Decimal(str(relative.score)) * WEIGHTS["relative_value"]
        reasoning.append(f"Relative Value: {relative.valuation} ({relative.score:+d})")

    # Map to verdict (range ≈ ±12)
    if total_score >= 6:
        verdict = Verdict.STRONG_BUY
    elif total_score >= 3:
        verdict = Verdict.BUY
    elif total_score <= -6:
        verdict = Verdict.STRONG_SELL
    elif total_score <= -3:
        verdict = Verdict.SELL
    else:
        verdict = Verdict.HOLD

    # Confidence
    abs_score = abs(total_score)
    if abs_score >= 7:
        confidence = "High"
    elif abs_score >= 4:
        confidence = "Medium"
    else:
        confidence = "Low"

    # Confluence adjusts confidence
    if confluence:
        adj = confluence.confidence_adjustment
        levels = ["Low", "Medium", "High"]
        idx = levels.index(confidence)
        new_idx = max(0, min(2, idx + adj))
        confidence = levels[new_idx]
        if confluence.warnings:
            reasoning.append(f"Confluence: {confluence.alignment} — {'; '.join(confluence.warnings)}")

    reasoning.append(f"Total weighted score: {total_score:.1f}")

    return verdict, confidence, reasoning


def _tech_to_score(tech: TechnicalIndicators) -> int:
    signal = tech.overall_signal
    if signal == "Strong Buy":
        return 2
    if signal == "Buy":
        return 1
    if signal == "Sell":
        return -1
    if signal == "Strong Sell":
        return -2
    return 0


def _fund_to_score(fund: FundamentalScore) -> int:
    if fund.overall_score >= 4:
        return 2
    if fund.overall_score >= 3:
        return 1
    if fund.overall_score <= 2:
        return -1
    return 0


def _sent_to_score(sent: SentimentResult) -> int:
    if sent.overall_score > Decimal("0.3"):
        return 1
    if sent.overall_score < Decimal("-0.3"):
        return -1
    return 0


# ── Risk assessment ─────────────────────────────────────────────────

def _assess_risk(
    stock: Stock,
    tech: TechnicalIndicators,
    fund: FundamentalScore,
    sent: SentimentResult,
    macro: MacroScore | None,
    options: OptionsFlowScore | None,
    smart_money: SmartMoneyScore | None,
) -> RiskRating:
    risk_score = 3

    # Technical extremes
    if tech.rsi_14 and (tech.rsi_14 > 75 or tech.rsi_14 < 25):
        risk_score += 1

    # Weak fundamentals
    if fund.health_score <= 2:
        risk_score += 1
    elif fund.health_score >= 4:
        risk_score -= 1

    # Negative sentiment
    if sent.overall_score < Decimal("-0.3"):
        risk_score += 1
    elif sent.overall_score > Decimal("0.3"):
        risk_score -= 1

    # High beta
    if stock.fundamentals and stock.fundamentals.beta:
        if stock.fundamentals.beta > Decimal("1.5"):
            risk_score += 1

    # Macro headwinds
    if macro and macro.score <= -2:
        risk_score += 1

    # Options elevated IV
    if options and options.iv_interpretation and "elevated" in options.iv_interpretation.lower():
        risk_score += 1

    # Smart money selling while price stable/rising
    if smart_money and smart_money.insider_signal == "selling":
        risk_score += 1

    risk_score = max(1, min(5, risk_score))
    return RiskRating(risk_score)


# ── Risk identification ─────────────────────────────────────────────

def _identify_risks(
    stock: Stock,
    tech: TechnicalIndicators,
    fund: FundamentalScore,
    macro: MacroScore | None,
    smart_money: SmartMoneyScore | None,
) -> list[str]:
    risks: list[str] = []

    if tech.rsi_14 and tech.rsi_14 > 70:
        risks.append("Technically overbought (RSI > 70)")
    if tech.trend == "downtrend":
        risks.append("Price in downtrend")

    if fund.health_score <= 2:
        risks.append("Weak financial health")
    if stock.fundamentals and stock.fundamentals.debt_to_equity:
        if stock.fundamentals.debt_to_equity > Decimal("2"):
            risks.append(f"High debt (D/E: {stock.fundamentals.debt_to_equity})")

    if stock.fundamentals and stock.fundamentals.beta:
        if stock.fundamentals.beta > Decimal("1.5"):
            risks.append(f"High volatility (beta: {stock.fundamentals.beta})")

    if macro and macro.score <= -1:
        risks.append(f"Macro headwind: {macro.regime}")

    if smart_money and smart_money.insider_signal == "selling":
        risks.append("Insiders are net sellers")

    return risks[:5]
