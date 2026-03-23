# Architecture: Trading Stock Analysis & Reporting App

## System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                             CLIENT LAYER                                  │
│                                                                           │
│  Claude Skills              FastAPI REST             Report Exports       │
│  /stock /ta /news           /reports /watchlist      HTML / JSON / PDF    │
│  /congress /politician      /macro /options                               │
│  /research /screen          /insider                                      │
└──────────┬────────────────────────┬────────────────────────┬─────────────┘
           │                        │                        │
           ▼                        ▼                        ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                            REPORT LAYER                                   │
│                                                                           │
│  ┌────────────────┐   ┌────────────────┐   ┌────────────────────┐        │
│  │ Report Builder  │   │   Exporter     │   │  Report Storage    │        │
│  │ (orchestrates   │   │ (HTML, JSON,   │   │  (SQLite reports   │        │
│  │  all analysis)  │   │  PDF)          │   │   table)           │        │
│  └───────┬────────┘   └────────────────┘   └────────────────────┘        │
│          │                                                                │
│          │  Uses DataGateway (single import) — never imports              │
│          │  individual providers directly                                 │
│          │                                                                │
└──────────┼────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      ANALYSIS LAYER (10 modules)                          │
│                                                                           │
│  ┌─ Core (original 4) ───────────────────────────────────────────────┐   │
│  │                                                                    │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐  │   │
│  │  │  Technical   │ │ Fundamental │ │  Sentiment  │ │ Screener  │  │   │
│  │  │  ±2 weight   │ │  ±2 weight  │ │  ±1 weight  │ │ (filter)  │  │   │
│  │  │  RSI, MACD,  │ │  P/E, PEG,  │ │  News NLP,  │ │ criteria  │  │   │
│  │  │  SMA, BB     │ │  growth,    │ │  headline   │ │ matching  │  │   │
│  │  │  signals     │ │  health     │ │  scoring    │ │           │  │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘  │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                           │
│  ┌─ New (6 modules) ─────────────────────────────────────────────────┐   │
│  │                                                                    │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌──────────────────────────┐    │   │
│  │  │ Macro Regime │ │Options Flow │ │    Smart Money           │    │   │
│  │  │ ±1.5 weight  │ │ ±1.5 weight │ │    ±2 weight             │    │   │
│  │  │ yield curve, │ │ P/C ratio,  │ │    insider cluster buys, │    │   │
│  │  │ VIX, rates,  │ │ IV rank,    │ │    Form 4 + Form 13F,   │    │   │
│  │  │ GDP, jobs    │ │ unusual act │ │    institutional flow    │    │   │
│  │  └─────────────┘ └─────────────┘ └──────────────────────────┘    │   │
│  │                                                                    │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌──────────────────────────┐    │   │
│  │  │ Congress    │ │ Relative    │ │    Confluence             │    │   │
│  │  │ ±0.5 weight │ │ Value       │ │    (meta-analysis)       │    │   │
│  │  │ STOCK Act   │ │ ±1.5 weight │ │    detects agreement/    │    │   │
│  │  │ trades,     │ │ vs sector   │ │    divergence across     │    │   │
│  │  │ bipartisan  │ │ peers       │ │    all other signals,    │    │   │
│  │  │ signals     │ │ P/E, margin │ │    adjusts confidence    │    │   │
│  │  └─────────────┘ └─────────────┘ └──────────────────────────┘    │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                           │
│  Each module is INDEPENDENT — they NEVER import each other               │
│  Pure computation only — NO API calls, NO DB access, NO side effects     │
│  All import data types from src/models/data_types.py                     │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                            DATA LAYER                                     │
│                                                                           │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                    DataGateway (gateway.py)                         │  │
│  │                                                                     │  │
│  │  Single entry point for ALL data access.                           │  │
│  │  Report builder and app.py ONLY import this class.                 │  │
│  │                                                                     │  │
│  │  gw = DataGateway()                                                │  │
│  │  gw.get_stock("AAPL")            # quote + fundamentals           │  │
│  │  gw.get_historical("AAPL")       # price history                  │  │
│  │  gw.get_macro_snapshot()         # macro indicators               │  │
│  │  gw.get_options_summary("AAPL")  # options + Greeks               │  │
│  │  gw.get_insider_summary("AAPL")  # Form 4 insiders               │  │
│  │  gw.get_institutional_summary()  # Form 13F hedge funds           │  │
│  │  gw.get_congress_summary("AAPL") # STOCK Act trades               │  │
│  │  gw.get_stock_news("AAPL")       # Tavily + Exa                  │  │
│  │  gw.get_microstructure("AAPL")   # Level 2 order book            │  │
│  │                                                                     │  │
│  │  Optional providers fail gracefully (return None)                  │  │
│  │  Market data uses Yahoo → Alpha Vantage fallback                  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│          │                                                                │
│          ▼                                                                │
│  ┌─ Market Data ──────────────────────────────────────────────────────┐  │
│  │                                                                     │  │
│  │  ┌──────────────────────────────────────────────────────────────┐  │  │
│  │  │ MarketDataService (market.py)                                │  │  │
│  │  │                                                              │  │  │
│  │  │ Yahoo Finance MCP (primary) ──► Alpha Vantage (fallback)    │  │  │
│  │  │                                                              │  │  │
│  │  │ get_quote()         Yahoo first → AV if Yahoo fails         │  │  │
│  │  │ get_fundamentals()  Yahoo first → AV if Yahoo fails         │  │  │
│  │  │ get_historical()    Yahoo first → AV if Yahoo fails         │  │  │
│  │  │                                                              │  │  │
│  │  │ AV has real httpx API calls (GLOBAL_QUOTE, OVERVIEW,        │  │  │
│  │  │ TIME_SERIES_DAILY). Yahoo stubs ready for MCP wiring.       │  │  │
│  │  └──────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  ┌─ Macro Data ───────────────────────────────────────────────────────┐  │
│  │                                                                     │  │
│  │  ┌──────────────────────────────────────────────────────────────┐  │  │
│  │  │ MacroProvider (macro.py)                                     │  │  │
│  │  │                                                              │  │  │
│  │  │ Reuses Alpha Vantage key — no extra API key needed          │  │  │
│  │  │ Real httpx calls to AV economic endpoints:                  │  │  │
│  │  │   FEDERAL_FUNDS_RATE, TREASURY_YIELD, CPI, UNEMPLOYMENT,   │  │  │
│  │  │   NONFARM_PAYROLL, REAL_GDP, RETAIL_SALES, INFLATION       │  │  │
│  │  │                                                              │  │  │
│  │  │ Yahoo Finance tickers for real-time:                        │  │  │
│  │  │   ^VIX, ^TNX (10Y), ^IRX (3M), DX-Y.NYB (dollar)         │  │  │
│  │  │                                                              │  │  │
│  │  │ MacroSnapshot with regime detection:                        │  │  │
│  │  │   high_volatility | recession_warning | tight_monetary |    │  │  │
│  │  │   strong_labor | normal                                     │  │  │
│  │  └──────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  ┌─ Options & Level 2 (merged) ───────────────────────────────────────┐  │
│  │                                                                     │  │
│  │  ┌──────────────────────────────────────────────────────────────┐  │  │
│  │  │ PolygonProvider (polygon.py)                                 │  │  │
│  │  │                                                              │  │  │
│  │  │ Real httpx calls to Polygon.io REST API:                    │  │  │
│  │  │                                                              │  │  │
│  │  │ Level 2:        /v3/quotes, /v3/trades, /v2/aggs            │  │  │
│  │  │   NBBO, order book depth, ticks, VWAP, liquidity scoring   │  │  │
│  │  │                                                              │  │  │
│  │  │ Options:         /v3/snapshot/options                        │  │  │
│  │  │   Chains, Greeks (Δ Γ Θ V), IV, put/call ratio,           │  │  │
│  │  │   unusual activity, sentiment                               │  │  │
│  │  └──────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  ┌─ Ownership & Insider Data ─────────────────────────────────────────┐  │
│  │                                                                     │  │
│  │  ┌────────────────┐  ┌────────────────┐                           │  │
│  │  │ SEC EDGAR      │  │ Capitol Trades │                           │  │
│  │  │ (sec_edgar.py) │  │ (congress.py)  │                           │  │
│  │  │                │  │                │                           │  │
│  │  │ Form 4:        │  │ Congress STOCK │                           │  │
│  │  │ CEO/CFO/Dir    │  │ Act trades,    │                           │  │
│  │  │ insider trades │  │ House+Senate,  │                           │  │
│  │  │ cluster buys   │  │ party data     │                           │  │
│  │  │                │  │                │                           │  │
│  │  │ Form 13F:      │  │ No API key     │                           │  │
│  │  │ hedge fund &   │  │ required       │                           │  │
│  │  │ institutional  │  │                │                           │  │
│  │  │                │  │                │                           │  │
│  │  │ No API key     │  │                │                           │  │
│  │  └────────────────┘  └────────────────┘                           │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  ┌─ News & Research ──────────────────────────────────────────────────┐  │
│  │                                                                     │  │
│  │  ┌──────────────────────────────────────────────────────────────┐  │  │
│  │  │ NewsProvider (news.py)                                       │  │  │
│  │  │                                                              │  │  │
│  │  │ Tavily (primary) + Exa (supplement) combined                │  │  │
│  │  │ Real httpx calls to both APIs                               │  │  │
│  │  │                                                              │  │  │
│  │  │ search_stock_news()  Tavily for headlines + Exa for depth   │  │  │
│  │  │ search_news()        General Tavily search                  │  │  │
│  │  │ search_research()    Exa semantic/deep search               │  │  │
│  │  │                                                              │  │  │
│  │  │ Deduplicates by URL across sources                          │  │  │
│  │  └──────────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  ┌─ Infrastructure ───────────────────────────────────────────────────┐  │
│  │                                                                     │  │
│  │  ALL providers ──► cache check ──► rate limit ──► API call         │  │
│  │                    ──► retry on failure ──► cache store             │  │
│  │                                                                     │  │
│  │  ┌────────────────────────────────────────────────────────────┐    │  │
│  │  │                   CACHE (SQLite)                            │    │  │
│  │  │                                                            │    │  │
│  │  │  quotes: 15 min TTL        insider trades: 24 hour TTL    │    │  │
│  │  │  fundamentals: 24 hour     congress trades: 24 hour        │    │  │
│  │  │  news: 1 hour              options chains: 15 min          │    │  │
│  │  │  historical: 15 min        macro indicators: 24 hour       │    │  │
│  │  │  level 2 / NBBO: 1 min    institutional (13F): 24 hour    │    │  │
│  │  └────────────────────────────────────────────────────────────┘    │  │
│  │                                                                     │  │
│  │  ┌──────────────────┐  ┌──────────────────┐                       │  │
│  │  │ RateLimiter      │  │ @with_retry      │                       │  │
│  │  │ (rate_limit.py)  │  │ (retry.py)       │                       │  │
│  │  │                  │  │                  │                       │  │
│  │  │ Token bucket     │  │ Exponential      │                       │  │
│  │  │ per provider:    │  │ backoff:         │                       │  │
│  │  │ AV: 5/min       │  │ max 3 retries    │                       │  │
│  │  │ Polygon: 5/min  │  │ 1s → 2s → 4s    │                       │  │
│  │  │ SEC: 10/sec     │  │ max 30s delay    │                       │  │
│  │  │ Thread-safe     │  │ Logs all retries │                       │  │
│  │  └──────────────────┘  └──────────────────┘                       │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          STORAGE (SQLite)                                  │
│                                                                           │
│  cache            reports          watchlist        api_log               │
│  ─────            ───────          ─────────        ───────               │
│  key              symbol           symbol           source                │
│  value            report_type      name             endpoint              │
│  created_at       content          added_at         status                │
│  expires_at       verdict                           error_message         │
│                   risk_rating                       timestamp             │
│                   sentiment_score                                         │
│                   created_at                                              │
└──────────────────────────────────────────────────────────────────────────┘
```

## Data Provider Inventory

| Provider | File | API Key | Rate Limit | Status | Data |
|----------|------|---------|------------|--------|------|
| Market (Yahoo → AV) | `market.py` | AV: `4P6G...` | AV: 5/min | **Working** (AV calls) | Quotes, fundamentals, history |
| Macro | `macro.py` | Reuses AV | Shared with AV | **Working** | Fed rate, yields, CPI, GDP, VIX |
| Polygon.io | `polygon.py` | `Vvrx...` | 5/min | **Working** | Level 2, ticks, options, Greeks |
| News | `news.py` | Tavily + Exa | 1000/mo | **Working** | Articles, research, headlines |
| SEC EDGAR | `sec_edgar.py` | None | 10/sec | Stub | Form 4 insiders, Form 13F |
| Capitol Trades | `congress.py` | None | N/A | Stub | Congress STOCK Act trades |

## Models (Pydantic)

All models use Pydantic `BaseModel` — free `.model_dump()` / `.model_validate()` serialization.

| File | Classes |
|------|---------|
| `models/stock.py` | `StockQuote`, `StockFundamentals`, `Stock` |
| `models/indicator.py` | `TechnicalIndicators`, `Signal`, `SignalType` |
| `models/report.py` | `Report`, `ReportSection`, `RiskRating`, `Verdict` |

## Layer Rules

### 1. Client Layer
- Entry points only. No business logic.
- FastAPI handles HTTP. Skills invoke analysis via the same code paths.
- All responses include timestamps and source attribution.

### 2. Report Layer
- Orchestration only. Calls `DataGateway` + analysis modules.
- **MUST use `DataGateway`** — never import individual providers.
- Reports are immutable. Never update a saved report — generate a new one.
- Every report is persisted to SQLite before returning.

### 3. Analysis Layer
- Pure computation. No API calls, no database access, no side effects.
- Each module (technical, fundamental, sentiment, screener) is independent — they never import each other.
- Input: Pydantic models and DataFrames. Output: scored results.
- All analysis functions must be unit-testable with no mocks needed.

### 4. Data Layer
- **`DataGateway`** is the only public interface — all consumers use it.
- Individual providers are internal to the data layer.
- Every external call: cache check → rate limit → API call → retry on failure → cache store.
- Market data uses Yahoo → Alpha Vantage automatic fallback.
- Optional providers (macro, polygon, SEC, congress) fail gracefully — return `None`.
- Rate limits enforced via token bucket (`RateLimiter`).
- Retries with exponential backoff (`@with_retry`).

### 5. Storage Layer
- Single SQLite database (`trading.db`).
- All queries use parameterized statements — no string concatenation.
- Schema changes require migration scripts.

## Data Flow

```
User Request (e.g. /research AAPL)
    │
    ▼
