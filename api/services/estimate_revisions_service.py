"""Estimate revisions service — analyst rating actions + EPS estimate trend.

Combines three Finnhub endpoints into a single story-driven payload:
  * get_upgrades_downgrades — recent rating actions, counts net-ups vs net-downs
  * get_recommendation_trend — current buy/hold/sell consensus + 90-day shift
  * get_eps_estimates — direction of forward EPS estimate revisions

Why this matters: direction-of-change in analyst estimates is one of the
strongest near-term price predictors (PEAD literature). Level matters less
than slope.

Yahoo Finance fallback: Finnhub's free tier has paywalled /stock/upgrade-downgrade
and sometimes the recommendation-trend endpoint. We read the existing cached
`market:fundamentals:{symbol}` payload first (yfinance.info), then fall back
to a live yfinance fetch only if the cache is empty. Yahoo gives us:
  • recommendationKey / recommendationMean → consensus when Finnhub is empty
  • targetMean/High/Low/MedianPrice → price targets (Finnhub free doesn't have)
  • numberOfAnalystOpinions → analyst count
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.data import finnhub as finnhub_data
from src.utils.config import FINNHUB_API_KEY
from src.utils.db import cache_get, cache_set

logger = logging.getLogger(__name__)

_CACHE_TTL_MINUTES = 12 * 60  # estimates don't move intraday

# Recency windows for counting actions
_WINDOW_DAYS = 30


def _empty(symbol: str, reason: str) -> dict:
    return {
        "symbol": symbol,
        "available": False,
        "reason": reason,
        "lede": None,
        "net_change_30d": 0,
        "upgrades_30d": 0,
        "downgrades_30d": 0,
        "initiations_30d": 0,
        "consensus": None,
        "consensus_shift": None,
        "eps_trend": None,
        "recent_actions": [],
        "price_targets": None,
        "analyst_count": None,
        "source": None,
        "from_cache": False,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }


def _yahoo_to_float(v) -> float | None:
    if v is None or v == "" or v == "0":
        return None
    try:
        f = float(v)
        return f if f != 0 else None
    except (TypeError, ValueError):
        return None


_YAHOO_REC_KEY_TO_CONSENSUS = {
    "strong_buy":   "Strong Buy",
    "buy":          "Buy",
    "hold":         "Hold",
    "sell":         "Sell",
    "strong_sell":  "Strong Sell",
    "underperform": "Sell",       # yfinance variant
    "outperform":   "Buy",        # yfinance variant
}


def _yahoo_analyst_data(symbol: str) -> dict:
    """Return Yahoo's analyst snapshot — cached fundamentals first, live yfinance second.

    Returns a dict (possibly with all-None values). Never raises; logs and
    falls through on any error so the calling pipeline keeps working.
    """
    out = {
        "consensus": None,
        "rec_mean": None,
        "analyst_count": None,
        "target_mean": None,
        "target_high": None,
        "target_low": None,
        "target_median": None,
    }

    # 1) Try the existing cached fundamentals payload (24h TTL, no extra fetch).
    fund = cache_get(f"market:fundamentals:{symbol}") or {}
    if fund:
        rec_key = (fund.get("recommendation_key") or "").lower()
        if rec_key in _YAHOO_REC_KEY_TO_CONSENSUS:
            out["consensus"] = _YAHOO_REC_KEY_TO_CONSENSUS[rec_key]
        out["rec_mean"]      = _yahoo_to_float(fund.get("recommendation_mean"))
        out["analyst_count"] = _yahoo_to_float(fund.get("number_of_analyst_opinions"))
        out["target_mean"]   = _yahoo_to_float(fund.get("target_mean_price"))
        out["target_high"]   = _yahoo_to_float(fund.get("target_high_price"))
        out["target_low"]    = _yahoo_to_float(fund.get("target_low_price"))
        out["target_median"] = _yahoo_to_float(fund.get("target_median_price"))

    # 2) If the cached payload doesn't carry these (older cache version), pull
    #    live. yfinance is rate-friendly here — info is a single endpoint.
    if all(v is None for v in out.values()):
        try:
            import yfinance as yf
            info = yf.Ticker(symbol).info or {}
            rec_key = (info.get("recommendationKey") or "").lower()
            if rec_key in _YAHOO_REC_KEY_TO_CONSENSUS:
                out["consensus"] = _YAHOO_REC_KEY_TO_CONSENSUS[rec_key]
            out["rec_mean"]      = _yahoo_to_float(info.get("recommendationMean"))
            out["analyst_count"] = _yahoo_to_float(info.get("numberOfAnalystOpinions"))
            out["target_mean"]   = _yahoo_to_float(info.get("targetMeanPrice"))
            out["target_high"]   = _yahoo_to_float(info.get("targetHighPrice"))
            out["target_low"]    = _yahoo_to_float(info.get("targetLowPrice"))
            out["target_median"] = _yahoo_to_float(info.get("targetMedianPrice"))
        except Exception as e:
            logger.warning("yahoo analyst fallback failed for %s: %r", symbol, e)

    if out["analyst_count"] is not None:
        out["analyst_count"] = int(out["analyst_count"])

    return out


def _classify_action(action: str | None) -> str:
    """Finnhub uses 'up'/'down'/'main'/'init' — normalize to category."""
    if not action:
        return "other"
    a = action.lower()
    if a == "up":   return "upgrade"
    if a == "down": return "downgrade"
    if a == "init": return "initiation"
    if a == "main": return "reiteration"
    return "other"


def _window_filter(rows: list[dict], days: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
    return [r for r in rows if (r.get("gradeTime") or 0) >= cutoff]


def _compose_lede(
    net: int, ups: int, downs: int, inits: int,
    consensus: str | None,
    *,
    has_actions_feed: bool = True,
    price_target_pct: float | None = None,
    analyst_count: int | None = None,
) -> str:
    """One-line interpretation of the rating-action flow.

    When the upgrade/downgrade feed isn't available (Finnhub free-tier
    paywall), shift the framing to the data we DO have: consensus + target
    implied upside / downside. Otherwise the user just sees a misleading
    "no recent rating action" line.
    """
    # No rating-action stream from the provider — lean on consensus + targets.
    if not has_actions_feed:
        bits: list[str] = []
        if consensus:
            who = f" ({analyst_count} analysts)" if analyst_count else ""
            bits.append(f"Consensus is {consensus}{who}")
        if price_target_pct is not None:
            direction = "above" if price_target_pct >= 0 else "below"
            bits.append(f"Average target sits {abs(price_target_pct):.0f}% {direction} the current price")
        if bits:
            return ". ".join(bits) + "."
        return "Analyst data isn't available for this stock right now."

    # Standard path — Finnhub gave us the upgrade/downgrade stream.
    pieces = []
    if ups or downs:
        pieces.append(f"{ups} upgrade{'' if ups == 1 else 's'} vs {downs} downgrade{'' if downs == 1 else 's'} in 30 days")
    if inits:
        pieces.append(f"{inits} new coverage initiation{'' if inits == 1 else 's'}")
    flow = "; ".join(pieces) if pieces else "no recent rating action"

    if net >= 3:
        return f"Analyst momentum is strongly positive — {flow}. Estimates are moving up."
    if net >= 1:
        return f"Analyst tone is improving — {flow}."
    if net <= -3:
        return f"Analyst momentum is sharply negative — {flow}. Estimates are being cut."
    if net <= -1:
        return f"Analyst tone is softening — {flow}."
    if consensus:
        return f"Analysts are quiet — {flow}. Consensus remains {consensus}."
    return f"Analysts are quiet — {flow}."


def _eps_trend(rows: list[dict] | None) -> dict | None:
    """Take quarterly EPS estimate rows and compute the implied growth slope."""
    if not rows:
        return None
    # Finnhub returns rows for past + future quarters; keep only future ones
    today_iso = datetime.utcnow().date().isoformat()
    future = sorted([r for r in rows if (r.get("period") or "") >= today_iso],
                    key=lambda r: r.get("period") or "")[:4]
    if not future:
        return None
    next_q = future[0]
    out = {
        "next_period":   next_q.get("period"),
        "next_eps_avg":  next_q.get("epsAvg"),
        "next_eps_high": next_q.get("epsHigh"),
        "next_eps_low":  next_q.get("epsLow"),
        "analyst_count": next_q.get("numberAnalysts"),
        "fy_path": [
            {"period": r.get("period"), "eps_avg": r.get("epsAvg")}
            for r in future
        ],
    }
    # Slope: last future quarter vs next
    if len(future) >= 2 and next_q.get("epsAvg") is not None:
        last = future[-1].get("epsAvg")
        first = next_q.get("epsAvg")
        if last is not None and first not in (None, 0):
            try:
                out["growth_pct"] = round(((float(last) - float(first)) / abs(float(first))) * 100.0, 1)
            except (TypeError, ValueError, ZeroDivisionError):
                out["growth_pct"] = None
    return out


def _consensus_label(row: dict) -> str:
    """Turn a Finnhub recommendation row into Strong Buy/Buy/Hold/Sell."""
    sb = row.get("strongBuy") or 0
    b  = row.get("buy") or 0
    h  = row.get("hold") or 0
    s  = row.get("sell") or 0
    ss = row.get("strongSell") or 0
    total = sb + b + h + s + ss
    if total == 0:
        return "no coverage"
    # Weighted mean (1=StrongBuy, 5=StrongSell, like Yahoo's rating_mean)
    score = (1*sb + 2*b + 3*h + 4*s + 5*ss) / total
    if score < 1.5:  return "Strong Buy"
    if score < 2.5:  return "Buy"
    if score < 3.5:  return "Hold"
    if score < 4.5:  return "Sell"
    return "Strong Sell"


def get_estimate_revisions(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"estimate_revisions:v1:{symbol}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    # No early return on missing FINNHUB_API_KEY anymore — Yahoo can carry the
    # card alone (consensus + price targets) even without a Finnhub subscription.

    # Finnhub feeds — note: free-tier paywalls /stock/upgrade-downgrade,
    # so `upgrades_raw` is typically None for free-tier users. We still try
    # Finnhub first (returns rec_trend on free) and fall back to Yahoo below.
    finnhub_available = bool(FINNHUB_API_KEY)
    upgrades_raw = finnhub_data.get_upgrades_downgrades(symbol) if finnhub_available else None
    rec_trend    = finnhub_data.get_recommendation_trend(symbol) if finnhub_available else None
    eps_rows     = finnhub_data.get_eps_estimates(symbol) if finnhub_available else None

    has_actions_feed = upgrades_raw is not None      # None == endpoint failed/paywalled
    upgrades = upgrades_raw or []
    rec_trend = rec_trend or []

    # 30-day action tally
    recent = _window_filter(upgrades, _WINDOW_DAYS)
    ups = sum(1 for r in recent if _classify_action(r.get("action")) == "upgrade")
    downs = sum(1 for r in recent if _classify_action(r.get("action")) == "downgrade")
    inits = sum(1 for r in recent if _classify_action(r.get("action")) == "initiation")
    net = ups - downs

    # Consensus shift: compare most recent rec_trend row vs ~90d prior
    consensus = consensus_shift = None
    if rec_trend:
        sorted_rt = sorted(rec_trend, key=lambda r: r.get("period") or "", reverse=True)
        latest = sorted_rt[0]
        consensus = _consensus_label(latest)
        if len(sorted_rt) >= 4:
            prior = sorted_rt[3]
            prior_label = _consensus_label(prior)
            if prior_label != consensus:
                consensus_shift = f"{prior_label} → {consensus} over 90 days"

    # Yahoo fallback — net-new fields (price targets) + consensus backstop.
    yahoo = _yahoo_analyst_data(symbol)
    if consensus is None and yahoo["consensus"]:
        consensus = yahoo["consensus"]

    price_targets = None
    target_pct_vs_current = None
    if yahoo["target_mean"] is not None:
        price_targets = {
            "mean":   yahoo["target_mean"],
            "high":   yahoo["target_high"],
            "low":    yahoo["target_low"],
            "median": yahoo["target_median"],
        }
        # Current price for upside math — quote lives in `market:quote:` not
        # `market:fundamentals:`. Fall back to a live yfinance regularMarketPrice
        # if neither cache has it.
        quote = cache_get(f"market:quote:{symbol}") or {}
        current_price = _yahoo_to_float(quote.get("price"))
        if current_price is None:
            try:
                import yfinance as yf
                current_price = _yahoo_to_float(
                    (yf.Ticker(symbol).info or {}).get("regularMarketPrice")
                )
            except Exception:
                current_price = None
        if current_price and current_price > 0:
            target_pct_vs_current = ((yahoo["target_mean"] - current_price) / current_price) * 100.0

    analyst_count = yahoo["analyst_count"]

    # Source tag — surfaces in the UI as a small "powered by" footer.
    if has_actions_feed and rec_trend:
        source = "Finnhub"
    elif rec_trend:
        source = "Finnhub (consensus only)"
    elif yahoo["consensus"] or price_targets:
        source = "Yahoo Finance"
    else:
        source = None

    # Format recent actions for the UI (sorted newest first)
    actions_out: list[dict] = []
    for r in sorted(recent, key=lambda x: x.get("gradeTime") or 0, reverse=True)[:8]:
        ts = r.get("gradeTime") or 0
        actions_out.append({
            "action": _classify_action(r.get("action")),
            "firm": r.get("company") or "",
            "from_grade": r.get("fromGrade") or "",
            "to_grade": r.get("toGrade") or "",
            "date": datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if ts else "",
        })

    eps_trend = _eps_trend(eps_rows)

    payload = {
        "symbol": symbol,
        "available": bool(consensus or price_targets or recent or eps_trend),
        "reason": None,
        "lede": _compose_lede(
            net, ups, downs, inits, consensus,
            has_actions_feed=has_actions_feed,
            price_target_pct=target_pct_vs_current,
            analyst_count=analyst_count,
        ),
        "net_change_30d": net,
        "upgrades_30d": ups,
        "downgrades_30d": downs,
        "initiations_30d": inits,
        "consensus": consensus,
        "consensus_shift": consensus_shift,
        "eps_trend": eps_trend,
        "recent_actions": actions_out,
        "price_targets": price_targets,
        "analyst_count": analyst_count,
        "source": source,
        "from_cache": False,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return payload
