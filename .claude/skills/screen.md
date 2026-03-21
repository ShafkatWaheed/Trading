---
name: screen
description: Screen stocks based on fundamental and technical criteria
user_invocable: true
arguments:
  - name: criteria
    description: "Screening criteria in plain English (e.g. 'P/E under 20, dividend yield above 3%')"
    required: true
---

# Stock Screener

Screen stocks matching: {{ criteria }}

## Steps

1. Parse the user's criteria into specific filters
2. Use Tavily/Exa to search for "stocks with {{ criteria }}" to find candidate tickers
3. For each candidate (up to 15 stocks):
   - Fetch key metrics from Yahoo Finance or Alpha Vantage MCP
   - Check if the stock actually meets ALL specified criteria
4. Filter down to only stocks that pass all criteria
5. For passing stocks, also fetch: RSI(14), SMA(50) vs current price, recent earnings surprise

## Output
Present results as a ranked table with:
- Ticker, Company Name
- All metrics the user filtered on
- RSI, trend direction
- Sector

Sort by the most relevant metric to the user's criteria. Max 20 results.