Report Builder
    │
    │  from src.data import DataGateway
    │  gw = DataGateway()
    │
    ├──► gw.get_stock("AAPL")
    │    └── MarketDataService: Yahoo → AV fallback
    │        └── cache → rate_limit → httpx → retry → cache
    │
    ├──► gw.get_historical("AAPL")
    │    └── MarketDataService: AV TIME_SERIES_DAILY
    │
    ├──► gw.get_macro_snapshot()
    │    └── MacroProvider: AV economic endpoints
    │
    ├──► gw.get_options_summary("AAPL")
    │    └── PolygonProvider: /v3/snapshot/options
    │
    ├──► gw.get_insider_summary("AAPL")
    │    └── SECEdgarProvider: Form 4 API
    │
    ├──► gw.get_congress_summary("AAPL")
    │    └── CongressDataProvider: Capitol Trades
    │
    ├──► gw.get_stock_news("AAPL")
    │    └── NewsProvider: Tavily search + Exa supplement
    │
    ├──► Analysis (pure computation, no I/O)
    │    ├── technical(historical_df) ──► TechnicalIndicators
    │    ├── fundamental(fundamentals) ──► FundamentalScore
    │    └── sentiment(articles) ──► SentimentResult
    │
    ├──► Combine all signals ──► Verdict + Risk + Confidence
    │
    ├──► Save to SQLite
    ├──► Export HTML / JSON / PDF
    │
    ▼
