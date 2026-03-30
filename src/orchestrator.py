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

    # ── Fetch data (parallelized — missing data = None) ────────

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as executor:
        f_stock = executor.submit(lambda: gw.get_stock(symbol))
        f_hist = executor.submit(lambda: _safe(lambda: gw.get_historical(symbol)))
        f_macro = executor.submit(lambda: gw.get_macro_snapshot())
        f_options = executor.submit(lambda: gw.get_options_summary(symbol))
        f_insider = executor.submit(lambda: gw.get_insider_summary(symbol))
        f_institutional = executor.submit(lambda: gw.get_institutional_summary(symbol))
        f_congress = executor.submit(lambda: gw.get_congress_summary(symbol))
        f_news = executor.submit(lambda: gw.get_stock_news(symbol))

    stock = f_stock.result()
    historical = f_hist.result()
    macro_snapshot = f_macro.result()
    options_summary = f_options.result()
    insider_summary = f_insider.result()
    institutional_summary = f_institutional.result()
    congress_summary = f_congress.result()
    news_articles = f_news.result()

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

    # Geopolitical risk (uses cached Tavily data)
    geo_data = _safe(lambda: _fetch_geopolitical_for_stock(symbol, stock))

    # Analyst ratings (from Yahoo Finance)
    analyst_data = _safe(lambda: _fetch_analyst_data(symbol))

    # Institutional holders
    holders_data = _safe(lambda: _fetch_holders_data(symbol))

    # Community buzz
    buzz_data = _safe(lambda: _fetch_community_buzz(symbol))

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
        geopolitical_data=geo_data,
        analyst_data=analyst_data,
        holders_data=holders_data,
        community_buzz=buzz_data,
        short_interest=_safe(lambda: gw.get_short_interest(symbol)),
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
    """Build sentiment from raw news articles using Claude AI batch scoring."""
    from src.sentiment.analyzer import score_headlines_batch

    # Collect headlines
    valid_articles = []
    headlines = []
    for a in articles:
        headline = a.get("title", "")
        if headline:
            valid_articles.append(a)
            headlines.append(headline)

    # Batch score all headlines in one Claude call
    if headlines:
        scores = score_headlines_batch(headlines)
    else:
        scores = []

    news_items: list[NewsArticle] = []
    for a, (sent_label, sent_score) in zip(valid_articles, scores):
        news_items.append(NewsArticle(
            headline=a.get("title", ""),
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


def _score_community_batch_with_claude(symbol: str, texts: list[str]) -> list[str] | None:
    """Score community posts for bullish/bearish/neutral using Claude."""
    import subprocess

    try:
        numbered = "\n".join(f"{i+1}. {t[:80]}" for i, t in enumerate(texts))

        prompt = f"""Score each community/social media post about {symbol} stock for trader sentiment.

{numbered}

For each post, determine: is the community bullish, bearish, or neutral on this stock?
Consider retail trader language (moon, YOLO, puts, short = directional. DD, analysis = could be either).

Respond with ONLY a JSON array of sentiment strings:
["bullish", "neutral", "bearish", "bullish", ...]"""

        env = dict(os.environ)
        env.pop("CLAUDECODE", None)

        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", "haiku"],
            capture_output=True, text=True, timeout=20, env=env,
        )
        response = proc.stdout.strip()

        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            import json
            data = json.loads(response[start:end])
            return [s if s in ("bullish", "bearish", "neutral") else "neutral" for s in data]
    except Exception:
        pass

    return None


def _fetch_community_buzz(symbol: str) -> dict | None:
    """Fetch community sentiment from Reddit, X, StockTwits via Tavily + Exa."""
    from src.utils.db import cache_get, cache_set
    import httpx
    from src.utils.config import TAVILY_API_KEY, EXA_API_KEY

    cache_key = f"buzz:{symbol}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    raw_posts = []

    # Tavily — Reddit + general community
    if TAVILY_API_KEY:
        queries = [
            f"{symbol} stock reddit sentiment discussion 2026",
            f"{symbol} stock buy sell opinion retail traders",
        ]
        for query in queries:
            try:
                resp = httpx.post(
                    "https://api.tavily.com/search",
                    json={"query": query, "api_key": TAVILY_API_KEY, "max_results": 5, "search_depth": "basic"},
                    timeout=15,
                )
                for r in resp.json().get("results", [])[:5]:
                    title = r.get("title", "")[:120]
                    content = r.get("content", "")[:200]
                    url = r.get("url", "")
                    source = "Reddit" if "reddit" in url.lower() else "StockTwits" if "stocktwits" in url.lower() else "X/Twitter" if "twitter" in url.lower() or "x.com" in url.lower() else "Web"
                    raw_posts.append({"title": title, "source": source, "url": url, "snippet": content[:150], "text_for_scoring": title + " " + content})
            except Exception:
                continue

    # Exa — deeper semantic search
    if EXA_API_KEY:
        try:
            resp = httpx.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": EXA_API_KEY},
                json={
                    "query": f"retail traders discussion {symbol} stock analysis buy sell sentiment",
                    "type": "auto", "num_results": 5,
                    "contents": {"highlights": {"max_characters": 300}},
                },
                timeout=15,
            )
            for r in resp.json().get("results", [])[:5]:
                title = r.get("title", "")[:120]
                highlights = r.get("highlights", [])
                content = highlights[0] if highlights else ""
                url = r.get("url", "")
                source = "Reddit" if "reddit" in url.lower() else "Research" if any(d in url.lower() for d in ["seeking", "motley", "investop"]) else "Community"
                if not any(p["url"] == url for p in raw_posts):
                    raw_posts.append({"title": title, "source": source, "url": url, "snippet": content[:150], "text_for_scoring": title + " " + content})
        except Exception:
            pass

    if not raw_posts:
        return None

    # Score all posts with Claude in one batch call
    posts = []
    texts = [p["text_for_scoring"][:100] for p in raw_posts]
    try:
        ai_scores = _score_community_batch_with_claude(symbol, texts)
    except Exception:
        ai_scores = None

    bullish_count = 0
    bearish_count = 0
    neutral_count = 0

    for i, rp in enumerate(raw_posts):
        if ai_scores and i < len(ai_scores):
            sentiment = ai_scores[i]
        else:
            # Keyword fallback
            t = rp["text_for_scoring"].lower()
            b = sum(1 for w in ("buy", "bull", "moon", "calls", "long", "undervalued", "squeeze") if w in t)
            s = sum(1 for w in ("sell", "bear", "puts", "short", "crash", "overvalued", "dump") if w in t)
            sentiment = "bullish" if b > s else "bearish" if s > b else "neutral"

        if sentiment == "bullish":
            bullish_count += 1
        elif sentiment == "bearish":
            bearish_count += 1
        else:
            neutral_count += 1

        posts.append({
            "title": rp["title"], "source": rp["source"], "url": rp["url"],
            "sentiment": sentiment, "snippet": rp["snippet"],
        })

    total = bullish_count + bearish_count + neutral_count
    bullish_pct = round(bullish_count / total * 100) if total > 0 else 0
    bearish_pct = round(bearish_count / total * 100) if total > 0 else 0

    # Determine signal
    if bullish_pct >= 65:
        signal = "bullish"
        score = 1
    elif bearish_pct >= 65:
        signal = "bearish"
        score = -1
    else:
        signal = "neutral"
        score = 0

    # Buzz level
    if total >= 15:
        buzz_level = "very high"
    elif total >= 8:
        buzz_level = "high"
    elif total >= 4:
        buzz_level = "moderate"
    else:
        buzz_level = "low"

    result = {
        "signal": signal,
        "score": score,
        "total_mentions": total,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "bullish_pct": bullish_pct,
        "bearish_pct": bearish_pct,
        "buzz_level": buzz_level,
        "posts": posts[:8],
        "sources": list(set(p["source"] for p in posts)),
    }

    cache_set(cache_key, result, ttl_minutes=60)
    return result


