"""Context Search service — Tier 1 LLM-mediated free-text → ranked stocks.

Pipeline:

    user query
        ↓ (Haiku via subprocess CLI)
    expand_query  →  {keywords, commodities[], industries[], themes[], ...}
        ↓
    fan out:
      • keywords → news_impact_service.analyze_news (uses expanded keywords)
      • commodities → graph_relevance_service.compute_relevance
        ↓
    merge results, group by leg, return ranked list with reasoning chains.

Failure modes degrade gracefully:
  • If Claude call fails → empty expansion, but the raw text still goes
    through the keyword tokenizer (existing news-impact behaviour) so the
    user gets *something* back.
  • If any leg fails it's just skipped, others continue.
"""

from __future__ import annotations

from api.services import graph_relevance_service, news_impact_service
from src.news.query_expander import expand_query


# Composite-score floor for inclusion in results. Anything below this is
# noise (graph fan-out lands on most stocks at very low weights once you
# multiply tier × industry-strength × hop-decay).
MIN_SCORE = 0.02


def search(query: str, *, limit: int = 40) -> dict:
    """Run the full context search pipeline.

    Returns:
        {
            "query": str,
            "expansion": {keywords, commodities, industries, themes, ...},
            "stocks": [
                {
                    "symbol": str,
                    "name": str | None,
                    "tier": str | None,
                    "sector": str | None,
                    "industry_code": str | None,
                    "composite_score": float,
                    "polarity": float,
                    "legs": ["keywords" | "commodities" | "graph_relevance", ...],
                    "reasoning": [str, ...],
                },
                ...
            ],
            "by_industry": [
                {"industry_code": str, "polarity": float, "strength": float, "stocks": [symbols]},
                ...
            ],
        }
    """
    expansion = expand_query(query)

    # ── Leg 1: enriched keyword search ─────────────────────────────
    #
    # We feed the original query PLUS the LLM-suggested keywords into the
    # news tokenizer. The aggregator only matches tokens present in
    # `keyword_impact`, so unknown LLM suggestions simply pass through —
    # the known ones add coverage to the user's literal text.
    enriched_text = query
    if expansion["keywords"]:
        enriched_text = f"{query}. {' '.join(expansion['keywords'])}"
    try:
        news_out = news_impact_service.analyze_news(enriched_text)
    except Exception:
        news_out = {"stocks": [], "industries": []}

    # ── Leg 2: commodity-driven graph relevance ────────────────────
    commodity_themes = [
        {
            "commodity_code": c["code"],
            "direction": c["direction"],
            "intensity": c["intensity"],
        }
        for c in expansion["commodities"]
    ]
    if commodity_themes:
        try:
            graph_out = graph_relevance_service.compute_relevance(
                commodity_themes, bullish_only=False, limit=limit * 3
            )
        except Exception:
            graph_out = {"relevance": []}
    else:
        graph_out = {"relevance": []}

    # ── Merge ──────────────────────────────────────────────────────
    merged: dict[str, dict] = {}

    for s in news_out.get("stocks", []) or []:
        sym = s["symbol"]
        merged[sym] = {
            "symbol": sym,
            "name": s.get("name"),
            "tier": s.get("tier"),
            "sector": s.get("sector"),
            "industry_code": s.get("industry_code"),
            "composite_score": float(s.get("composite_score", 0.0)),
            "polarity": float(s.get("polarity", 0.0)),
            "legs": ["keywords"],
            "reasoning": _reasons_from_news_row(s),
        }

    for r in graph_out.get("relevance", []) or []:
        sym = r["symbol"]
        score = float(r["score"])
        if sym in merged:
            # Combine: keep the larger magnitude score, append leg + reasons
            row = merged[sym]
            if abs(score) > abs(row["composite_score"]):
                row["composite_score"] = score
                row["polarity"] = 1.0 if score > 0 else -1.0 if score < 0 else row["polarity"]
            if "graph_relevance" not in row["legs"]:
                row["legs"].append("graph_relevance")
            for reason in r.get("reasons", []):
                if reason not in row["reasoning"]:
                    row["reasoning"].append(reason)
        else:
            merged[sym] = {
                "symbol": sym,
                "name": None,
                "tier": None,
                "sector": None,
                "industry_code": None,
                "composite_score": score,
                "polarity": 1.0 if score > 0 else -1.0 if score < 0 else 0.0,
                "legs": ["graph_relevance"],
                "reasoning": list(r.get("reasons", [])),
            }

    # ── Rank + truncate ────────────────────────────────────────────
    ranked = [r for r in merged.values() if abs(r["composite_score"]) >= MIN_SCORE]
    ranked.sort(key=lambda r: abs(r["composite_score"]), reverse=True)
    ranked = ranked[:limit]

    # ── Industry view ──────────────────────────────────────────────
    industries = []
    for ind in (news_out.get("industries") or []):
        industries.append({
            "industry_code": ind["industry_code"],
            "polarity": float(ind.get("polarity", 0.0)),
            "strength": float(ind.get("strength", 0.0)),
            "contributing_keywords": list(ind.get("contributing_keywords", [])),
            "stocks": [
                r["symbol"] for r in ranked if r["industry_code"] == ind["industry_code"]
            ][:10],
        })

    return {
        "query": query,
        "expansion": _expansion_for_payload(expansion),
        "stocks": ranked,
        "by_industry": industries,
        "matched_keywords": news_out.get("matched_keywords", []),
        "matched_symbols": news_out.get("matched_symbols", []),
    }


def _reasons_from_news_row(s: dict) -> list[str]:
    """Build a human-readable reasoning trace from a news-impact stock row."""
    reasons: list[str] = []
    kws = s.get("contributing_keywords") or []
    inds = s.get("contributing_industries") or []
    if kws and inds:
        reasons.append(
            f"matched {', '.join(kws)} → {', '.join(inds)} (polarity {s.get('polarity', 0):+.1f})"
        )
    elif kws:
        reasons.append(f"matched keywords: {', '.join(kws)}")
    elif inds:
        reasons.append(f"in industries: {', '.join(inds)}")
    if s.get("direct_target"):
        reasons.append("direct target stock in news text")
    return reasons


def _expansion_for_payload(expansion: dict) -> dict:
    """Strip the `_raw` field for the public API; expose only the parsed view."""
    return {
        "keywords": expansion["keywords"],
        "commodities": expansion["commodities"],
        "industries": expansion["industries"],
        "themes": expansion["themes"],
        "substitutes_hint": expansion["substitutes_hint"],
        "interpretation": expansion["interpretation"],
    }
