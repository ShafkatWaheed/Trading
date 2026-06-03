"""Pre-earnings setup signal — composites 6 signals into "is the market
pricing in a beat, a miss, or noise?"

This is NOT an insider-trading detector — actual insider trading is rare
(SEC catches dozens of cases per year out of ~10K quarterly announcements,
base rate ~0.06%). Calling pre-earnings momentum "insider trading" would
generate a 99%+ false-positive rate.

What this IS: a composite "market positioning into earnings" view. Strong
agreement across price + volume + options + analyst revisions + short
interest + earnings beat history = the tape is pricing in a beat. Strong
disagreement = melt-up against fundamentals, often disappoints.

Components and their honest meaning:
  • days_to_earnings   — how close we are to the binary event
  • price_change_5d    — short-term tape direction
  • price_change_30d   — month-long lean
  • volume_vs_avg      — conviction behind the move
  • options_call_skew  — derivatives positioning (bullish/bearish/neutral)
  • analyst_revisions  — sell-side raising/cutting estimates (legal flow)
  • short_interest_chg — bears covering or doubling down
  • beat_streak        — base-rate prior from historical surprises

When fewer than 4 components are present, we return verdict "insufficient_data"
rather than guess. When the next earnings is >45 days out, verdict is
"no_earnings_imminent" — the signal isn't actionable until the event is closer.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Any
import logging

from src.utils.db import cache_get, cache_set

logger = logging.getLogger(__name__)

_CACHE_TTL_MINUTES = 6 * 60        # 6h default; bumped lower when earnings <5d away
_CACHE_TTL_MINUTES_NEAR = 60       # 1h when earnings within 5 days


def _days_until_next_earnings(symbol: str) -> tuple[int | None, str | None]:
    """Return (days_until, iso_date) for the next earnings, or (None, None)."""
    try:
        from src.data.gateway import DataGateway
        rows = DataGateway().get_earnings_calendar(symbol) or []
    except Exception:
        return None, None
    today = date.today()
    upcoming = []
    for r in rows:
        d_str = r.get("date")
        if not d_str:
            continue
        try:
            d = datetime.fromisoformat(str(d_str)[:10]).date()
        except Exception:
            continue
        # Only consider dates in the future, and only if EPS not yet reported
        if d >= today and r.get("eps_actual") is None:
            upcoming.append(d)
    if not upcoming:
        return None, None
    nxt = min(upcoming)
    return (nxt - today).days, nxt.isoformat()


def _price_and_volume_signals(symbol: str) -> dict:
    """Compute price change 5d/30d and volume vs 30d avg."""
    out: dict[str, Any] = {
        "price_change_5d_pct": None,
        "price_change_30d_pct": None,
        "volume_vs_30d_avg_pct": None,
    }
    try:
        from src.data.gateway import DataGateway
        hist = DataGateway().get_historical(symbol, period_days=90)
    except Exception:
        return out
    if hist is None or len(hist) < 31:
        return out
    closes = list(hist["close"])
    vols = list(hist["volume"]) if "volume" in hist.columns else []
    last = float(closes[-1])
    try:
        d5 = float(closes[-6])
        out["price_change_5d_pct"] = round((last - d5) / d5 * 100, 2) if d5 > 0 else None
    except Exception:
        pass
    try:
        d30 = float(closes[-31])
        out["price_change_30d_pct"] = round((last - d30) / d30 * 100, 2) if d30 > 0 else None
    except Exception:
        pass
    try:
        if len(vols) >= 31:
            recent_vol = float(vols[-1])
            avg30 = sum(float(v) for v in vols[-31:-1]) / 30.0
            if avg30 > 0:
                out["volume_vs_30d_avg_pct"] = round((recent_vol - avg30) / avg30 * 100, 2)
    except Exception:
        pass
    return out


def _options_skew(symbol: str) -> dict:
    """Pull options put/call ratio + IV rank if available."""
    out: dict[str, Any] = {"put_call_ratio": None, "iv_rank": None, "skew_tone": None}
    try:
        from api.services import options_flow_service
        o = options_flow_service.get_options_flow(symbol)
        if not isinstance(o, dict):
            return out
        pcr = o.get("put_call_ratio")
        out["put_call_ratio"] = round(float(pcr), 2) if pcr is not None else None
        out["iv_rank"] = o.get("iv_rank")
        # Tone: <0.7 = bullish positioning (more calls), >1.0 = bearish, else neutral
        if pcr is not None:
            if pcr < 0.7:
                out["skew_tone"] = "bullish"
            elif pcr > 1.0:
                out["skew_tone"] = "bearish"
            else:
                out["skew_tone"] = "neutral"
    except Exception as e:
        logger.info("pre-earnings: options skew failed for %s: %r", symbol, e)
    return out


def _analyst_revisions(symbol: str) -> dict:
    """Pull recent analyst revision tilt."""
    out: dict[str, Any] = {
        "raises_30d": None, "cuts_30d": None, "net_revision_tone": None,
    }
    try:
        from api.services import estimate_revisions_service
        e = estimate_revisions_service.get_estimate_revisions(symbol)
        if not isinstance(e, dict):
            return out
        # rating_actions contains "upgrade", "downgrade", "initiate", "reiterate"
        actions = e.get("rating_actions") or []
        up = down = 0
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        for a in actions:
            d = (a.get("date") or "")[:10]
            if d < cutoff:
                continue
            action = (a.get("action") or "").lower()
            if "upgrade" in action or "raise" in action:
                up += 1
            elif "downgrade" in action or "cut" in action or "lower" in action:
                down += 1
        out["raises_30d"] = up
        out["cuts_30d"] = down
        if up > down + 1:
            out["net_revision_tone"] = "bullish"
        elif down > up + 1:
            out["net_revision_tone"] = "bearish"
        else:
            out["net_revision_tone"] = "neutral"
    except Exception as e:
        logger.info("pre-earnings: analyst revisions failed for %s: %r", symbol, e)
    return out


def _short_interest_change(symbol: str) -> dict:
    """Short interest level + recent change direction."""
    out: dict[str, Any] = {
        "short_pct_float": None, "short_change_tone": None,
    }
    try:
        from src.data.gateway import DataGateway
        si = DataGateway().get_short_interest(symbol)
        if not isinstance(si, dict):
            return out
        sp = si.get("short_pct_float")
        out["short_pct_float"] = round(float(sp), 2) if sp is not None else None
        # Without a historical short series we can't compute change reliably.
        # Heuristic: high short interest (>10%) is a setup for either squeeze or pain.
        if sp is not None:
            if sp > 15:
                out["short_change_tone"] = "squeeze_setup"
            elif sp < 3:
                out["short_change_tone"] = "low_short_pressure"
            else:
                out["short_change_tone"] = "moderate"
    except Exception as e:
        logger.info("pre-earnings: short interest failed for %s: %r", symbol, e)
    return out


def _recent_news_split(symbol: str) -> dict:
    """Pull recent positive + negative headlines from the cached news feed,
    filtered to items materially relevant to the upcoming print.

    Filter logic:
      1. Fetch the cached news_feed
      2. Classify every item via news_relevance_service (Claude, batched)
      3. Keep only items in EARNINGS_RELEVANT categories
         (earnings_preview / channel_check / analyst_revision / product_news)
      4. Split the kept items by sentiment (bullish / bearish)
      5. Tag each surfaced item with its relevance category so the UI can
         show "PREVIEW" / "CHANNEL CHECK" / "ANALYST" / "PRODUCT"

    The relevance filter degrades gracefully — if the Claude call fails or
    times out, we fall back to surfacing everything (old behavior).
    """
    out: dict = {"bullish": [], "bearish": [], "net_sentiment": None, "source_warning": None}
    try:
        from api.services import news_feed_service, news_relevance_service
        nf = news_feed_service.get_news_feed(symbol)
        if not isinstance(nf, dict):
            return out
        items = nf.get("items") or []
        if not items:
            return out

        # Tag every item with a relevance category. Cached 6h.
        try:
            categories = news_relevance_service.classify_items(symbol, items)
        except Exception as e:
            logger.info("pre-earnings: relevance classify failed for %s: %r", symbol, e)
            categories = ["general"] * len(items)

        # Attach category to each item, then sort by published desc
        tagged = []
        for i, cat in zip(items, categories):
            i2 = dict(i)
            i2["category"] = cat
            tagged.append(i2)

        def _pub_key(i: dict):
            return (i.get("published") or "", i.get("sentiment_score") or 0)
        items_sorted = sorted(tagged, key=_pub_key, reverse=True)

        # Filter to earnings-relevant categories — drops generic "Y bought
        # N shares" and broad listicles. If the filtered list is empty
        # (Claude tagged everything as general, or the relevance call failed
        # silently), fall back to ALL items so we don't show nothing.
        relevant = [
            i for i in items_sorted
            if i.get("category") in news_relevance_service.EARNINGS_RELEVANT
        ]
        if not relevant:
            relevant = items_sorted

        def _to_item(i: dict) -> dict:
            return {
                "title":   (i.get("title") or "")[:160],
                "url":     i.get("url") or "",
                "source":  i.get("source") or "",
                "published": i.get("published"),
                "sentiment_score": i.get("sentiment_score"),
                "category": i.get("category") or "general",
            }

        bullish = [_to_item(i) for i in relevant if i.get("sentiment") == "bullish"][:4]
        bearish = [_to_item(i) for i in relevant if i.get("sentiment") == "bearish"][:4]
        out["bullish"] = bullish
        out["bearish"] = bearish
        out["net_sentiment"] = nf.get("net_sentiment")
        out["source_warning"] = nf.get("source_warning")
    except Exception as e:
        logger.info("pre-earnings: news split failed for %s: %r", symbol, e)
    return out


def _beat_streak(symbol: str) -> dict:
    """How often has the company beaten the last 4 reported quarters."""
    out: dict[str, Any] = {
        "quarters_examined": 0, "beats": 0, "misses": 0, "avg_surprise_pct": None,
    }
    try:
        from src.data.gateway import DataGateway
        rows = DataGateway().get_earnings_calendar(symbol) or []
    except Exception:
        return out
    reported = [r for r in rows if r.get("eps_actual") is not None and r.get("eps_estimate") is not None]
    reported = reported[:6]
    if not reported:
        return out
    beats = misses = 0
    surprises = []
    for r in reported:
        try:
            act = float(r["eps_actual"])
            est = float(r["eps_estimate"])
            if est > 0:
                pct = (act - est) / abs(est) * 100
                surprises.append(pct)
            if act > est:
                beats += 1
            elif act < est:
                misses += 1
        except Exception:
            pass
    out["quarters_examined"] = len(reported)
    out["beats"] = beats
    out["misses"] = misses
    out["avg_surprise_pct"] = round(sum(surprises) / len(surprises), 2) if surprises else None
    return out


# ── Composite verdict ──────────────────────────────────────────────


def _classify_signal(*, days: int | None, price_5d: float | None, price_30d: float | None,
                     vol_pct: float | None, skew_tone: str | None,
                     rev_tone: str | None, beat_rate: float | None) -> tuple[str, list[dict], float]:
    """Score each component as +1 / 0 / -1 toward "pricing in a beat".

    Returns (verdict, signal_breakdown, score_-100..+100).
    """
    breakdown: list[dict] = []
    score = 0
    weight = 0

    def add(label: str, tone: str, value: str):
        nonlocal score, weight
        if tone == "positive":
            score += 1
        elif tone == "negative":
            score -= 1
        weight += 1
        breakdown.append({"label": label, "tone": tone, "value": value})

    if price_5d is not None:
        if price_5d > 2:
            add("price 5d", "positive", f"+{price_5d:.1f}%")
        elif price_5d < -2:
            add("price 5d", "negative", f"{price_5d:.1f}%")
        else:
            add("price 5d", "neutral", f"{price_5d:+.1f}%")
    if price_30d is not None:
        if price_30d > 5:
            add("price 30d", "positive", f"+{price_30d:.1f}%")
        elif price_30d < -5:
            add("price 30d", "negative", f"{price_30d:.1f}%")
        else:
            add("price 30d", "neutral", f"{price_30d:+.1f}%")
    if vol_pct is not None:
        if vol_pct > 20:
            add("volume vs avg", "positive", f"+{vol_pct:.0f}%")
        elif vol_pct < -20:
            add("volume vs avg", "negative", f"{vol_pct:.0f}%")
        else:
            add("volume vs avg", "neutral", f"{vol_pct:+.0f}%")
    if skew_tone:
        tone = "positive" if skew_tone == "bullish" else "negative" if skew_tone == "bearish" else "neutral"
        add("options skew", tone, skew_tone)
    if rev_tone:
        tone = "positive" if rev_tone == "bullish" else "negative" if rev_tone == "bearish" else "neutral"
        add("analyst revisions", tone, rev_tone)
    if beat_rate is not None:
        if beat_rate >= 0.75:
            add("beat history", "positive", f"{int(beat_rate*100)}% beat rate")
        elif beat_rate <= 0.25:
            add("beat history", "negative", f"{int(beat_rate*100)}% beat rate")
        else:
            add("beat history", "neutral", f"{int(beat_rate*100)}% beat rate")

    if weight < 4:
        return "insufficient_data", breakdown, 0.0
    if days is not None and days > 45:
        return "no_earnings_imminent", breakdown, round(100 * score / max(weight, 1), 1)

    normalized = round(100 * score / weight, 1)  # -100 (full miss) to +100 (full beat)
    if normalized >= 50:
        verdict = "pricing_in_beat"
    elif normalized >= 20:
        verdict = "leaning_bullish"
    elif normalized > -20:
        verdict = "mixed"
    elif normalized > -50:
        verdict = "leaning_bearish"
    else:
        verdict = "pricing_in_miss"
    return verdict, breakdown, normalized


def get_pre_earnings_setup(symbol: str, force: bool = False) -> dict:
    """Public entry. Returns the composite pre-earnings setup payload."""
    symbol = symbol.upper()
    cache_key = f"pre_earnings_setup:v1:{symbol}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    days, next_date = _days_until_next_earnings(symbol)
    pv = _price_and_volume_signals(symbol)
    skew = _options_skew(symbol)
    rev = _analyst_revisions(symbol)
    short = _short_interest_change(symbol)
    beats = _beat_streak(symbol)
    news = _recent_news_split(symbol)

    beat_rate = None
    if beats.get("quarters_examined", 0) > 0:
        beat_rate = beats["beats"] / beats["quarters_examined"]

    verdict, breakdown, normalized_score = _classify_signal(
        days=days,
        price_5d=pv["price_change_5d_pct"],
        price_30d=pv["price_change_30d_pct"],
        vol_pct=pv["volume_vs_30d_avg_pct"],
        skew_tone=skew.get("skew_tone"),
        rev_tone=rev.get("net_revision_tone"),
        beat_rate=beat_rate,
    )

    headline = _verdict_headline(verdict, days, normalized_score)

    payload = {
        "symbol": symbol,
        "verdict": verdict,
        "headline": headline,
        "score": normalized_score,
        "days_to_next_earnings": days,
        "next_earnings_date": next_date,
        "signals": breakdown,
        "components": {
            **pv,
            **skew,
            **rev,
            **short,
            "beats_examined": beats.get("quarters_examined"),
            "beats": beats.get("beats"),
            "misses": beats.get("misses"),
            "avg_surprise_pct": beats.get("avg_surprise_pct"),
            "beat_rate_pct": round(beat_rate * 100, 1) if beat_rate is not None else None,
        },
        "recent_news": {
            "bullish":         news.get("bullish") or [],
            "bearish":         news.get("bearish") or [],
            "net_sentiment":   news.get("net_sentiment"),
            "source_warning":  news.get("source_warning"),
        },
        "disclaimer": (
            "This is NOT an insider-trading detector. It's a composite view of "
            "how the tape is positioning into the binary earnings event. Use "
            "in combination with bull/risk theses — not in isolation."
        ),
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "from_cache": False,
    }

    ttl = _CACHE_TTL_MINUTES_NEAR if (days is not None and days <= 5) else _CACHE_TTL_MINUTES
    # Don't cache "insufficient_data" — caller may want a retry once data lands.
    if verdict != "insufficient_data":
        try:
            cache_set(cache_key, payload, ttl_minutes=ttl)
        except Exception:
            pass
    return payload


def _verdict_headline(verdict: str, days: int | None, score: float) -> str:
    when = f"({days}d to earnings)" if days is not None else ""
    if verdict == "pricing_in_beat":
        return f"Tape is pricing in a beat {when} — multiple signals agree".strip()
    if verdict == "leaning_bullish":
        return f"Modestly bullish setup {when}".strip()
    if verdict == "mixed":
        return f"Mixed signals into earnings {when} — no clear positioning".strip()
    if verdict == "leaning_bearish":
        return f"Modestly bearish setup {when}".strip()
    if verdict == "pricing_in_miss":
        return f"Tape is pricing in a miss {when} — multiple signals agree".strip()
    if verdict == "no_earnings_imminent":
        return "No earnings within 45 days — setup not yet meaningful"
    return "Insufficient data — fewer than 4 components available"
