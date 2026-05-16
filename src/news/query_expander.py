"""LLM query expander (Tier 1 of Context Search).

Translates a free-text user query into the structured themes the graph
already understands. Single Claude call per query (Haiku via subprocess CLI),
~$0.001 per request.

Output shape (consumed by `context_search_service`):

    {
        "keywords":   [str, ...],          # for the keyword news engine
        "commodities": [{"code": str, "direction": "up"|"down", "intensity": float}, ...],
        "industries": [{"code": str, "polarity": float}, ...],
        "themes":     [str, ...],          # short labels for UI grouping
        "substitutes_hint": [str, ...],    # "EVs benefit from high oil" etc.
        "interpretation": str,             # one-sentence plain-language readback
        "_raw":   dict | None,             # raw LLM JSON for debugging
    }

If the LLM call fails or returns garbage, returns a safe empty expansion so
the downstream pipeline degrades gracefully (the user just gets the
keyword-only result from raw tokenizing).
"""

from __future__ import annotations

import sqlite3

from src.utils.claude_cli import ask_claude_json
from src.utils.db import get_connection, init_db


def _commodity_codes() -> list[str]:
    init_db()
    conn = get_connection()
    try:
        return [r[0] for r in conn.execute("SELECT code FROM commodities ORDER BY code").fetchall()]
    finally:
        conn.close()


def _industry_codes(limit: int = 200) -> list[str]:
    init_db()
    conn = get_connection()
    try:
        return [
            r[0]
            for r in conn.execute(
                "SELECT code FROM industries ORDER BY code LIMIT ?", (limit,)
            ).fetchall()
        ]
    finally:
        conn.close()


# Cache the lookups for the lifetime of the process — these change rarely.
_LOOKUPS_CACHE: dict | None = None


def _lookups() -> dict:
    global _LOOKUPS_CACHE
    if _LOOKUPS_CACHE is None:
        _LOOKUPS_CACHE = {
            "commodities": _commodity_codes(),
            "industries": _industry_codes(),
        }
    return _LOOKUPS_CACHE


def _build_prompt(query: str) -> str:
    lookups = _lookups()
    commodities = ", ".join(lookups["commodities"])
    # Industries can be long — show the first 80 plus the total count so the
    # model picks from the canonical list but isn't drowned.
    industries_sample = ", ".join(lookups["industries"][:80])
    industries_count = len(lookups["industries"])

    return f"""You translate free-text market scenarios into a structured set of
themes the knowledge graph understands. The graph knows commodities,
industries, and a small keyword catalogue. Your job: given the user's query,
return the relevant themes the graph should activate, with directions and
intensities.

User query:
\"\"\"{query}\"\"\"

Canonical commodity codes (you MUST pick from this list — others will be ignored):
{commodities}

Canonical industry codes (a sample of {industries_count}; you may use ones close
to those listed, but exact yfinance industry names work best):
{industries_sample}

Reasoning rules:
- Think through 1st-, 2nd-, and 3rd-order effects. Example: middle-east oil
  supply shock → (1st) crude up, (2nd) defense up + airlines down + refiner
  squeeze, (3rd) fertilizer cost up via gas-coupling + EV demand boost.
- For each commodity, give "up" or "down" + intensity 0.1–1.0.
- For each industry, give polarity in [-1, 1] (positive = beneficiary).
- Keywords are short phrases the news tokenizer will match against (max 5 words each).
- substitutes_hint lists named substitution links the graph should explore
  (e.g. "EVs vs ICE on high oil", "GLP-1 weight loss vs processed food").

Return ONLY a JSON object with this exact shape:

{{
  "keywords": ["war", "opec", "supply disruption"],
  "commodities": [
    {{"code": "crude_oil", "direction": "up", "intensity": 0.9}}
  ],
  "industries": [
    {{"code": "Aerospace & Defense", "polarity": 0.7}},
    {{"code": "Airlines", "polarity": -0.5}}
  ],
  "themes": ["supply_shock", "geopolitical_risk"],
  "substitutes_hint": ["EVs benefit from high oil prices"],
  "interpretation": "One short sentence summarising what the user is asking about."
}}

If the query doesn't imply any market impact, return an empty expansion with
arrays empty and a brief interpretation explaining that."""


def _coerce_str_list(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if x and isinstance(x, (str, int, float))]


def _coerce_commodities(raw, valid: set[str]) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip().lower()
        if code not in valid:
            continue
        direction = str(item.get("direction") or "up").lower()
        if direction not in ("up", "down"):
            direction = "up"
        try:
            intensity = float(item.get("intensity", 1.0))
        except (TypeError, ValueError):
            intensity = 1.0
        intensity = max(0.0, min(1.0, intensity))
        out.append({"code": code, "direction": direction, "intensity": intensity})
    return out


def _coerce_industries(raw, valid_lower: set[str]) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip()
        if not code:
            continue
        # Industries are case-sensitive in the DB ("Aerospace & Defense"). We
        # accept any case from the LLM and let the downstream match handle the
        # canonical form — but we drop industries we don't recognise to avoid
        # garbage.
        if code.lower() not in valid_lower:
            continue
        try:
            polarity = float(item.get("polarity", 0.0))
        except (TypeError, ValueError):
            polarity = 0.0
        polarity = max(-1.0, min(1.0, polarity))
        out.append({"code": code, "polarity": polarity})
    return out


def expand_query(query: str, *, model: str = "haiku") -> dict:
    """Return a structured expansion of the free-text query.

    Always returns a dict in the documented shape; failure modes return an
    empty expansion rather than raising so the caller can fall back to plain
    keyword matching.
    """
    query = (query or "").strip()
    if not query:
        return _empty(reason="empty query")

    prompt = _build_prompt(query)
    raw = ask_claude_json(prompt, model=model, timeout=45)
    if not isinstance(raw, dict):
        return _empty(reason="claude returned no JSON", raw=raw)

    lookups = _lookups()
    valid_commodities = set(lookups["commodities"])
    valid_industries_lower = {i.lower() for i in lookups["industries"]}

    return {
        "keywords": _coerce_str_list(raw.get("keywords"))[:30],
        "commodities": _coerce_commodities(raw.get("commodities"), valid_commodities),
        "industries": _coerce_industries(raw.get("industries"), valid_industries_lower),
        "themes": _coerce_str_list(raw.get("themes"))[:10],
        "substitutes_hint": _coerce_str_list(raw.get("substitutes_hint"))[:10],
        "interpretation": str(raw.get("interpretation", ""))[:400],
        "_raw": raw,
    }


def _empty(*, reason: str, raw: object = None) -> dict:
    return {
        "keywords": [],
        "commodities": [],
        "industries": [],
        "themes": [],
        "substitutes_hint": [],
        "interpretation": reason,
        "_raw": raw if isinstance(raw, (dict, list)) else None,
    }
