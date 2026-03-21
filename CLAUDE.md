# Trading Stock Analysis & Reporting App

## Project Purpose
Stock research and analysis tool that generates reports to help decide which stocks to trade. NOT an order execution system.

**Core features:**
- Analyze stocks and generate buy/sell/hold reports
- Screen stocks based on fundamentals & technicals
- Track watchlists and monitor signals
- News sentiment analysis
- Sector/industry comparison
- Congressional/political trade tracking (STOCK Act disclosures)

## Tech Stack
- **Language:** Python
- **Database:** SQLite (via MCP server at trading.db)
- **Data Sources:** Yahoo Finance MCP, Alpha Vantage MCP (+ macro data), Capitol Trades MCP, SEC EDGAR, Polygon.io, Tavily, Exa
- **Report Output:** PDF / HTML / JSON

## Architecture (STRICTLY ENFORCED)

**Read [ARCHITECTURE.md](ARCHITECTURE.md) before making ANY code changes.** The architecture is law — every change must comply.

### Dependency Direction — NEVER VIOLATE
```
Client (app.py) → Report (reports/) → Analysis (analysis/, sentiment/) → Models (models/)
                                    → Data (data/)                      → Models (models/)
                                                                          ↓
                                                                    Storage (utils/db)
```

**FORBIDDEN imports — Claude MUST refuse to write these:**
- `analysis/` must NEVER import from `data/`, `reports/`, `utils/db`, or `app.py`
- `data/` must NEVER import from `analysis/`, `reports/`, or `app.py`
- `models/` must NEVER import from any other `src/` module
- `utils/db.py` must NEVER import from `models/`
- `sentiment/` must NEVER import from `data/`, `reports/`, or `app.py`
- `screener/` must NEVER import from `data/`, `reports/`, or `app.py`

**If a change requires violating a dependency rule, STOP and ask the user first.**

### Layer Responsibilities — DO NOT MIX
- **Models:** Data structures only. No logic, no I/O, no imports from src.
- **Analysis:** Pure computation. Input models, output scores. No API calls, no DB, no side effects.
- **Data:** Fetch + cache. The ONLY layer allowed to call external APIs.
- **Reports:** Orchestration. Calls data + analysis, builds reports. The ONLY layer that ties them together.
- **Client (app.py):** HTTP endpoints only. Delegates everything to reports layer.
- **Utils:** Generic DB/config. No business logic.

### Data Layer
- Fetch market data from Yahoo Finance and Alpha Vantage MCP servers
- Cache ALL external API responses in SQLite to avoid rate limits
- Store historical analysis reports for trend comparison
- Never call an external API if cached data is fresh (< 15 min for prices, < 24h for fundamentals)

### Analysis Engine
- **Technical indicators:** RSI, MACD, moving averages (SMA/EMA), Bollinger Bands, volume analysis, support/resistance
- **Fundamental metrics:** P/E, PEG, EPS growth, debt-to-equity, free cash flow, ROE, dividend yield
- **Sentiment:** Score news articles from Tavily/Exa on a -1 to +1 scale
- **Comparison:** Always compare stock metrics against sector/industry averages

### Congressional Trade Tracking
- Track politician stock trades from STOCK Act disclosures (House + Senate)
- Data sources: Capitol Trades MCP (free, no key), Quiver Quantitative, official government feeds
- Track: politician name, party, chamber, state, committees, trade date, filed date, amount range
- Flag trades that may indicate conflict of interest (committee vs traded sector)
- Flag late filers (> 45 day filing deadline = STOCK Act violation)
- Calculate net congressional buy/sell sentiment per stock
- Always include 45-day disclosure delay disclaimer in reports

### Corporate Insider & Institutional Tracking (SEC EDGAR)
- Form 4: Track CEO, CFO, director, 10% owner trades
- Form 13F: Track hedge fund and institutional portfolio changes (quarterly)
- Detect cluster buys: 2+ insiders buying same stock within 7 days = strong bullish signal
- Track net insider buy/sell ratio and dollar amounts
- SEC EDGAR API is free, no key required

### Macroeconomic Indicators (Alpha Vantage + Yahoo Finance — no extra key needed)
- Source: Alpha Vantage economic endpoints (FEDERAL_FUNDS_RATE, TREASURY_YIELD, CPI, UNEMPLOYMENT, REAL_GDP, etc.)
- Real-time via Yahoo Finance tickers: ^TNX (10Y), ^VIX, ^IRX (3M), DX-Y.NYB (dollar)
- Fed Funds Rate, Treasury yields (2Y, 10Y), yield curve spread
- Inflation: CPI, retail sales
- Employment: unemployment rate, nonfarm payrolls
- GDP growth, VIX, dollar index
- Macro regime detection: recession_warning (inverted yield curve), tight_monetary, high_volatility
- Reports should include macro context when relevant to the stock's sector

### Options & Derivatives Data
- Options chains: calls/puts by expiration and strike
- Greeks: Delta, Gamma, Theta, Vega
- Implied volatility and IV rank/percentile
- Put/Call ratio: < 0.7 bullish, > 1.0 bearish
- Unusual options activity detection (volume >> open interest)
- Max pain calculation
- Options sentiment should be included in stock reports

### Level 2 Market Microstructure (Polygon.io)
- NBBO quotes with bid/ask depth
- Order book imbalance (buy vs sell pressure)
- Tick-by-tick trade data
- VWAP calculation
- Large trade detection (> 10,000 shares)
- Liquidity scoring (high/medium/low)
- Polygon.io requires API key (free tier: 5 calls/min)

### Report Generation
- Every report must include: summary, technical analysis, fundamental analysis, sentiment, risk rating
- Risk rating scale: 1 (low risk) to 5 (high risk)
- Include data tables and chart-ready data
- Export formats: PDF, HTML, JSON
- Reports are timestamped and stored in SQLite for historical reference

## Code Rules

### Data Types
- Use `Decimal` for ALL price and financial values — NEVER use `float` for money
- All timestamps in UTC, stored as ISO 8601 strings
- Use `dataclasses` or `pydantic` for all models

### Code Quality
- Type hints on ALL functions — no exceptions
- Every analysis function must have unit tests
- Docstrings on public functions (keep brief, 1-2 lines)
- No hardcoded API keys — always from environment variables
- No hardcoded stock symbols in logic — always parameterized

### Database
- All schema changes require a migration script
- Use parameterized queries — never string concatenation for SQL
- Index on: symbol, date, report_type

### API Calls
- Wrap all external API calls in try/except with proper error messages
- Implement retry with exponential backoff (max 3 retries)
- Log all API failures to SQLite
- Respect rate limits: Alpha Vantage (5/min free tier), Yahoo Finance (reasonable pace)

### File Organization
```
Trading/
├── CLAUDE.md
├── trading.db
├── src/
│   ├── data/          # Data fetching & caching (market + congress)
│   ├── analysis/      # Technical & fundamental analysis
│   ├── sentiment/     # News sentiment scoring
│   ├── reports/       # Report generation & export
│   ├── models/        # Data models (Stock, Report, Indicator)
│   ├── screener/      # Stock screening & filtering
│   └── utils/         # Shared utilities
├── tests/
├── reports/           # Generated report output
└── requirements.txt
```

## What NOT To Do
- Do NOT build order execution or broker integration
- Do NOT store real trading credentials
- Do NOT use `float` for financial calculations
- Do NOT make unbounded API calls without caching
- Do NOT generate reports without a risk disclaimer