def _fetch_analyst_data(symbol: str) -> dict | None:
    """Fetch analyst ratings and price targets from Yahoo Finance."""
    from src.utils.db import cache_get, cache_set
    import yfinance as yf

    cache_key = f"analyst:{symbol}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        consensus = info.get("recommendationKey", "hold")
        target_mean = info.get("targetMeanPrice")
        target_high = info.get("targetHighPrice")
        target_low = info.get("targetLowPrice")
        num_analysts = info.get("numberOfAnalystOpinions", 0)
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")

        # Get recommendation breakdown
        strong_buy = buy = hold_count = sell = strong_sell = 0
        try:
            recs = ticker.recommendations
            if recs is not None and not recs.empty:
                latest = recs.iloc[0]
                strong_buy = int(latest.get("strongBuy", 0))
                buy = int(latest.get("buy", 0))
                hold_count = int(latest.get("hold", 0))
                sell = int(latest.get("sell", 0))
                strong_sell = int(latest.get("strongSell", 0))
        except Exception:
            pass

        result = {
            "consensus": consensus,
            "target_mean": float(target_mean) if target_mean else None,
            "target_high": float(target_high) if target_high else None,
            "target_low": float(target_low) if target_low else None,
            "num_analysts": int(num_analysts) if num_analysts else 0,
            "current_price": float(current_price) if current_price else None,
            "strong_buy": strong_buy,
            "buy": buy,
            "hold": hold_count,
            "sell": sell,
            "strong_sell": strong_sell,
        }

        cache_set(cache_key, result, ttl_minutes=60 * 24)
        return result
    except Exception:
        return None


