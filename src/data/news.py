"""Combined news provider: Tavily (primary) + Exa (supplement) + Google News RSS (free fallback).

Single interface for all news and research queries. Honors quota cooldowns set
by `src.data.quota_tracker` so we don't hammer paid providers that have already
returned 402/403/429/432 in the last 4 hours.
"""

import httpx

from src.data.google_news_rss import get_google_news
from src.data.quota_tracker import is_exhausted, mark_exhausted
from src.utils.config import TAVILY_API_KEY, EXA_API_KEY
from src.utils.db import cache_get, cache_set, log_api_call

# Statuses we treat as "monthly quota exhausted". 432 is Tavily's non-standard
# "no credits left" response — wasn't recognized previously, so the cooldown
# flag never got set and we kept burning requests on the dead provider.
_TAVILY_QUOTA_STATUSES = (402, 403, 429, 432)
_EXA_QUOTA_STATUSES    = (402, 403, 429)


class NewsProvider:

    def search_stock_news(self, symbol: str, days: int = 7) -> list[dict]:
        """Fetch stock news. Falls through Tavily → Exa → Google News RSS.

        Empty results are NOT cached — per project_cache_strategy, a stale empty
        payload masks recoveries. Only non-empty results are cached for 60min.
        """
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

        results: list[dict] = []
        # Use company name + ticker for specific results
        results.extend(self._tavily_search(f'"{company_name}" OR "{symbol}" stock news earnings', max_results=7))
        results.extend(self._exa_search(f"{company_name} {symbol} stock analysis earnings outlook", num_results=3))

        # Free fallback when the paid providers came back empty (rate-limited,
        # missing keys, or transient errors). Google News RSS is unlimited.
        if not results:
            results.extend(self._google_news_search(f"{company_name} {symbol} stock", limit=10))

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

        if filtered:
            cache_set(cache_key, filtered, ttl_minutes=60)
        return filtered

    def search_news(self, query: str, max_results: int = 10) -> list[dict]:
        cache_key = f"news:search:{query}:{max_results}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        results = self._tavily_search(query, max_results=max_results)
        if not results:
            results = self._google_news_search(query, limit=max_results)
        if results:
            cache_set(cache_key, results, ttl_minutes=60)
        return results

    def search_research(self, query: str) -> list[dict]:
        cache_key = f"news:research:{query}"
        cached = cache_get(cache_key)
        if cached:
            return cached

        results = self._exa_search(query, num_results=8)
        if results:
            cache_set(cache_key, results, ttl_minutes=60)
        return results

    def _tavily_search(self, query: str, max_results: int = 5) -> list[dict]:
        if not TAVILY_API_KEY:
            return []

        # Honor the cooldown — quota_tracker flagged Tavily within the last 4h.
        # Saves a round-trip latency hit on a request we know will fail.
        if is_exhausted("tavily"):
            return []

        try:
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={"query": query, "api_key": TAVILY_API_KEY, "max_results": max_results},
                timeout=30,
            )
            if resp.status_code in _TAVILY_QUOTA_STATUSES:
                mark_exhausted("tavily")
                log_api_call("tavily", f"search/{query[:50]}", "quota_exhausted",
                             f"status={resp.status_code}")
                return []
            resp.raise_for_status()
            raw = resp.json()
            log_api_call("tavily", f"search/{query[:50]}", "success")
        except httpx.HTTPStatusError as e:
            if e.response.status_code in _TAVILY_QUOTA_STATUSES:
                mark_exhausted("tavily")
                log_api_call("tavily", f"search/{query[:50]}", "quota_exhausted", str(e))
            else:
                log_api_call("tavily", f"search/{query[:50]}", "error", str(e))
            return []
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

        if is_exhausted("exa"):
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
            if resp.status_code in _EXA_QUOTA_STATUSES:
                mark_exhausted("exa")
                log_api_call("exa", f"search/{query[:50]}", "quota_exhausted",
                             f"status={resp.status_code}")
                return []
            resp.raise_for_status()
            raw = resp.json()
            log_api_call("exa", f"search/{query[:50]}", "success")
        except httpx.HTTPStatusError as e:
            if e.response.status_code in _EXA_QUOTA_STATUSES:
                mark_exhausted("exa")
                log_api_call("exa", f"search/{query[:50]}", "quota_exhausted", str(e))
            else:
                log_api_call("exa", f"search/{query[:50]}", "error", str(e))
            return []
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

    def _google_news_search(self, query: str, limit: int = 10) -> list[dict]:
        """Free, unlimited fallback when paid providers are out of credit."""
        rows = get_google_news(query, limit=limit) or []
        out: list[dict] = []
        for r in rows:
            url = r.get("url") or ""
            out.append({
                "title": r.get("title") or "",
                "url": url,
                "source": (r.get("source") or (url.split("/")[2] if url else "")),
                "published": r.get("pub_date") or "",
                "content_snippet": (r.get("description") or "")[:500],
            })
        return out
