---
name: stock
description: Look up a stock's current price, key stats, and summary
user_invocable: true
arguments:
  - name: ticker
    description: Stock ticker symbol (e.g. AAPL, TSLA)
    required: true
---

# Stock Lookup

Look up current data for the stock ticker: {{ ticker }}

## Steps

1. Use Yahoo Finance MCP or Alpha Vantage MCP to fetch:
   - Current price, open, high, low, volume
   - Market cap, P/E ratio, EPS, dividend yield
   - 52-week high/low
   - Beta

2. Use Tavily to search for the latest headline about {{ ticker }}

3. Present results in a clean table format:
   - Price & Trading section
   - Valuation section
   - Latest news headline

Keep output concise — just the data, no lengthy commentary.