def _interpret_holders_with_claude(symbol: str, institutions: list[dict], funds: list[dict],
                                    insider_pct: float, inst_pct: float) -> dict | None:
    """Ask Claude to interpret institutional holder changes — distinguish passive vs active."""
    import subprocess

    if not institutions:
        return None

    try:
        holders_text = "\n".join(
            f"  {i['name'][:35]}: holds {i['pct_held']:.1f}%, changed {i['pct_change']:+.1f}%"
            for i in institutions[:8]
        )
        funds_text = "\n".join(
            f"  {f['name'][:40]}: holds {f['pct_held']:.1f}%, changed {f['pct_change']:+.1f}%"
            for f in funds[:5]
        ) if funds else "  No fund data"

        prompt = f"""Analyze the institutional ownership of {symbol} stock and determine the trading signal.

INSTITUTIONAL HOLDERS (top 8):
{holders_text}

MUTUAL FUND HOLDERS (top 5):
{funds_text}

OWNERSHIP: Insiders {insider_pct:.1f}%, Institutions {inst_pct:.1f}%

Distinguish between:
- PASSIVE holders (Vanguard, BlackRock, State Street, SPDR, iShares) — their changes are index rebalancing, NOT conviction
- ACTIVE holders (ARK Invest, Bridgewater, Renaissance, Soros, Berkshire) — their changes ARE high-conviction bets
- If an active manager is increasing, that's MORE meaningful than a passive fund increasing

Respond with ONLY this JSON:
{{"signal": "bullish" or "bearish" or "neutral", "score": 1 or -1 or 0, "interpretation": "2-3 sentences explaining what the institutional moves REALLY mean for this stock. Distinguish passive rebalancing from active conviction."}}"""

        env = dict(os.environ)
        env.pop("CLAUDECODE", None)

        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", "haiku"],
            capture_output=True, text=True, timeout=20, env=env,
        )
        response = proc.stdout.strip()

        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            import json
            return json.loads(response[start:end])
    except Exception:
        pass

    return None


