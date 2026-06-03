"""News relevance classifier — tags each headline by category so the
pre-earnings card can filter to items actually relevant to the upcoming
print, instead of surfacing M&A noise or "Drucker Wealth bought 100 shares".

Categories (returned per item, in input order):
  earnings_preview   sell-side preview, whisper number, analyst expectations
  channel_check      supplier/customer data, scuttlebutt, industry research
  analyst_revision   target price change, rating change, estimate revision
  product_news       material product launch / partnership / business update
  legal              lawsuits, regulatory action, SEC issues
  merger             M&A / divestiture / restructuring
  general            other / unrelated to the upcoming print (e.g. position
                     disclosures by small advisors, generic "5 stocks to buy"
                     listicles)

One Haiku call per symbol classifies ALL items at once (batched) so cost +
latency stays bounded. Cached 6h.
"""
from __future__ import annotations

import logging
from datetime import datetime

from src.utils.claude_cli import ask_claude_json
from src.utils.db import cache_get, cache_set

logger = logging.getLogger(__name__)

_CACHE_TTL_MINUTES = 6 * 60

# Categories Claude is allowed to assign. Anything else gets coerced to "general".
_VALID_CATEGORIES = {
    "earnings_preview", "channel_check", "analyst_revision",
    "product_news", "legal", "merger", "general",
}

# Subset that's relevant to the upcoming earnings print. Used by callers
# (e.g. pre_earnings_setup_service) to filter the pre-earnings news split.
EARNINGS_RELEVANT = {
    "earnings_preview", "channel_check", "analyst_revision", "product_news",
}


def classify_items(symbol: str, items: list[dict], *, force: bool = False) -> list[str]:
    """Classify every news item for `symbol` into a category. Order-preserving.

    Args:
        symbol: ticker
        items: list of dicts with keys `title` and optional `snippet`
        force: bypass cache

    Returns:
        list[str] same length as `items`, each in _VALID_CATEGORIES. Items that
        couldn't be classified fall back to "general".
    """
    symbol = symbol.upper()
    if not items:
        return []

    # Cache keyed on the symbol — assume items don't change radically between
    # 6h windows. If a fresh item appears, the news_feed cache rolls under it,
    # so by the time it surfaces here the cache layer would have re-fetched.
    cache_key = f"news_relevance:v1:{symbol}"
    if not force:
        cached = cache_get(cache_key)
        if isinstance(cached, dict):
            cached_titles = cached.get("titles") or []
            cached_tags = cached.get("tags") or []
            # Only reuse if the title list matches — guards against drift.
            current_titles = [(i.get("title") or "")[:160] for i in items]
            if cached_titles == current_titles and len(cached_tags) == len(items):
                return cached_tags

    prompt = _build_prompt(symbol, items)
    try:
        result = ask_claude_json(prompt, model="haiku", timeout=60, retries=1)
    except Exception as e:
        logger.warning("news_relevance: Claude call failed for %s %r", symbol, e)
        return ["general"] * len(items)

    tags_raw = (result or {}).get("tags") if isinstance(result, dict) else None
    if not isinstance(tags_raw, list) or len(tags_raw) != len(items):
        logger.info("news_relevance: malformed tags for %s (got %r)", symbol, tags_raw)
        return ["general"] * len(items)

    tags = [str(t).strip().lower() if t else "general" for t in tags_raw]
    tags = [t if t in _VALID_CATEGORIES else "general" for t in tags]

    try:
        cache_set(
            cache_key,
            {
                "titles": [(i.get("title") or "")[:160] for i in items],
                "tags": tags,
                "last_updated": datetime.utcnow().isoformat() + "Z",
            },
            ttl_minutes=_CACHE_TTL_MINUTES,
        )
    except Exception:
        pass
    return tags


def _build_prompt(symbol: str, items: list[dict]) -> str:
    listing = "\n".join(
        f"[{i+1}] {(it.get('title') or '')[:180]} — {(it.get('snippet') or '')[:120]}"
        for i, it in enumerate(items)
    )
    valid_cats = ", ".join(sorted(_VALID_CATEGORIES))
    return f"""You are classifying news headlines for {symbol} by their relevance to an
upcoming earnings call. For EACH item, assign exactly one category:

  earnings_preview   — sell-side preview, whisper number, "what to expect"
                       articles, analyst expectations for the print
  channel_check      — supplier / customer data, scuttlebutt, industry
                       research that points at how the quarter is shaping up
  analyst_revision   — target price change, rating change, estimate revision
                       (upgrade, downgrade, raised PT, cut PT)
  product_news       — material product launch, major partnership, business
                       update that would move the print (e.g. "Boeing wins
                       $5B contract", "Apple Vision Pro launches")
  legal              — lawsuits, regulatory action, SEC investigation,
                       government antitrust
  merger             — M&A activity (acquirer or target), divestiture,
                       restructuring, spin-off
  general            — anything else: routine SEC disclosures, position
                       disclosures by small advisory firms ("X bought N
                       shares"), generic "stocks to buy" listicles, broad
                       sector pieces that aren't specifically about the print

ITEMS:
{listing}

Return JSON ONLY with this exact shape — no prose, no markdown fence:
{{"tags": ["category_for_item_1", "category_for_item_2", ...]}}

The tags array MUST be EXACTLY {len(items)} entries long, in the same order
as the input. Each tag MUST be one of: {valid_cats}.
"""