Report returned to user
```

## Dependency Direction (STRICT)

```
Client (app.py, skills)
    │
    ▼
Report Layer (reports/)
    │
    ├──► DataGateway (data/gateway.py)     ← ONLY data import allowed
    │         │
    │         ├──► MarketDataService (data/market.py)
    │         ├──► MacroProvider (data/macro.py)
    │         ├──► PolygonProvider (data/polygon.py)
    │         ├──► SECEdgarProvider (data/sec_edgar.py)
    │         ├──► CongressDataProvider (data/congress.py)
    │         └──► NewsProvider (data/news.py)
    │
    ├──► Analysis Layer (analysis/, sentiment/, screener/)
    │         │
    │         ▼
    │       Models (models/) ← Pydantic BaseModel
    │
    └──► Storage (utils/db)
```

### Rules:
- **Models** depend on nothing. Pure Pydantic data structures.
- **Analysis** depends only on Models. Never imports Data or Storage.
- **Data providers** depend on Models, Storage, and Utils. Never import Analysis.
- **DataGateway** depends on all providers. This is the only public data interface.
- **Report** depends on DataGateway, Analysis, and Models. Never imports individual providers.
- **Client** depends on Report. Never calls DataGateway or Analysis directly.
- **Storage (utils/db)** depends on nothing except stdlib.

### Forbidden Dependencies:
- Analysis → Data (analysis must not fetch data)
- Analysis → Storage (analysis must not read/write DB)
- Data providers → Analysis (data must not analyze)
- Data providers → Report (data must not build reports)
- Report → individual data providers (must use DataGateway)
- Models → anything (models are leaf nodes)
- Storage → Models (storage is generic)

## Module Ownership

| File | Responsibility | Allowed Dependencies |
|------|---------------|---------------------|
| `src/models/stock.py` | StockQuote, StockFundamentals, Stock | pydantic, decimal |
| `src/models/indicator.py` | TechnicalIndicators, Signal, SignalType | pydantic, decimal |
| `src/models/report.py` | Report, ReportSection, RiskRating, Verdict | pydantic, decimal |
| `src/data/gateway.py` | **DataGateway** — single entry point | all providers, models |
| `src/data/market.py` | MarketDataService (Yahoo → AV fallback) | models, utils, httpx |
| `src/data/macro.py` | MacroProvider (AV economic + Yahoo tickers) | models, utils, httpx |
| `src/data/polygon.py` | PolygonProvider (Level 2 + options merged) | models, utils, httpx |
| `src/data/sec_edgar.py` | SECEdgarProvider (Form 4 + 13F) | models, utils |
| `src/data/congress.py` | CongressDataProvider (STOCK Act) | models, utils |
| `src/data/news.py` | NewsProvider (Tavily + Exa combined) | utils, httpx |
| `src/models/data_types.py` | Shared data types for analysis + data layer | stdlib, decimal |
| `src/analysis/technical.py` | RSI, MACD, SMA, BB, signals | models, pandas, ta |
| `src/analysis/fundamental.py` | Valuation, growth, health scoring | models |
| `src/analysis/macro.py` | Macro regime scoring (VIX, yields, rates) | models/data_types |
| `src/analysis/options_flow.py` | Options P/C ratio, IV, unusual activity | models/data_types |
| `src/analysis/smart_money.py` | Insider + institutional behavior | models/data_types |
| `src/analysis/congress_signal.py` | Congressional STOCK Act trade signals | models/data_types |
| `src/analysis/relative_value.py` | Stock vs sector peer comparison | models/stock |
| `src/analysis/confluence.py` | Cross-signal agreement/divergence | stdlib only |
| `src/sentiment/analyzer.py` | News sentiment scoring | models |
| `src/screener/screener.py` | Filter stocks by criteria | models |
| `src/reports/builder.py` | Orchestrate DataGateway + analysis → Report | gateway, models, analysis, sentiment, utils |
| `src/reports/exporter.py` | Export reports to HTML/JSON/PDF | models |
| `src/utils/db.py` | SQLite access, caching, API logging | stdlib only |
| `src/utils/config.py` | Environment variables, constants | stdlib, dotenv |
| `src/utils/rate_limit.py` | Token bucket rate limiter per provider | stdlib (threading, time) |
| `src/utils/retry.py` | @with_retry exponential backoff decorator | utils/db (for logging) |
| `src/app.py` | FastAPI HTTP endpoints | reports, utils |

## Signal Aggregation

Reports combine multiple independent signals into a final verdict:

```
┌──────────────────────────────────────────────────────────────┐
│                    SIGNAL SOURCES (10)                         │
│                                                               │
│  Signal             Range     Weight   Max Contribution       │
│  ─────────────────  ────────  ───────  ────────────────       │
│  Technical          ±2        1.0x     ±2.0                   │
│  Fundamental        ±2        1.0x     ±2.0                   │
│  Sentiment          ±1        1.0x     ±1.0                   │
│  Macro Regime       ±2        0.75x    ±1.5                   │
│  Options Flow       ±2        0.75x    ±1.5                   │
│  Smart Money        ±2        1.0x     ±2.0  ← cluster buy!  │
│  Congress           ±1        0.5x     ±0.5                   │
│  Relative Value     ±2        0.75x    ±1.5                   │
│                                                               │
│  Total range: ≈ ±12                                           │
│                                                               │
│         ▼                                                     │
│  ┌──────────────────────────────────────────────────┐        │
│  │              VERDICT ENGINE                       │        │
│  │                                                   │        │
│  │  >= +6: Strong Buy   <= -6: Strong Sell          │        │
│  │  >= +3: Buy          <= -3: Sell                 │        │
│  │  else: Hold                                       │        │
│  │                                                   │        │
│  │  Confidence: |score| >= 7 High, >= 4 Med, else Low│       │
│  │  Confluence adjusts confidence ±1 level           │        │
│  │  Risk Rating: 1-5 (macro + IV + insiders + beta)  │        │
│  └──────────────────────────────────────────────────┘        │
│                                                               │
│  ┌──────────────────────────────────────────────────┐        │
│  │          CONFLUENCE DETECTOR                      │        │
│  │                                                   │        │
│  │  Checks all signals for agreement/divergence:     │        │
│  │  strong_agreement → confidence +1                 │        │
│  │  divergent (strong signals conflict) → conf -1    │        │
│  │  Flags: "Insiders buying but technicals bearish"  │        │
│  └──────────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────────┘
```

## Scaling Path

| Phase | What Changes | What Stays |
|-------|-------------|-----------|
| Phase 1 (now) | CLI + skills | All layers |
| Phase 2 | Add FastAPI web UI | Analysis, Data, Models unchanged |
| Phase 3 | Add APScheduler for nightly scans | Just add scheduler, no layer changes |
| Phase 4 | Add Streamlit dashboard | Reads from same SQLite, no backend changes |
| Phase 5 | Swap SQLite → PostgreSQL | Only utils/db.py changes |
| Phase 6 | Add WebSocket for live prices | Add to Data layer, Client gets new endpoint |
| Phase 7 | Add Alpaca MCP for execution | New provider in DataGateway, reports untouched |
| Phase 8 | Wire Yahoo Finance MCP | Just implement stubs in market.py, nothing else changes |
| Phase 9 | Wire SEC EDGAR + Capitol Trades | Just implement stubs, gateway already exposes them |
