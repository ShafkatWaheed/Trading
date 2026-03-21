---
name: news
description: Search latest market-moving news for a stock
user_invocable: true
arguments:
  - name: ticker
    description: Stock ticker symbol (e.g. AAPL, TSLA)
    required: true
---

# Stock News

Find the latest news for {{ ticker }}.

## Steps

1. Use Tavily to search "{{ ticker }} stock news" with `time_range: "week"`
2. Use Exa to search "{{ ticker }} earnings analyst rating" for deeper results
3. For each article, extract:
   - Headline
   - Source
   - Date
   - Sentiment (positive / neutral / negative)
   - Key takeaway (1 sentence)

4. Present as a table sorted by date (newest first), max 10 articles
5. End with a **Sentiment Summary**: overall sentiment score and brief assessment of how news may impact the stock
