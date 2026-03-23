"""Orchestrator: end-to-end stock analysis.

This is the single function that ties DataGateway + all analysis modules
+ report builder together. Called by CLI and API endpoints.
"""

from decimal import Decimal

from src.data import DataGateway
from src.analysis import technical, fundamental
from src.analysis import macro as macro_analysis
from src.analysis import options_flow
from src.analysis import smart_money
from src.analysis import congress_signal
from src.analysis import relative_value
from src.analysis import confluence
from src.analysis.confluence import SignalInput
from src.sentiment.analyzer import SentimentResult, NewsArticle, score_headline
from src.reports.builder import build_report
from src.reports.exporter import export_html, export_json, export_pdf
from src.models.report import Report
from src.utils.db import init_db


def analyze_stock(symbol: str, export: bool = True, pdf: bool = False) -> Report:
    """Run full analysis on a stock and generate a report.

    Args:
        symbol: Stock ticker (e.g. "AAPL").
        export: If True, save HTML + JSON to reports/ directory.
    """
    init_db()
    symbol = symbol.upper()
    gw = DataGateway()

    # ── Fetch data (each wrapped — missing data = None) ────────

    stock = gw.get_stock(symbol)

    historical = _safe(lambda: gw.get_historical(symbol))
    macro_snapshot = gw.get_macro_snapshot()
    options_summary = gw.get_options_summary(symbol)
    insider_summary = gw.get_insider_summary(symbol)
    institutional_summary = gw.get_institutional_summary(symbol)
    congress_summary = gw.get_congress_summary(symbol)
    news_articles = gw.get_stock_news(symbol)

    # ── Run analysis ───────────────────────────────────────────

    # Technical (requires historical prices)
    tech_result = None
    if historical is not None and not historical.empty:
        tech_result = _safe(lambda: technical.analyze(symbol, historical))

    # Fundamental
    fund_result = None
    if stock.fundamentals:
        fund_result = _safe(lambda: fundamental.analyze(stock.fundamentals))

    # Sentiment
    sentiment_result = _build_sentiment(symbol, news_articles)

    # Macro
    macro_result = None
    if macro_snapshot:
        macro_result = _safe(lambda: macro_analysis.analyze(macro_snapshot))

    # Options flow
    options_result = None
    if options_summary:
        options_result = _safe(lambda: options_flow.analyze(options_summary))

    # Smart money (insider + institutional)
    smart_money_result = _safe(lambda: smart_money.analyze(insider_summary, institutional_summary))

    # Congress
    congress_result = None
    if congress_summary:
        congress_result = _safe(lambda: congress_signal.analyze(congress_summary))

    # Relative value (skip if no fundamentals — needs sector avg in future)
    relative_result = None

    # Confluence (combine all signals)
    confluence_result = None
    signal_inputs = _build_signal_inputs(
        tech_result, fund_result, sentiment_result,
        macro_result, options_result, smart_money_result,
        congress_result, relative_result,
    )
    if signal_inputs:
        confluence_result = confluence.analyze(signal_inputs)

    # ── Build report ───────────────────────────────────────────

    # Ensure we have minimum required data for a report
    if tech_result is None:
        from src.models.indicator import TechnicalIndicators
        from datetime import datetime
        tech_result = TechnicalIndicators(symbol=symbol, timestamp=datetime.utcnow())

    if fund_result is None:
        from src.analysis.fundamental import FundamentalScore
        fund_result = FundamentalScore(
            symbol=symbol, valuation_score=3, growth_score=3,
            profitability_score=3, health_score=3, overall_score=3,
            strengths=[], weaknesses=["Insufficient data for full fundamental analysis"],
        )

    report = build_report(
        stock=stock,
        technicals=tech_result,
        fundamentals_score=fund_result,
        sentiment=sentiment_result,
        macro_score=macro_result,
        options_score=options_result,
        smart_money_score=smart_money_result,
        congress_score=congress_result,
        relative_value_score=relative_result,
        confluence=confluence_result,
    )

    # ── Export ──────────────────────────────────────────────────

    if export:
        html_path = export_html(report)
        json_path = export_json(report)
        print(f"  HTML: {html_path}")
        print(f"  JSON: {json_path}")
        if pdf:
            pdf_path = export_pdf(report)
            print(f"  PDF:  {pdf_path}")

    return report


def _build_sentiment(symbol: str, articles: list[dict]) -> SentimentResult:
    """Build sentiment from raw news articles."""
    news_items: list[NewsArticle] = []
    for a in articles:
        headline = a.get("title", "")
        if not headline:
            continue
        sent_label, sent_score = score_headline(headline)
        news_items.append(NewsArticle(
            headline=headline,
            source=a.get("source", ""),
            url=a.get("url", ""),
            published=a.get("published", ""),
            sentiment=sent_label,
            sentiment_score=sent_score,
            takeaway=a.get("content_snippet", "")[:200],
        ))

    result = SentimentResult(symbol=symbol, articles=news_items)
    result.compute_overall()

    if result.articles:
        pos = sum(1 for a in result.articles if a.sentiment == "positive")
        neg = sum(1 for a in result.articles if a.sentiment == "negative")
        result.summary = (
            f"{len(result.articles)} articles analyzed: "
            f"{pos} positive, {neg} negative, "
            f"{len(result.articles) - pos - neg} neutral. "
            f"Overall: {result.overall_sentiment} ({result.overall_score})"
        )
    else:
        result.summary = "No news articles found."

    return result


def _build_signal_inputs(tech, fund, sent, macro, options, smart, congress, relative) -> list[SignalInput]:
    """Construct SignalInput list for confluence detection."""
    signals: list[SignalInput] = []

    if tech and tech.overall_signal != "Neutral":
        score_map = {"Strong Buy": 2, "Buy": 1, "Sell": -1, "Strong Sell": -2}
        signals.append(SignalInput(
            name="technical", score=score_map.get(tech.overall_signal, 0),
            max_score=2, label=tech.overall_signal,
        ))

    if fund:
        score = 2 if fund.overall_score >= 4 else 1 if fund.overall_score >= 3 else -1 if fund.overall_score <= 2 else 0
        signals.append(SignalInput(
            name="fundamental", score=score, max_score=2,
            label=f"Score {fund.overall_score}/5",
        ))

    if sent and sent.overall_score != Decimal("0"):
        score = 1 if sent.overall_score > Decimal("0.3") else -1 if sent.overall_score < Decimal("-0.3") else 0
        signals.append(SignalInput(
            name="sentiment", score=score, max_score=1,
            label=sent.overall_sentiment,
        ))

    if macro:
        signals.append(SignalInput(
            name="macro", score=macro.score, max_score=2, label=macro.regime,
        ))

    if options:
        signals.append(SignalInput(
            name="options", score=options.score, max_score=2, label=options.signal,
        ))

    if smart and smart.score != 0:
        signals.append(SignalInput(
            name="smart_money", score=smart.score, max_score=2,
            label=f"{smart.insider_signal}/{smart.institutional_signal}",
        ))

    if congress and congress.signal != "no_data":
        signals.append(SignalInput(
            name="congress", score=congress.score, max_score=1,
            label=congress.signal,
        ))

    if relative:
        signals.append(SignalInput(
            name="relative_value", score=relative.score, max_score=2,
            label=relative.valuation,
        ))

    return signals


def _safe(fn, default=None):
    """Call fn, return default on any exception."""
    try:
        return fn()
    except Exception:
        return default
