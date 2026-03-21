---
name: politician
description: Deep dive into a specific politician's trading portfolio and performance
user_invocable: true
arguments:
  - name: name
    description: "Politician name (e.g. Pelosi, Tuberville, Gottheimer)"
    required: true
---

# Politician Trading Profile

Generate a full trading profile for {{ name }}.

## Steps

1. Use Tavily to search "{{ name }} stock trades portfolio performance 2025 2026"
2. Use Exa to search "{{ name }} congressional trading financial disclosure history"

3. Build profile:

   **Overview:**
   - Full name, party, chamber (House/Senate), state
   - Committees (important for conflict of interest analysis)
   - Estimated net worth
   - Trading frequency (how many trades per month)

   **Recent Trades (last 6 months):**
   | Date | Stock | Buy/Sell | Amount Range | Price at Trade | Current Price | Return |

   **Top Holdings (if available):**
   | Stock | Estimated Value | Sector |

   **Performance Analysis:**
   - Estimated return vs S&P 500 over same period
   - Best and worst trades
   - Average days to file (compliance score)

   **Sector Exposure:**
   - Which sectors they trade most
   - Cross-reference with committee assignments (flag conflicts)

   **Trading Patterns:**
   - Do they trade before major legislation?
   - Frequency of large trades (> $100K)
   - Buy/sell ratio

4. **Conflict of Interest Flag:**
   - If politician sits on a committee related to stocks they trade, flag it
   - Example: Banking committee member trading bank stocks

5. Disclaimer: "Data sourced from public STOCK Act filings. Filings may be delayed up to 45 days. This is not financial advice."
