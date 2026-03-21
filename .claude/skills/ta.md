---
name: ta
description: Technical analysis with key indicators for a stock
user_invocable: true
arguments:
  - name: ticker
    description: Stock ticker symbol (e.g. AAPL, TSLA)
    required: true
---

# Technical Analysis

Run technical analysis on {{ ticker }}.

## Steps

1. Fetch historical price data (daily, last 6 months) from Alpha Vantage or Yahoo Finance MCP

2. Calculate and present these indicators:
   - **Trend:** SMA(20), SMA(50), SMA(200), EMA(12), EMA(26)
   - **Momentum:** RSI(14), MACD(12,26,9), Stochastic %K/%D
   - **Volatility:** Bollinger Bands(20,2), ATR(14)
   - **Volume:** Average volume (20-day), volume trend

3. Identify:
   - Current trend (uptrend / downtrend / sideways)
   - Key support and resistance levels
   - Any crossover signals (golden cross, death cross, MACD crossover)
   - RSI condition (overbought > 70 / oversold < 30 / neutral)

4. Present indicators in a table, then a **Signal Summary**:
   - Bullish signals count vs bearish signals count
   - Overall technical rating: Strong Buy / Buy / Neutral / Sell / Strong Sell