def _fetch_holders_data(symbol: str) -> dict | None:
    """Fetch major holders, top institutions, and mutual funds from Yahoo Finance."""
    from src.utils.db import cache_get, cache_set
    import yfinance as yf

    cache_key = f"holders:{symbol}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    try:
        ticker = yf.Ticker(symbol)

        # Major holders summary
        insider_pct = 0
        inst_pct = 0
        inst_count = 0
        try:
            mh = ticker.major_holders
            if mh is not None and not mh.empty:
                vals = dict(zip(mh["Breakdown"], mh["Value"]))
                insider_pct = float(vals.get("insidersPercentHeld", 0)) * 100
                inst_pct = float(vals.get("institutionsPercentHeld", 0)) * 100
                inst_count = int(vals.get("institutionsCount", 0))
        except Exception:
            pass

        # Top institutional holders
        top_institutions = []
        net_inst_buying = 0
        try:
            ih = ticker.institutional_holders
            if ih is not None and not ih.empty:
                for _, row in ih.head(10).iterrows():
                    pct_change = float(row.get("pctChange", 0))
                    net_inst_buying += pct_change
                    top_institutions.append({
                        "name": str(row.get("Holder", "")),
                        "pct_held": round(float(row.get("pctHeld", 0)) * 100, 2),
                        "shares": int(row.get("Shares", 0)),
                        "pct_change": round(pct_change * 100, 2),
                    })
        except Exception:
            pass

        # Top mutual fund holders
        top_funds = []
        try:
            mf = ticker.mutualfund_holders
            if mf is not None and not mf.empty:
                for _, row in mf.head(5).iterrows():
                    top_funds.append({
                        "name": str(row.get("Holder", "")),
                        "pct_held": round(float(row.get("pctHeld", 0)) * 100, 2),
                        "pct_change": round(float(row.get("pctChange", 0)) * 100, 2),
                    })
        except Exception:
            pass

        # Determine signal
        buyers = sum(1 for i in top_institutions if i["pct_change"] > 0)
        sellers = sum(1 for i in top_institutions if i["pct_change"] < 0)

        if buyers > sellers * 2:
            signal = "bullish"
            score = 1
        elif sellers > buyers * 2:
            signal = "bearish"
            score = -1
        else:
            signal = "neutral"
            score = 0

        # Notable holders (Berkshire, ARK, etc.)
        notable = []
        notable_names = {"berkshire": "Warren Buffett", "ark invest": "Cathie Wood", "bridgewater": "Ray Dalio", "renaissance": "Jim Simons", "soros": "George Soros"}
        for inst in top_institutions:
            for key, name in notable_names.items():
                if key in inst["name"].lower():
                    action = "increasing" if inst["pct_change"] > 0 else "decreasing" if inst["pct_change"] < 0 else "holding"
                    notable.append(f"{name} ({inst['name'][:30]}) is {action} position")

        # Ask Claude to interpret the institutional data
        ai_analysis = _interpret_holders_with_claude(symbol, top_institutions, top_funds, insider_pct, inst_pct)
        if ai_analysis:
            signal = ai_analysis.get("signal", signal)
            score = ai_analysis.get("score", score)

        result = {
            "insider_pct": round(insider_pct, 2),
            "institutional_pct": round(inst_pct, 2),
            "institutional_count": inst_count,
            "top_institutions": top_institutions[:5],
            "top_funds": top_funds[:3],
            "buyers": buyers,
            "sellers": sellers,
            "net_direction": "accumulating" if buyers > sellers else "distributing" if sellers > buyers else "stable",
            "signal": signal,
            "score": score,
            "notable": notable,
            "ai_interpretation": ai_analysis.get("interpretation", "") if ai_analysis else "",
        }

        cache_set(cache_key, result, ttl_minutes=60 * 24)
        return result
    except Exception:
        return None


