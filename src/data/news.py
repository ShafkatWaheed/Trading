"""Combined news provider: Tavily (primary) + Exa (supplement).

Single interface for all news and research queries.
"""

import httpx

from src.utils.config import TAVILY_API_KEY, EXA_API_KEY
from src.utils.db import cache_get, cache_set, log_api_call


class NewsProvider:

    def search_stock_news(self, symbol: str, days: int = 7) -> list[dict]:
        cache_key = f"news:stock:{symbol}:{days}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        # Get company name for better search results
        company_name = symbol
        try:
            import yfinance as yf
            info = yf.Ticker(symbol).info
            company_name = info.get("shortName") or info.get("longName") or symbol
        except Exception:
            pass

        results = []
        # Use company name + ticker for specific results
        results.extend(self._tavily_search(f'"{company_name}" OR "{symbol}" stock news earnings', max_results=7))
        results.extend(self._exa_search(f"{company_name} {symbol} stock analysis earnings outlook", num_results=3))

        # Deduplicate by URL
        seen: set[str] = set()
        unique: list[dict] = []
        for r in results:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique.append(r)

        # Filter out results that don't mention the stock
        symbol_upper = symbol.upper()
        name_lower = company_name.lower()
        filtered = []
        for r in unique:
            text = (r.get("title", "") + " " + r.get("content_snippet", "")).lower()
            if symbol_upper.lower() in text or name_lower in text:
                filtered.append(r)

        # If filtering removed everything, keep originals
        if not filtered:
            filtered = unique

        cache_set(cache_key, filtered, ttl_minutes=60)
        return filtered

    def search_news(self, query: str, max_results: int = 10) -> list[dict]:
        cache_key = f"news:search:{query}:{max_results}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        results = self._tavily_search(query, max_results=max_results)
        cache_set(cache_key, results, ttl_minutes=60)
        return results

    def search_research(self, query: str) -> list[dict]:
        cache_key = f"news:research:{query}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        results = self._exa_search(query, num_results=8)
        cache_set(cache_key, results, ttl_minutes=60)
        return results

    def _tavily_search(self, query: str, max_results: int = 5) -> list[dict]:
        if not TAVILY_API_KEY:
            return []

        try:
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={"query": query, "api_key": TAVILY_API_KEY, "max_results": max_results},
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json()
            log_api_call("tavily", f"search/{query[:50]}", "success")
        except Exception as e:
            log_api_call("tavily", f"search/{query[:50]}", "error", str(e))
            return []

        results: list[dict] = []
        for r in raw.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "source": r.get("url", "").split("/")[2] if r.get("url") else "",
                "published": r.get("published_date", ""),
                "content_snippet": r.get("content", "")[:500],
            })
        return results

    def _exa_search(self, query: str, num_results: int = 5) -> list[dict]:
        if not EXA_API_KEY:
            return []

        try:
            resp = httpx.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": EXA_API_KEY},
                json={
                    "query": query,
                    "type": "auto",
                    "num_results": num_results,
                    "contents": {"highlights": {"max_characters": 4000}},
                },
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json()
            log_api_call("exa", f"search/{query[:50]}", "success")
        except Exception as e:
            log_api_call("exa", f"search/{query[:50]}", "error", str(e))
            return []

        results: list[dict] = []
        for r in raw.get("results", []):
            highlights = r.get("highlights", [])
            snippet = highlights[0] if highlights else r.get("text", "")[:500]
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "source": r.get("url", "").split("/")[2] if r.get("url") else "",
                "published": r.get("publishedDate", ""),
                "content_snippet": snippet[:500] if isinstance(snippet, str) else "",
            })
        return results
