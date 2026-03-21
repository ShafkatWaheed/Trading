---
name: research
description: Deep research report combining all data sources for a stock
user_invocable: true
arguments:
  - name: ticker
    description: Stock ticker symbol (e.g. AAPL, TSLA)
    required: true
---

# Deep Research Report

Generate a comprehensive analysis report for {{ ticker }}.

## Steps

### 1. Company Overview
- Fetch company profile, sector, industry from Yahoo Finance MCP
- Brief description of what the company does

### 2. Price & Valuation
- Current price, 52-week range, market cap
- P/E, PEG, P/S, P/B ratios
- Compare valuations against sector averages

### 3. Fundamental Analysis
- Revenue & earnings growth (last 4 quarters)
- Profit margins, ROE, debt-to-equity
- Free cash flow trend
- Dividend info (if applicable)

### 4. Technical Analysis
- Key indicators: RSI, MACD, SMA(50/200)
- Current trend and key levels
- Recent crossover signals

### 5. News & Sentiment
- Use Tavily for recent news (last 7 days)
- Use Exa for analyst opinions and deeper research
- Overall sentiment score (-1 to +1)

### 6. Risk Assessment
- Rate 1-5 based on: volatility, debt, earnings stability, sector risk, news sentiment
- List top 3 risks

### 7. Verdict
- **Rating:** Strong Buy / Buy / Hold / Sell / Strong Sell
- **Confidence:** High / Medium / Low
- Brief reasoning (3-5 bullet points)

## Output Format
Present as a structured report with clear sections and tables. End with a disclaimer: "This is AI-generated analysis for informational purposes only. Not financial advice."