def _analyze_geo_events_with_claude(raw_events: list[dict]) -> list[dict] | None:
    """Use Claude to analyze geopolitical events — severity + sector impact."""
    import subprocess

    if not raw_events:
        return None

    try:
        events_text = "\n".join(
            f"{i+1}. [{e['type'].replace('_', ' ').title()}] {e['title']}\n   {e.get('content', '')[:100]}"
            for i, e in enumerate(raw_events)
        )

        prompt = f"""Analyze these geopolitical/economic events for their impact on US stock market sectors.

{events_text}

For each event, determine:
1. Severity: "high" (actively moving markets) or "moderate" (developing, watch closely)
2. Which US stock market sectors are NEGATIVELY affected (at risk)
3. Which sectors BENEFIT from this event

Use standard GICS sector names: Technology, Healthcare, Financials, Energy, Consumer Discretionary, Consumer Staples, Industrials, Materials, Utilities, Real Estate, Communication Services

Respond with ONLY a JSON array:
[
  {{"type": "tariff", "title": "...", "severity": "high", "negative_sectors": ["Technology", "Industrials"], "positive_sectors": ["Utilities", "Healthcare"]}},
  ...
]"""

        env = dict(os.environ)
        env.pop("CLAUDECODE", None)

        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", "haiku"],
            capture_output=True, text=True, timeout=25, env=env,
        )
        response = proc.stdout.strip()

        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            import json
            data = json.loads(response[start:end])
            events = []
            for item in data:
                events.append({
                    "type": item.get("type", "unknown"),
                    "title": item.get("title", ""),
                    "severity": item.get("severity", "moderate"),
                    "negative_sectors": item.get("negative_sectors", []),
                    "positive_sectors": item.get("positive_sectors", []),
                })
            return events
    except Exception:
        pass

    return None


def _fetch_geopolitical_for_stock(symbol: str, stock) -> dict | None:
    """Fetch geopolitical events and tag with stock's sector for relevance."""
    import httpx
    from src.utils.config import TAVILY_API_KEY
    from src.utils.db import cache_get, cache_set

    # Use cached geopolitical events (shared across all stocks, 1hr TTL)
    cache_key = "geo:events"
    cached = cache_get(cache_key)

    if not cached:
        if not TAVILY_API_KEY:
            return None

        queries = [
            ("tariff", "US tariffs trade war 2026 impact industries"),
            ("war", "war conflict military impact US stock market 2026"),
            ("natural_disaster", "flood hurricane earthquake disaster US economic impact 2026"),
            ("supply_chain", "supply chain disruption shortage US industry 2026"),
        ]

        # Fetch events from Tavily
        raw_events = []
        for event_type, query in queries:
            try:
                resp = httpx.post(
                    "https://api.tavily.com/search",
                    json={"query": query, "api_key": TAVILY_API_KEY, "max_results": 2, "search_depth": "basic"},
                    timeout=15,
                )
                for r in resp.json().get("results", [])[:2]:
                    raw_events.append({
                        "type": event_type,
                        "title": r.get("title", "")[:100],
                        "content": r.get("content", "")[:150],
                    })
            except Exception:
                continue

        # Use Claude to analyze severity and sector impact for all events in one call
        events = _analyze_geo_events_with_claude(raw_events)
        if not events:
            # Fallback: basic keyword scoring
            impact_map = {
                "tariff": {"negative": ["Technology", "Consumer Discretionary", "Industrials"], "positive": ["Domestic Manufacturing", "Utilities"]},
                "war": {"negative": ["Airlines", "Tourism", "Financials"], "positive": ["Defense & Aerospace", "Energy"]},
                "natural_disaster": {"negative": ["Insurance", "Real Estate", "Agriculture"], "positive": ["Construction", "Infrastructure"]},
                "supply_chain": {"negative": ["Automotive", "Electronics", "Retail"], "positive": ["Shipping & Logistics"]},
            }
            events = []
            for re in raw_events:
                impact = impact_map.get(re["type"], {})
                events.append({
                    "type": re["type"], "title": re["title"],
                    "severity": "moderate",
                    "negative_sectors": impact.get("negative", []),
                    "positive_sectors": impact.get("positive", []),
                })

        if events:
            cache_set(cache_key, events, ttl_minutes=60)
            cached = events

    if not cached:
        return None

    # Determine stock's sector
    sector = ""
    if stock and stock.fundamentals:
        sector = getattr(stock.fundamentals, "sector", "") or ""

    # Also include disruption themes (cached separately)
    disruption_key = "geo:disruption_themes"
    disruption_cached = cache_get(disruption_key)
    # Disruption themes are fetched by the dashboard — if not cached, pass empty
    # They'll be populated when the user visits Market Pulse

    return {"events": cached, "stock_sector": sector, "symbol": symbol, "disruption_themes": disruption_cached or []}


def _safe(fn, default=None):
    """Call fn, return default on any exception."""
    try:
        return fn()
    except Exception:
        return default
