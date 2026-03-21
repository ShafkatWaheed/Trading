---
name: congress
description: Track what politicians are buying/selling for a stock
user_invocable: true
arguments:
  - name: query
    description: "Stock ticker (AAPL) or politician name (Pelosi)"
    required: true
---

# Congressional Trade Tracker

Look up political trading activity for: {{ query }}

## Steps

1. Determine if {{ query }} is a stock ticker or politician name

2. **If stock ticker:**
   - Use Tavily to search "{{ query }} congress politician stock trades 2026"
   - Use Exa to search "{{ query }} congressional trading disclosure STOCK Act"
   - Find: which politicians bought/sold, when, how much, party affiliation
   - Check Capitol Trades data for the ticker

3. **If politician name:**
   - Use Tavily to search "{{ query }} stock trades portfolio 2026"
   - Use Exa to search "{{ query }} financial disclosure STOCK Act trades"
   - Find: what stocks they traded, amounts, timing, committees they sit on

4. Present results:

   **Summary Table:**
   | Politician | Party | Buy/Sell | Amount | Trade Date | Filed Date | Days Late |

   **Analysis:**
   - Net buy/sell ratio from politicians
   - Party breakdown (Democrat vs Republican buying patterns)
   - Any trades near committee hearings or legislation
   - Notable late filers (> 45 days = STOCK Act violation)

   **Signal:**
   - If multiple politicians buying → "Congressional Bullish Signal"
   - If multiple politicians selling → "Congressional Bearish Signal"
   - Compare politician trades vs stock performance after trade date

5. End with disclaimer: "Congressional trades are disclosed 45 days after the fact. Past politician trades do not guarantee future returns."
