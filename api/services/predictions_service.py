"""Daily top-10 gainers predictions.

Pipeline
--------
Each morning (pre-market) we score every Tier A symbol using the active
strategy and store the top 10 picks. After market close we record each
pick's actual % move so accuracy can be tracked over time. Claude
periodically reviews a window of completed predictions and proposes a
new strategy version; old versions are kept for comparison.

Point-in-time guarantee
-----------------------
- Predictions for date `D` are generated PRE-OPEN of `D` using only
  data available at or before the close of `D-1`. No current-day data.
- Actuals for date `D` are stamped AFTER `D` market close.
- Strategy reviews look only at rows where `actuals` is recorded — the
  in-flight day is never used for training.

Phase 1 scope (this file)
-------------------------
- Schema bootstrap (a baseline strategy is auto-inserted on first call)
- `generate_predictions_for_date(date)` — score Tier A, pick top 10,
  persist to `daily_predictions`. Idempotent: returns the existing rows
  if predictions for that date are already stored.
- `get_predictions_for_date(date)` — read-only fetch
- `get_predictions_today()` — convenience wrapper

Baseline strategy v1
--------------------
"5d momentum" — rank by trailing 5-day % change. Deliberately simple
so Claude has clear room to improve it. Each pick carries a 1-line
reasoning string for the UI.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

from src.data.gateway import DataGateway
from src.utils.claude_cli import ask_claude_json
from src.utils.db import cache_get, cache_set, get_connection, init_db

# market_service is imported lazily inside _pulse_context to avoid a circular
# import (market_service → other services → predictions_service in some paths).

logger = logging.getLogger(__name__)


_BASELINE_STRATEGY = {
    "name": "5d_momentum_v1",
    "description": (
        "Baseline: rank Tier A by trailing 5-day % return; pick top 10. "
        "Deliberately simple so Claude has room to improve it with "
        "catalysts, sector strength, oversold-bounce signals, etc."
    ),
    "config": {
        "ranking_signal": "change_5d",
        "lookback_days": 5,
        "universe_tier": "A",
        "min_history_days": 6,    # need at least 6 bars to compute change_5d
        "top_n": 10,
    },
}


# ── Market Pulse context (Phase 4) ─────────────────────────────────────


_PULSE_TOP_SECTORS_N = 3


def _pulse_context() -> dict:
    """Pull the current Market Pulse and extract the bits relevant to
    prediction scoring: regime + top-N sectors by flow.

    Returns:
      {
        "regime":           "bull" | "bear" | "neutral" | "unclear",
        "top_sectors":      ["Technology", "Energy", "Healthcare"],
        "top_sectors_flow": {"Technology": 1.2, "Energy": 0.8, ...},
      }
    Returns an empty dict if the pulse is unavailable — callers must
    treat that as "no pulse signal available".
    """
    try:
        from api.services import market_service
        pulse = market_service.get_pulse(period="1M") or {}
    except Exception as e:
        logger.info("predictions: pulse fetch failed: %r", e)
        return {}

    regime = pulse.get("regime") or "unclear"
    flows = pulse.get("sector_flows") or []
    # Highest change_pct first; ignore sectors with missing data.
    flows_sorted = sorted(
        (f for f in flows if isinstance(f, dict) and f.get("sector")),
        key=lambda f: float(f.get("change_pct") or 0.0),
        reverse=True,
    )
    top = flows_sorted[:_PULSE_TOP_SECTORS_N]
    return {
        "regime":           regime,
        "top_sectors":      [f["sector"] for f in top],
        "top_sectors_flow": {f["sector"]: float(f.get("change_pct") or 0) for f in top},
        "all_sector_flows": {
            f["sector"]: float(f.get("change_pct") or 0)
            for f in flows
            if isinstance(f, dict) and f.get("sector")
        },
    }


def _symbol_sectors(symbols: list[str]) -> dict[str, str]:
    """Bulk-load primary-sector per symbol. Returns {} for unmapped names."""
    if not symbols:
        return {}
    init_db()
    placeholders = ",".join("?" * len(symbols))
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT si.symbol AS symbol, i.sector AS sector
              FROM stock_industry si
              JOIN industries i ON si.industry_code = i.code
             WHERE si.is_primary = 1
               AND si.symbol IN ({placeholders})
            """,
            tuple(symbols),
        ).fetchall()
    finally:
        conn.close()
    return {r["symbol"]: r["sector"] for r in rows}


# ── Phase 5: cached per-symbol signals for richer composite scoring ────


def _bulk_bubble_signals(symbols: list[str]) -> dict[str, float]:
    """Per-symbol signal from cached bubble score → -1..+1.

    Mapping (matches the labels bubble_score_service emits):
        "Overheated", "Bubble", "Peak" → -1.0  (penalty)
        "Fair Value", "Normal"          →  0.0
        "Undervalued", "Discounted"     → +1.0  (bonus)

    Source: cache table where key = "bubble_score:v1:{SYMBOL}". One bulk
    SELECT keeps the per-pick path O(1).
    """
    if not symbols:
        return {}
    init_db()
    keys = [f"bubble_score:v1:{s}" for s in symbols]
    placeholders = ",".join("?" * len(keys))
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT key, value FROM cache WHERE key IN ({placeholders})",
            tuple(keys),
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, float] = {}
    for r in rows:
        try:
            data = json.loads(r["value"])
        except Exception:
            continue
        label = (data.get("label") or "").lower()
        sym = r["key"].rsplit(":", 1)[-1]
        if any(t in label for t in ("overheated", "bubble", "peak")):
            out[sym] = -1.0
        elif any(t in label for t in ("undervalued", "discount")):
            out[sym] = 1.0
        else:
            out[sym] = 0.0
    return out


def _bulk_analyst_revisions(symbols: list[str]) -> dict[str, float]:
    """Per-symbol analyst revision signal → -1..+1.

    Maps Finnhub net_change_30d (upgrades − downgrades over 30 days) to
    a clipped [-1, +1] range using ±10 as full saturation. So a stock
    with +5 net upgrades returns 0.5; +12 returns 1.0; -10 returns -1.0.

    Source: cache "estimate_revisions:v1:{SYMBOL}" (24h TTL, written by
    the existing analyst service).
    """
    if not symbols:
        return {}
    init_db()
    keys = [f"estimate_revisions:v1:{s}" for s in symbols]
    placeholders = ",".join("?" * len(keys))
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT key, value FROM cache WHERE key IN ({placeholders})",
            tuple(keys),
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, float] = {}
    for r in rows:
        try:
            data = json.loads(r["value"])
        except Exception:
            continue
        sym = r["key"].rsplit(":", 1)[-1]
        net = data.get("net_change_30d")
        if net is None:
            continue
        try:
            scaled = max(-1.0, min(1.0, float(net) / 10.0))
        except (TypeError, ValueError):
            continue
        out[sym] = scaled
    return out


def _bulk_cache_signal(
    symbols: list[str],
    key_prefix: str,
    extractor,
) -> dict[str, float]:
    """Generic bulk cache reader. One SQL query → per-symbol numeric signal.

    `key_prefix` is the cache-key namespace (e.g. "options_flow:v1").
    `extractor(parsed_value) -> float | None` converts the cached JSON to
    a normalized score; returning None skips that symbol.
    """
    if not symbols:
        return {}
    init_db()
    keys = [f"{key_prefix}:{s}" for s in symbols]
    placeholders = ",".join("?" * len(keys))
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT key, value FROM cache WHERE key IN ({placeholders})",
            tuple(keys),
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, float] = {}
    for r in rows:
        try:
            data = json.loads(r["value"])
        except Exception:
            continue
        try:
            v = extractor(data)
        except Exception:
            continue
        if v is None:
            continue
        sym = r["key"].rsplit(":", 1)[-1]
        try:
            out[sym] = max(-1.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            continue
    return out


def _bulk_options_signals(symbols: list[str]) -> dict[str, float]:
    """options_flow signal — P/C ratio + IV interpretation → -1..+1.

    options_flow already publishes a normalized `signal` field on the cache
    payload. We map: bullish → +1, bearish → -1, neutral → 0.
    """
    def _extract(d: dict) -> float | None:
        if not d.get("available", True):
            return None
        sig = (d.get("signal") or "").lower()
        if "bullish" in sig:
            return 1.0
        if "bearish" in sig:
            return -1.0
        return 0.0
    return _bulk_cache_signal(symbols, "options_flow:v1", _extract)


def _bulk_news_signals(symbols: list[str]) -> dict[str, float]:
    """news_feed net_sentiment already in [-1, +1]."""
    def _extract(d: dict) -> float | None:
        v = d.get("net_sentiment")
        return float(v) if v is not None else None
    return _bulk_cache_signal(symbols, "news_feed:v1", _extract)


def _bulk_pre_earnings_signals(symbols: list[str]) -> dict[str, float]:
    """pre_earnings_setup composite score → normalized to [-1, +1]."""
    def _extract(d: dict) -> float | None:
        if d.get("verdict") in ("insufficient_data", "no_earnings_imminent", None):
            return None
        s = d.get("score")
        if s is None:
            return None
        # Service emits roughly [-100, +100]
        return max(-1.0, min(1.0, float(s) / 100.0))
    return _bulk_cache_signal(symbols, "pre_earnings_setup:v1", _extract)


def _bulk_peer_valuation_signals(symbols: list[str]) -> dict[str, float]:
    """peer_valuation — compute P/E discount vs sector median.

    Returns -1..+1 where +1 = cheaper than peers (own P/E < median),
    -1 = more expensive. Symbols without P/E data are dropped.
    """
    def _extract(d: dict) -> float | None:
        self_row = next((r for r in (d.get("rows") or []) if r.get("is_self")), None)
        medians = d.get("medians") or {}
        if not self_row:
            return None
        own_pe = self_row.get("pe_ratio")
        med_pe = medians.get("pe_ratio")
        if not own_pe or not med_pe or own_pe <= 0 or med_pe <= 0:
            return None
        # Discount: 1 - own/median. own < median → positive (cheap)
        return max(-1.0, min(1.0, 1.0 - (float(own_pe) / float(med_pe))))
    return _bulk_cache_signal(symbols, "peer_valuation:v1", _extract)


def _bulk_catalyst_signals(symbols: list[str], *, horizon_days: int = 30) -> dict[str, float]:
    """catalyst_calendar — +1 if any high-weight catalyst within `horizon_days`."""
    def _extract(d: dict) -> float | None:
        events = d.get("events") or []
        for e in events:
            d_out = e.get("days_out")
            if d_out is None or d_out > horizon_days:
                continue
            w = (e.get("weight") or "").lower()
            if w in ("high", "very_high"):
                return 1.0
        return 0.0
    return _bulk_cache_signal(symbols, "catalyst_calendar:v1", _extract)


def _bulk_recommendation_signals(symbols: list[str]) -> dict[str, float]:
    """recommendation.action → buy=+1, sell=-1, hold=0."""
    def _extract(d: dict) -> float | None:
        a = (d.get("action") or "").lower()
        if "buy" in a or "strong_buy" in a:
            return 1.0
        if "sell" in a or "avoid" in a:
            return -1.0
        if "hold" in a or "wait" in a or "watch" in a:
            return 0.0
        return None
    return _bulk_cache_signal(symbols, "recommendation:v1", _extract)


def _bulk_macro_fit_signals(symbols: list[str]) -> dict[str, float]:
    """macro_fit composite — regime_score + sector_score normalized.

    Both scores already roughly in [-1, +1]; we average them.
    """
    def _extract(d: dict) -> float | None:
        if not d.get("available", True):
            return None
        rs = d.get("regime_score")
        ss = d.get("sector_score")
        scores = [float(s) for s in (rs, ss) if s is not None]
        if not scores:
            return None
        return sum(scores) / len(scores)
    return _bulk_cache_signal(symbols, "macro_fit:v1", _extract)


def _bulk_analyst_consensus_signals(symbols: list[str]) -> dict[str, float]:
    """analyst_consensus upside_pct → clipped to [-1, +1] at ±20% upside."""
    def _extract(d: dict) -> float | None:
        v = d.get("upside_pct")
        if v is None:
            return None
        return max(-1.0, min(1.0, float(v) / 20.0))
    return _bulk_cache_signal(symbols, "analyst_consensus:v1", _extract)


def _bulk_fundamentals_signals(symbols: list[str]) -> dict[str, float]:
    """fundamentals_story overall_score (0-100) → centered to [-1, +1]."""
    def _extract(d: dict) -> float | None:
        if not d.get("available", True):
            return None
        s = d.get("overall_score")
        if s is None:
            return None
        # 50 → 0; 100 → +1; 0 → -1
        return max(-1.0, min(1.0, (float(s) - 50.0) / 50.0))
    return _bulk_cache_signal(symbols, "fundamentals_story:v1", _extract)


def _bulk_premarket_signals(symbols: list[str], *, cache_ttl_min: int = 30) -> dict[str, float]:
    """Pre-market gap signal → -1..+1.

    Computes (pre_market_price − previous_close) / previous_close × 100,
    then normalizes by clipping to ±5% (a 5% pre-market move is huge
    and saturates the signal — we don't want a single 30% gapper to
    dwarf every other factor).

    Cached for 30 min — pre-market values shift through the morning
    but only need to be fresh-ish at generation time. After 9:30 ET the
    pre-market price freezes at the open and the signal stops changing.

    Uses yfinance Ticker.info per symbol — about 0.3s each, parallelized
    with 16 workers → ~10s for 500 Tier A symbols. Errors are swallowed
    silently so a flaky Yahoo response on one symbol doesn't kill the
    whole bulk load.
    """
    if not symbols:
        return {}

    # Try cache first — generation may run twice within 30 min (manual
    # trigger after the scheduled one) so we don't want N×500 yfinance
    # calls every time.
    cached: dict[str, float] = {}
    misses: list[str] = []
    for s in symbols:
        v = cache_get(f"premarket_signal:v1:{s}")
        if v is not None and isinstance(v, dict) and "score" in v:
            cached[s] = float(v["score"])
        else:
            misses.append(s)

    if not misses:
        return cached

    def _fetch(sym: str) -> tuple[str, float | None]:
        try:
            import yfinance as yf
            info = yf.Ticker(sym).info or {}
            pre = info.get("preMarketPrice")
            prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
            if pre is None or prev is None or float(prev) <= 0:
                return sym, None
            gap_pct = ((float(pre) - float(prev)) / float(prev)) * 100.0
            return sym, max(-1.0, min(1.0, gap_pct / 5.0))    # ±5% saturation
        except Exception:
            return sym, None

    fetched: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=16) as pool:
        for sym, score in pool.map(_fetch, misses):
            if score is not None:
                fetched[sym] = score
                try:
                    cache_set(f"premarket_signal:v1:{sym}", {"score": score}, ttl_minutes=cache_ttl_min)
                except Exception:
                    pass

    return {**cached, **fetched}


def _bulk_reddit_signals(symbols: list[str], *, cache_ttl_min: int = 60) -> dict[str, float]:
    """Reddit/WSB mention-spike signal → 0..+1.

    Pulls the apewisdom top-mentioned-tickers list (free, no auth) and
    maps the symbols we care about onto its `mentions` count, then
    normalizes by rank (1st place = 1.0, 100th place = 0.0).

    One HTTP call covers the whole universe. apewisdom updates every
    ~10 min so 60-min caching is plenty.
    """
    if not symbols:
        return {}

    cache_key = "reddit_signal:v1:apewisdom_universe"
    cached = cache_get(cache_key)
    if cached is None or not isinstance(cached, dict):
        try:
            import httpx
            resp = httpx.get(
                "https://apewisdom.io/api/v1.0/filter/all-stocks/page/1",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json() or {}
        except Exception as e:
            logger.info("predictions: apewisdom fetch failed: %r", e)
            data = {}
        # apewisdom returns {"count": N, "pages": M, "results": [{"ticker", "mentions", ...}, ...]}
        results = data.get("results") or []
        # Map ticker → normalized rank score (rank 1 = highest)
        ranks: dict[str, float] = {}
        for i, item in enumerate(results[:100]):
            sym = (item.get("ticker") or "").upper()
            if not sym:
                continue
            ranks[sym] = max(0.0, 1.0 - (i / 100.0))
        cached = ranks
        try:
            cache_set(cache_key, ranks, ttl_minutes=cache_ttl_min)
        except Exception:
            pass

    return {s: cached.get(s.upper(), 0.0) for s in symbols if cached.get(s.upper(), 0.0) > 0}


def _bulk_congress_buys(symbols: list[str], *, days: int = 30) -> dict[str, float]:
    """Per-symbol congress-buy signal → 0..1.

    Returns 1.0 if there were any buy-side congressional trades in the
    last `days` for a given ticker, else 0.0. (Cluster size could be a
    follow-up; the binary signal alone has historically tracked sector
    rotation reasonably well — see notes in congress_signal_service.)
    """
    if not symbols:
        return {}
    init_db()
    placeholders = ",".join("?" * len(symbols))
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).date().isoformat()
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT DISTINCT ticker
              FROM congress_trades
             WHERE ticker IN ({placeholders})
               AND lower(transaction_type) = 'buy'
               AND transaction_date >= ?
            """,
            (*symbols, cutoff),
        ).fetchall()
    finally:
        conn.close()
    return {r["ticker"]: 1.0 for r in rows}


# ── Strategy bootstrap + lookup ────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _ensure_baseline_strategy() -> int:
    """Create v1 baseline if no ACTIVE strategy exists. Return the active version.

    "Active" requires activated_at IS NOT NULL — a freshly proposed
    strategy waiting to be activated does not count.
    """
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT version FROM prediction_strategies "
            "WHERE activated_at IS NOT NULL AND deactivated_at IS NULL "
            "ORDER BY version DESC LIMIT 1"
        ).fetchone()
        if row:
            return int(row["version"])
        now = _now_iso()
        cur = conn.execute(
            """
            INSERT INTO prediction_strategies
              (name, description, config_json, created_at, activated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                _BASELINE_STRATEGY["name"],
                _BASELINE_STRATEGY["description"],
                json.dumps(_BASELINE_STRATEGY["config"]),
                now, now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def get_active_strategy() -> dict:
    """Return the currently-active strategy row + parsed config.

    Bootstraps the baseline on first call.
    """
    _ensure_baseline_strategy()
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT version, name, description, config_json, created_at, "
            "       activated_at "
            "FROM prediction_strategies "
            "WHERE activated_at IS NOT NULL AND deactivated_at IS NULL "
            "ORDER BY version DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise RuntimeError("predictions: no active strategy after bootstrap")
    try:
        config = json.loads(row["config_json"])
    except Exception:
        config = {}
    return {
        "version":      int(row["version"]),
        "name":         row["name"],
        "description":  row["description"],
        "config":       config,
        "created_at":   row["created_at"],
        "activated_at": row["activated_at"],
    }


# ── Universe + signal scoring ──────────────────────────────────────────


def _load_universe(tier: str) -> list[str]:
    """Return list of symbols for a tier."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol FROM stocks_universe WHERE tier = ? ORDER BY symbol",
            (tier,),
        ).fetchall()
    finally:
        conn.close()
    return [r["symbol"] for r in rows]


def _momentum_for(symbol: str, *, lookback_days: int, min_history_days: int) -> float | None:
    """Pure trailing %-return helper. Returns None if data is missing."""
    try:
        gw = DataGateway()
        df = gw.get_historical(symbol, period_days=min_history_days + 30)
    except Exception as e:
        logger.info("predictions: get_historical failed for %s: %r", symbol, e)
        return None
    if df is None or len(df) < min_history_days:
        return None
    try:
        close = df["Close"] if "Close" in df.columns else df["close"]
        latest = float(close.iloc[-1])
        prior = float(close.iloc[-1 - lookback_days])
    except Exception:
        return None
    if prior <= 0:
        return None
    return ((latest - prior) / prior) * 100.0


def _score_one(
    symbol: str,
    *,
    lookback_days: int,
    min_history_days: int,
    signal: str = "change_5d",
    pulse: dict | None = None,
    sector: str | None = None,
    weights: dict | None = None,
    bubble_signal: float = 0.0,
    analyst_signal: float = 0.0,
    congress_signal: float = 0.0,
    options_signal: float = 0.0,
    news_signal: float = 0.0,
    pre_earnings_signal: float = 0.0,
    peer_val_signal: float = 0.0,
    catalyst_signal: float = 0.0,
    recommendation_signal: float = 0.0,
    macro_fit_signal: float = 0.0,
    analyst_consensus_signal: float = 0.0,
    fundamentals_signal: float = 0.0,
    premarket_signal: float = 0.0,
    reddit_signal: float = 0.0,
) -> dict | None:
    """Compute one symbol's score under the active strategy.

    Dispatches on `signal`:
      - change_Nd        → pure momentum (legacy / baseline)
      - composite_v1     → momentum + Market Pulse sector + cached signals
                          (bubble, analyst revisions, congress buys)

    Returns {symbol, score, reasoning, components} or None on missing data.
    POINT-IN-TIME: only the most-recent COMPLETED daily bars are used; the
    pulse + cached signals are pre-open snapshots, never today's intraday.
    """
    change_pct = _momentum_for(
        symbol, lookback_days=lookback_days, min_history_days=min_history_days
    )
    if change_pct is None:
        return None

    if signal == "composite_v1":
        # Weight defaults — momentum + sector dominant; all cached-signal
        # weights start at 0 so legacy v1 strategies keep their behavior.
        # Claude proposals turn the new factors on by setting non-zero
        # weights based on what the playbook says works.
        w = {**{
            "momentum":             0.5,
            "sector_match":         0.3,
            "sector_flow":          0.2,
            "bubble":               0.0,
            "analyst":              0.0,
            "congress":             0.0,
            "options":              0.0,
            "news":                 0.0,
            "pre_earnings":         0.0,
            "peer_valuation":       0.0,
            "catalyst":             0.0,
            "recommendation":       0.0,
            "macro_fit":            0.0,
            "analyst_consensus":    0.0,
            "fundamentals":         0.0,
            "premarket":            0.0,
            "reddit":               0.0,
        }, **(weights or {})}
        top_sectors = set((pulse or {}).get("top_sectors") or [])
        sector_flows = (pulse or {}).get("all_sector_flows") or {}

        sector_match = 1.0 if (sector and sector in top_sectors) else 0.0
        sector_flow = float(sector_flows.get(sector or "", 0.0)) if sector else 0.0

        # All non-momentum factors normalized to ~%-point magnitude (×10)
        # so weights are comparable to the momentum weight.
        score = (
            w["momentum"]           * change_pct
            + w["sector_match"]     * sector_match            * 10.0
            + w["sector_flow"]      * sector_flow
            + w["bubble"]           * bubble_signal           * 10.0
            + w["analyst"]          * analyst_signal          * 10.0
            + w["congress"]         * congress_signal         * 10.0
            + w["options"]          * options_signal          * 10.0
            + w["news"]             * news_signal             * 10.0
            + w["pre_earnings"]     * pre_earnings_signal     * 10.0
            + w["peer_valuation"]   * peer_val_signal         * 10.0
            + w["catalyst"]         * catalyst_signal         * 10.0
            + w["recommendation"]   * recommendation_signal   * 10.0
            + w["macro_fit"]        * macro_fit_signal        * 10.0
            + w["analyst_consensus"] * analyst_consensus_signal * 10.0
            + w["fundamentals"]     * fundamentals_signal     * 10.0
            + w["premarket"]        * premarket_signal        * 10.0
            + w["reddit"]           * reddit_signal           * 10.0
        )

        bits: list[str] = [f"{change_pct:+.1f}% 5d"]
        if sector_match > 0:
            bits.append(f"sector match ({sector})")
        if abs(sector_flow) > 0.1:
            bits.append(f"flow {sector_flow:+.1f}%")
        if bubble_signal > 0:
            bits.append("undervalued")
        elif bubble_signal < 0:
            bits.append("overheated")
        if analyst_signal > 0.1:
            bits.append("analyst-up")
        if congress_signal > 0:
            bits.append("congress-buy")
        if options_signal > 0.5:
            bits.append("options-bullish")
        elif options_signal < -0.5:
            bits.append("options-bearish")
        if news_signal > 0.3:
            bits.append("news-bullish")
        elif news_signal < -0.3:
            bits.append("news-bearish")
        if pre_earnings_signal > 0.3:
            bits.append("pre-earnings-setup")
        if peer_val_signal > 0.2:
            bits.append("cheap-vs-peers")
        if catalyst_signal > 0:
            bits.append("catalyst-30d")
        if recommendation_signal > 0.5:
            bits.append("rec-buy")
        if macro_fit_signal > 0.3:
            bits.append("macro-fit+")
        elif macro_fit_signal < -0.3:
            bits.append("macro-fit-")
        if analyst_consensus_signal > 0.3:
            bits.append("upside")
        if fundamentals_signal > 0.3:
            bits.append("fundamentals+")
        elif fundamentals_signal < -0.3:
            bits.append("fundamentals-")
        if premarket_signal > 0.2:
            bits.append(f"premkt +{premarket_signal*5:.1f}%")
        elif premarket_signal < -0.2:
            bits.append(f"premkt {premarket_signal*5:.1f}%")
        if reddit_signal > 0.1:
            bits.append("wsb-trending")

        return {
            "symbol":    symbol,
            "score":     score,
            "reasoning": " · ".join(bits),
            "components": {
                "momentum":                  change_pct,
                "sector":                    sector,
                "sector_match":              bool(sector_match),
                "sector_flow":               sector_flow,
                "bubble_signal":             bubble_signal,
                "analyst_signal":            analyst_signal,
                "congress_signal":           congress_signal,
                "options_signal":            options_signal,
                "news_signal":               news_signal,
                "pre_earnings_signal":       pre_earnings_signal,
                "peer_val_signal":           peer_val_signal,
                "catalyst_signal":           catalyst_signal,
                "recommendation_signal":     recommendation_signal,
                "macro_fit_signal":          macro_fit_signal,
                "analyst_consensus_signal":  analyst_consensus_signal,
                "fundamentals_signal":       fundamentals_signal,
                "premarket_signal":          premarket_signal,
                "reddit_signal":             reddit_signal,
            },
        }

    # Default branch: pure change_Nd momentum (1d / 5d / 20d).
    return {
        "symbol":    symbol,
        "score":     change_pct,
        "reasoning": (
            f"+{change_pct:.1f}% over {lookback_days}d momentum"
            if change_pct >= 0
            else f"{change_pct:.1f}% over {lookback_days}d (mean-reversion candidate)"
        ),
    }


def _rank_universe(symbols: list[str], config: dict, *,
                   pulse: dict | None = None,
                   sectors_by_sym: dict[str, str] | None = None,
                   signals_by_sym: dict[str, dict] | None = None) -> list[dict]:
    """Score every symbol in parallel and return top N by score desc.

    `signals_by_sym` is the union of every cached per-symbol signal —
    {sym: {bubble: float, analyst: float, options: float, ...}}. Default
    0 for any missing key so _score_one's per-keyword arguments stay
    backwards-compatible.
    """
    lookback = int(config.get("lookback_days", 5))
    min_hist = int(config.get("min_history_days", 6))
    top_n = int(config.get("top_n", 10))
    signal = config.get("ranking_signal", "change_5d")
    weights = config.get("weights") if isinstance(config.get("weights"), dict) else None
    sectors_by_sym = sectors_by_sym or {}
    signals_by_sym = signals_by_sym or {}

    def _sigs_for(sym: str) -> dict:
        return signals_by_sym.get(sym) or {}

    scored: list[dict] = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        for result in pool.map(
            lambda s: _score_one(
                s,
                lookback_days=lookback,
                min_history_days=min_hist,
                signal=signal,
                pulse=pulse,
                sector=sectors_by_sym.get(s),
                weights=weights,
                bubble_signal             = _sigs_for(s).get("bubble", 0.0),
                analyst_signal            = _sigs_for(s).get("analyst", 0.0),
                congress_signal           = _sigs_for(s).get("congress", 0.0),
                options_signal            = _sigs_for(s).get("options", 0.0),
                news_signal               = _sigs_for(s).get("news", 0.0),
                pre_earnings_signal       = _sigs_for(s).get("pre_earnings", 0.0),
                peer_val_signal           = _sigs_for(s).get("peer_valuation", 0.0),
                catalyst_signal           = _sigs_for(s).get("catalyst", 0.0),
                recommendation_signal     = _sigs_for(s).get("recommendation", 0.0),
                macro_fit_signal          = _sigs_for(s).get("macro_fit", 0.0),
                analyst_consensus_signal  = _sigs_for(s).get("analyst_consensus", 0.0),
                fundamentals_signal       = _sigs_for(s).get("fundamentals", 0.0),
                premarket_signal          = _sigs_for(s).get("premarket", 0.0),
                reddit_signal             = _sigs_for(s).get("reddit", 0.0),
            ),
            symbols,
        ):
            if result is not None:
                scored.append(result)
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_n]


def _bulk_all_signals(symbols: list[str]) -> dict[str, dict]:
    """Union of every per-symbol cached signal in one structure.

    {sym: {bubble, analyst, congress, options, news, pre_earnings,
           peer_valuation, catalyst, recommendation, macro_fit,
           analyst_consensus, fundamentals}}

    Missing keys absent (the caller defaults them to 0). Each bulk loader
    is one SQL query so this stays fast at ~500-symbol scale.
    """
    out: dict[str, dict] = {}
    sources = [
        ("bubble",            _bulk_bubble_signals(symbols)),
        ("analyst",           _bulk_analyst_revisions(symbols)),
        ("congress",          _bulk_congress_buys(symbols)),
        ("options",           _bulk_options_signals(symbols)),
        ("news",              _bulk_news_signals(symbols)),
        ("pre_earnings",      _bulk_pre_earnings_signals(symbols)),
        ("peer_valuation",    _bulk_peer_valuation_signals(symbols)),
        ("catalyst",          _bulk_catalyst_signals(symbols)),
        ("recommendation",    _bulk_recommendation_signals(symbols)),
        ("macro_fit",         _bulk_macro_fit_signals(symbols)),
        ("analyst_consensus", _bulk_analyst_consensus_signals(symbols)),
        ("fundamentals",      _bulk_fundamentals_signals(symbols)),
        # Phase 8 — attention/retail signals
        ("premarket",         _bulk_premarket_signals(symbols)),
        ("reddit",            _bulk_reddit_signals(symbols)),
    ]
    for key, data in sources:
        for sym, val in data.items():
            out.setdefault(sym, {})[key] = val
    return out


# ── Public API ─────────────────────────────────────────────────────────


def generate_predictions_for_date(date: str, *, force: bool = False) -> dict:
    """Generate (or retrieve) top-10 predictions for `date` (YYYY-MM-DD).

    Idempotent: returns the already-stored rows if predictions exist for
    this date, unless `force=True`. Predictions are immutable once stored
    — re-running with the same date and strategy returns whatever is in
    the table, preserving the historical accuracy record.

    The `date` parameter is the day the predictions WILL BE MEASURED, not
    the day they were created. Caller is responsible for passing the
    correct date (typically "today" if called pre-market).
    """
    init_db()

    if not force:
        existing = get_predictions_for_date(date)
        if existing["picks"]:
            return existing

    strategy = get_active_strategy()
    config = strategy["config"]
    tier = config.get("universe_tier", "A")
    symbols = _load_universe(tier)
    if not symbols:
        # Defensive: no Tier A loaded yet. Don't crash; return empty.
        logger.warning("predictions: no symbols in Tier %s — universe needs seeding", tier)
        return {
            "date": date,
            "strategy_version": strategy["version"],
            "strategy_name":    strategy["name"],
            "picks":            [],
            "universe_size":    0,
        }

    # Phase 4: pull Market Pulse context once per generation. Composite
    # strategies use it for sector match + flow signal; pure-momentum
    # strategies ignore the pulse but we still attach it to the payload
    # so the UI can show the regime alongside the picks.
    pulse = _pulse_context()
    sectors_by_sym = _symbol_sectors(symbols)

    # Phase 5+7: bulk-load every cached per-symbol signal in one shot.
    # 12 separate one-shot SQL queries = ~5-10ms total at 500-symbol scale.
    signals_by_sym = _bulk_all_signals(symbols)

    top = _rank_universe(
        symbols, config,
        pulse=pulse,
        sectors_by_sym=sectors_by_sym,
        signals_by_sym=signals_by_sym,
    )
    now = _now_iso()

    conn = get_connection()
    try:
        # Replace any prior rows for this date — safe because predictions
        # are owned by (date, rank) and the new run is for the same date.
        conn.execute("DELETE FROM daily_predictions WHERE prediction_date = ?", (date,))
        # Phase 6: serialize pulse once per generation (same for all 10
        # picks) and components per-pick. Weekly playbook review reads
        # these to correlate hits with macro state + signal contribution.
        pulse_json = json.dumps(pulse, default=str) if pulse else None
        for rank, row in enumerate(top, start=1):
            comp_json = json.dumps(row.get("components") or {}, default=str)
            conn.execute(
                """
                INSERT INTO daily_predictions
                  (prediction_date, rank, symbol, score, reasoning,
                   strategy_version, created_at,
                   pulse_snapshot_json, components_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date, rank, row["symbol"], row["score"],
                    row["reasoning"], strategy["version"], now,
                    pulse_json, comp_json,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "date":              date,
        "strategy_version":  strategy["version"],
        "strategy_name":     strategy["name"],
        "picks":             [
            {**row, "rank": i, "strategy_version": strategy["version"]}
            for i, row in enumerate(top, start=1)
        ],
        "universe_size":     len(symbols),
        "pulse_context":     pulse,
    }


def get_predictions_for_date(date: str) -> dict:
    """Read-only fetch of predictions for a date. Empty list if none."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT rank, symbol, score, reasoning, strategy_version, created_at
              FROM daily_predictions
             WHERE prediction_date = ?
             ORDER BY rank
            """,
            (date,),
        ).fetchall()
        # Lookup strategy name for the rows we have. All picks for a date
        # use the same strategy (we replace them as a set).
        strategy_version = rows[0]["strategy_version"] if rows else None
        strategy_name: str | None = None
        if strategy_version is not None:
            srow = conn.execute(
                "SELECT name FROM prediction_strategies WHERE version = ?",
                (strategy_version,),
            ).fetchone()
            strategy_name = srow["name"] if srow else None
    finally:
        conn.close()
    return {
        "date":             date,
        "strategy_version": strategy_version,
        "strategy_name":    strategy_name,
        "picks":            [dict(r) for r in rows],
    }


def get_predictions_today() -> dict:
    """Convenience: predictions for today's UTC date.

    If none exist yet (pre-market hasn't run the scheduler), generates
    them inline. Caller pays the wall-clock cost of scoring the universe
    on first call of the day.
    """
    today = datetime.now(tz=timezone.utc).date().isoformat()
    return generate_predictions_for_date(today)


# ── Actuals + accuracy (Phase 2) ─────────────────────────────────────────


def _eod_change_pct(symbol: str, date: str) -> tuple[float | None, float | None, float | None]:
    """Open / close / change_pct for `symbol` on `date`.

    Returns (open, close, change_pct) or (None, None, None) on any miss.
    Used by `record_actuals_for_date` AFTER market close — calling it
    earlier in the day yields incomplete data and the row gets stamped
    with None values.
    """
    try:
        gw = DataGateway()
        # 90 days of history gives us plenty of buffer to find `date`.
        df = gw.get_historical(symbol, period_days=90)
    except Exception as e:
        logger.info("predictions: get_historical failed for %s: %r", symbol, e)
        return None, None, None
    if df is None or len(df) == 0:
        return None, None, None

    # The DataFrame index is a DatetimeIndex; match the date.
    try:
        target_rows = df[df.index.astype(str).str.startswith(date)]
    except Exception:
        return None, None, None
    if len(target_rows) == 0:
        return None, None, None
    row = target_rows.iloc[-1]
    try:
        open_ = float(row["Open"] if "Open" in row.index else row["open"])
        close = float(row["Close"] if "Close" in row.index else row["close"])
    except Exception:
        return None, None, None
    if open_ <= 0:
        return None, None, None
    return open_, close, ((close - open_) / open_) * 100.0


def record_actuals_for_date(date: str) -> dict:
    """Record open/close/change_pct for every symbol predicted on `date`,
    plus the actual universe ranks (for hit/miss computation).

    Idempotent — re-running for the same date overwrites the rows so a
    later EOD fetch (when more bars are settled) supersedes an earlier one.

    POINT-IN-TIME GUARANTEE: only call AFTER market close for `date`. The
    helper does not check this — caller (scheduler / manual route) must.
    """
    init_db()

    # 1. Pull the predictions for this date.
    preds = get_predictions_for_date(date)
    if not preds["picks"]:
        return {"date": date, "recorded": 0, "reason": "no_predictions"}

    # 2. Score the FULL Tier A universe for the same date so we know
    #    where each predicted pick ranked among actual winners.
    universe = _load_universe("A")
    universe_changes: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = pool.map(
            lambda s: (s, _eod_change_pct(s, date)),
            universe,
        )
        for sym, (_o, _c, change) in results:
            if change is not None:
                universe_changes[sym] = change

    # Rank universe by change desc; symbol → rank (1-based).
    sorted_universe = sorted(universe_changes.items(), key=lambda kv: kv[1], reverse=True)
    rank_by_sym = {sym: i + 1 for i, (sym, _) in enumerate(sorted_universe)}
    universe_size = len(rank_by_sym)

    # 3. Persist actuals row per predicted pick.
    now = _now_iso()
    conn = get_connection()
    recorded = 0
    try:
        for pick in preds["picks"]:
            sym = pick["symbol"]
            # If we scored the symbol while ranking the universe, reuse
            # the change directly. Otherwise it's missing data — None values.
            if sym in universe_changes:
                # Re-derive open/close from the freshly-fetched bar so the
                # row has the exact prices the universe rank used.
                open_, close, change = _eod_change_pct(sym, date)
            else:
                open_, close, change = None, None, None
            rank = rank_by_sym.get(sym)
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_prediction_actuals
                  (prediction_date, symbol, open_price, close_price,
                   change_pct, universe_rank, universe_size, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (date, sym, open_, close, change, rank, universe_size, now),
            )
            recorded += 1
        conn.commit()
    finally:
        conn.close()

    return {
        "date":          date,
        "recorded":      recorded,
        "universe_size": universe_size,
    }


def get_accuracy_window(*, window_days: int = 30, hit_threshold: int = 25) -> dict:
    """Rolling accuracy over the last `window_days` of COMPLETED predictions.

    "Completed" = prediction has a matching actuals row. In-flight days
    (today, weekend predictions where market hasn't closed) are excluded.

    Hit definition: a predicted symbol "hit" if its actual rank in the
    scored universe for that day was <= `hit_threshold`.

    Returns:
      {
        "window_days":       30,
        "hit_threshold":     25,
        "days_evaluated":    N,
        "predictions_total": N * 10,
        "hits":              count of picks with universe_rank <= 25,
        "hit_rate":          hits / predictions_total,
        "by_strategy":       {version: {predictions, hits, hit_rate}}
      }
    """
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT dp.prediction_date     AS date,
                   dp.symbol              AS symbol,
                   dp.strategy_version    AS strategy_version,
                   dpa.universe_rank      AS universe_rank,
                   dpa.universe_size      AS universe_size,
                   dpa.change_pct         AS change_pct
              FROM daily_predictions dp
              JOIN daily_prediction_actuals dpa
                ON dp.prediction_date = dpa.prediction_date
               AND dp.symbol = dpa.symbol
             WHERE dpa.universe_rank IS NOT NULL
             ORDER BY dp.prediction_date DESC, dp.rank
             LIMIT ?
            """,
            (window_days * 10,),
        ).fetchall()
    finally:
        conn.close()

    total = len(rows)
    hits = sum(1 for r in rows if r["universe_rank"] and r["universe_rank"] <= hit_threshold)
    days_evaluated = len({r["date"] for r in rows})

    # Per-strategy breakdown
    by_strategy: dict[int, dict[str, Any]] = {}
    for r in rows:
        v = r["strategy_version"]
        if v not in by_strategy:
            by_strategy[v] = {"predictions": 0, "hits": 0}
        by_strategy[v]["predictions"] += 1
        if r["universe_rank"] and r["universe_rank"] <= hit_threshold:
            by_strategy[v]["hits"] += 1
    for v, b in by_strategy.items():
        b["hit_rate"] = b["hits"] / b["predictions"] if b["predictions"] else 0.0

    return {
        "window_days":       window_days,
        "hit_threshold":     hit_threshold,
        "days_evaluated":    days_evaluated,
        "predictions_total": total,
        "hits":              hits,
        "hit_rate":          (hits / total) if total else 0.0,
        "by_strategy":       by_strategy,
    }


def get_predictions_with_actuals(date: str) -> dict:
    """Return predictions for a date enriched with actuals (when present).

    Used by the UI to show "yesterday's predictions and how they did".
    Picks without an actuals row get None values — the UI can show "TBD".
    """
    preds = get_predictions_for_date(date)
    if not preds["picks"]:
        return preds

    init_db()
    conn = get_connection()
    try:
        actuals = {
            r["symbol"]: dict(r)
            for r in conn.execute(
                """
                SELECT symbol, open_price, close_price, change_pct,
                       universe_rank, universe_size, recorded_at
                  FROM daily_prediction_actuals
                 WHERE prediction_date = ?
                """,
                (date,),
            ).fetchall()
        }
    finally:
        conn.close()

    enriched = []
    for pick in preds["picks"]:
        a = actuals.get(pick["symbol"], {})
        enriched.append({
            **pick,
            "open_price":     a.get("open_price"),
            "close_price":    a.get("close_price"),
            "actual_change_pct": a.get("change_pct"),
            "universe_rank":  a.get("universe_rank"),
            "universe_size":  a.get("universe_size"),
            "actuals_recorded_at": a.get("recorded_at"),
        })
    return {
        **preds,
        "picks": enriched,
        "actuals_present": bool(actuals),
    }


# ── Strategy adaptation (Phase 3b) ───────────────────────────────────────


# Signals Claude is allowed to combine in a new strategy. Keeping the
# vocabulary fixed prevents Claude from inventing a signal we can't compute
# — silently no-op'ing a "VIX divergence over 90min" signal is the kind
# of bug that's hard to diagnose later.
#
# v1 vocabulary is intentionally momentum-only at varying windows — the
# existing _score_one supports any change_Nd via `lookback_days`. RSI and
# volume signals are deferred until we wire matching scoring code.
_ALLOWED_RANKING_SIGNALS = {
    "change_1d":  "trailing 1-day % return (overnight gappers)",
    "change_5d":  "trailing 5-day % return (default baseline)",
    "change_20d": "trailing 20-day % return (longer momentum)",
    "composite_v1": (
        "blend trailing %-return with Market Pulse sector flow: "
        "score = momentum*w_momentum + sector_in_pulse_top*w_sector "
        "+ sector_flow_pct*w_sector_flow. Weights configurable; pulse "
        "top-N sectors are pulled fresh at generation time."
    ),
}


def _completed_predictions_window(days: int = 14) -> list[dict]:
    """Return all predictions with actuals from the last `days` calendar days.

    Used as the data Claude reviews when proposing a new strategy.
    """
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT dp.prediction_date     AS date,
                   dp.rank                AS rank,
                   dp.symbol              AS symbol,
                   dp.score               AS predicted_score,
                   dp.reasoning           AS reasoning,
                   dp.strategy_version    AS strategy_version,
                   dpa.change_pct         AS actual_change_pct,
                   dpa.universe_rank      AS universe_rank,
                   dpa.universe_size      AS universe_size
              FROM daily_predictions dp
              JOIN daily_prediction_actuals dpa
                ON dp.prediction_date = dpa.prediction_date
               AND dp.symbol = dpa.symbol
             WHERE dpa.universe_rank IS NOT NULL
             ORDER BY dp.prediction_date DESC, dp.rank
             LIMIT ?
            """,
            (days * 10,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def _build_strategy_review_prompt(history: list[dict], current: dict) -> str:
    """Build the Claude prompt for strategy review.

    Inputs the recent prediction record + current strategy; asks Claude to
    propose either a tweaked or a fundamentally different strategy from the
    allowed signal vocabulary.
    """
    if not history:
        return ""

    # Compress history into a per-date summary so the prompt stays compact.
    by_date: dict[str, list[dict]] = {}
    for r in history:
        by_date.setdefault(r["date"], []).append(r)
    summary_lines: list[str] = []
    for date in sorted(by_date.keys(), reverse=True):
        rows = by_date[date]
        rows.sort(key=lambda r: r["rank"])
        avg_actual = sum(r["actual_change_pct"] or 0 for r in rows) / max(len(rows), 1)
        hits = sum(1 for r in rows if (r["universe_rank"] or 999) <= 25)
        line = f"{date}: avg_actual_return={avg_actual:.2f}%, hits_in_top25={hits}/{len(rows)}"
        summary_lines.append(line)
        for r in rows[:5]:    # top 5 picks per day to keep prompt small
            summary_lines.append(
                f"  #{r['rank']:>2} {r['symbol']:<8} "
                f"actual={r['actual_change_pct']:+.2f}% "
                f"rank={r['universe_rank']}/{r['universe_size']}  "
                f"({r['reasoning'] or '-'})"
            )

    vocab_lines = "\n".join(f"  - {k}: {v}" for k, v in _ALLOWED_RANKING_SIGNALS.items())

    # Include the playbook so the proposal sits on top of accumulated
    # wisdom rather than starting from scratch each week.
    playbook = _read_skills()

    # Show Claude the current Market Pulse so it can decide whether
    # composite_v1's pulse-aware signals are worth leaning into.
    pulse = _pulse_context()
    if pulse:
        pulse_blurb = (
            f"  Current market regime: {pulse.get('regime')}\n"
            f"  Top sectors by flow: {', '.join(pulse.get('top_sectors') or []) or '—'}\n"
        )
    else:
        pulse_blurb = "  Market Pulse currently unavailable.\n"

    return f"""You are tuning a daily top-10 gainers prediction strategy for Tier A US stocks.

Current strategy (v{current['version']} — "{current['name']}"):
  {current['description']}
  Config: {json.dumps(current['config'])}

Current playbook (your accumulated observations across prior weeks):
```
{playbook}
```

Market Pulse context the predictor will see at run time:
{pulse_blurb}
Recent prediction performance (most recent first; "hit" = predicted symbol's
same-day rank in Tier A was top 25 of ~500 names):
{chr(10).join(summary_lines)}

Allowed ranking signals (use exactly one of these as `ranking_signal`):
{vocab_lines}

Other config keys you can set:
  - lookback_days:    integer 1-60
  - top_n:            integer (keep at 10)
  - universe_tier:    "A" (don't change for now)
  - min_history_days: integer (typically lookback_days + 1)
  - weights (ONLY when ranking_signal=composite_v1, all 0.0-1.0):
        {{
          "momentum", "sector_match", "sector_flow",
          "bubble", "analyst", "congress",
          "options", "news", "pre_earnings", "peer_valuation",
          "catalyst", "recommendation", "macro_fit",
          "analyst_consensus", "fundamentals"
        }}

  Available factors for composite_v1 (each is per-symbol, normalized to ~[-1,+1]):
    - momentum            trailing %-return over lookback_days
    - sector_match        1 if symbol's sector is in pulse top-3, else 0
    - sector_flow         %-flow of symbol's sector this period
    - bubble              -1 overheated, 0 fair, +1 undervalued
    - analyst             net analyst upgrades over 30d (Finnhub)
    - congress            1 if any congressional buy in the last 30d
    - options             +1 bullish flow (low P/C, +IV), -1 bearish
    - news                net news sentiment over last few days [-1, +1]
    - pre_earnings        pre-earnings setup score (composite of pre-announce signals)
    - peer_valuation      +1 cheap vs sector P/E median, -1 expensive
    - catalyst            +1 if a high-weight catalyst within 30d
    - recommendation      buy=+1, sell=-1, hold=0 (third-party verdict)
    - macro_fit           does this stock fit the current macro regime + sector signal
    - analyst_consensus   target-price upside (clipped at ±20%)
    - fundamentals        overall_score (0-100) centered to [-1, +1]
    - premarket           pre-market % gap vs prior close (clipped at ±5%)
                          — directly predictive of same-day open direction
    - reddit              WSB/apewisdom mention rank (1.0 = top spot)
                          — captures viral retail attention

Propose ONE new strategy. Goals:
  1. Beat the current strategy's recent hit rate
  2. Stay in the allowed signal vocabulary
  3. Give a short, specific name (e.g. "composite_pre_earnings_v1")
  4. If picking composite_v1, set weights based on the recent record AND
     the playbook above:
     - look for which factors hit picks shared
     - look for which factors miss picks shared
     - if recent winners had "analyst-up" + "options-bullish" → weight those
     - if losers had "overheated" → add bubble penalty
     - if catalyst-30d picks all dropped → reduce catalyst weight
  5. Keep weight count manageable — non-zero weights on 4-7 factors is
     usually better than spreading thinly across all 15

Return ONLY this JSON, no prose:
{{
  "name":        "<short kebab-case name>",
  "description": "<1-2 sentence rationale: what you observed and why this should be better>",
  "config": {{
    "ranking_signal":   "<one of the allowed signals above>",
    "lookback_days":    <integer or null>,
    "top_n":            10,
    "universe_tier":    "A",
    "min_history_days": <integer>,
    "weights":          <object or null — only for composite_v1>
  }}
}}"""


def _validate_proposed_strategy(proposal: object) -> dict | None:
    """Defensive shape check on Claude's response. Returns the cleaned
    dict or None if any required field is missing/invalid.

    Prevents a bad proposal (e.g. Claude inventing a new signal name) from
    being activated and breaking _score_one. The next morning generation
    would then fail silently which is hard to debug — better to reject up front.
    """
    if not isinstance(proposal, dict):
        return None
    name = (proposal.get("name") or "").strip()
    desc = (proposal.get("description") or "").strip()
    cfg = proposal.get("config")
    if not name or not desc or not isinstance(cfg, dict):
        return None

    signal = (cfg.get("ranking_signal") or "").strip()
    if signal not in _ALLOWED_RANKING_SIGNALS:
        logger.info("predictions: rejecting proposed strategy — bad signal %r", signal)
        return None
    if cfg.get("universe_tier") not in (None, "A"):
        # Out of scope for v1 — only support Tier A
        return None

    # For change_Nd signals, pin lookback_days to N. For composite_v1,
    # let the proposed lookback through (composite uses momentum at any
    # window — 5d is the typical choice).
    _SIGNAL_LOOKBACK = {"change_1d": 1, "change_5d": 5, "change_20d": 20}
    if signal in _SIGNAL_LOOKBACK:
        lookback = _SIGNAL_LOOKBACK[signal]
    else:
        try:
            lookback = int(cfg.get("lookback_days") or 5)
        except (TypeError, ValueError):
            lookback = 5
    lookback = max(1, min(60, lookback))
    min_hist = lookback + 1

    try:
        top_n = int(cfg.get("top_n") or 10)
    except (TypeError, ValueError):
        top_n = 10

    out_config: dict = {
        "ranking_signal":   signal,
        "lookback_days":    lookback,
        "top_n":            max(1, min(50, top_n)),
        "universe_tier":    "A",
        "min_history_days": min_hist,
    }

    # composite_v1 takes a weights dict — sanitize it.
    if signal == "composite_v1":
        raw_w = cfg.get("weights") or {}
        if not isinstance(raw_w, dict):
            raw_w = {}
        def _w(key: str, default: float) -> float:
            try:
                return max(0.0, min(1.0, float(raw_w.get(key, default))))
            except (TypeError, ValueError):
                return default
        out_config["weights"] = {
            "momentum":           _w("momentum",           0.5),
            "sector_match":       _w("sector_match",       0.3),
            "sector_flow":        _w("sector_flow",        0.2),
            # Phase 5 — cached per-symbol signals
            "bubble":             _w("bubble",             0.0),
            "analyst":            _w("analyst",            0.0),
            "congress":           _w("congress",           0.0),
            # Phase 7 — expanded vocabulary (all default 0; Claude opts in)
            "options":            _w("options",            0.0),
            "news":               _w("news",               0.0),
            "pre_earnings":       _w("pre_earnings",       0.0),
            "peer_valuation":     _w("peer_valuation",     0.0),
            "catalyst":           _w("catalyst",           0.0),
            "recommendation":     _w("recommendation",     0.0),
            "macro_fit":          _w("macro_fit",          0.0),
            "analyst_consensus":  _w("analyst_consensus",  0.0),
            "fundamentals":       _w("fundamentals",       0.0),
            # Phase 8 — attention / retail signals (daily-horizon edge)
            "premarket":          _w("premarket",          0.0),
            "reddit":             _w("reddit",             0.0),
        }

    return {
        "name":        name[:64],
        "description": desc[:500],
        "config":      out_config,
    }


def review_and_propose_strategy(*, window_days: int = 14, force: bool = False) -> dict:
    """Ask Claude to review recent predictions and propose a new strategy.

    Returns:
      {
        "proposed":     bool,           # did Claude return something valid?
        "proposal":     {...}|None,     # the validated proposal (not yet active)
        "current":      {...},          # active strategy at review time
        "history_rows": int,            # how much data Claude saw
      }

    The proposal is NOT activated — caller must explicitly POST
    /predictions/strategy/activate?version=N. Lets the user vet before a
    new strategy goes live.
    """
    current = get_active_strategy()
    history = _completed_predictions_window(days=window_days)

    if not history and not force:
        return {
            "proposed":     False,
            "reason":       "no_completed_predictions_in_window",
            "current":      current,
            "history_rows": 0,
        }

    prompt = _build_strategy_review_prompt(history, current)
    if not prompt:
        return {
            "proposed":     False,
            "reason":       "empty_prompt",
            "current":      current,
            "history_rows": len(history),
        }

    try:
        raw = ask_claude_json(prompt, model="haiku", timeout=120, retries=1)
    except Exception as e:
        logger.info("predictions: Claude review call failed: %r", e)
        raw = None

    cleaned = _validate_proposed_strategy(raw)
    if cleaned is None:
        return {
            "proposed":     False,
            "reason":       "claude_proposal_invalid_or_missing",
            "current":      current,
            "history_rows": len(history),
        }

    # Persist as a strategy row — DEACTIVATED until explicit activation. The
    # row gets a version number so the user can reference it via activate().
    init_db()
    now = _now_iso()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO prediction_strategies
              (name, description, config_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (cleaned["name"], cleaned["description"], json.dumps(cleaned["config"]), now),
        )
        new_version = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()

    return {
        "proposed":      True,
        "proposal":      {**cleaned, "version": new_version},
        "current":       current,
        "history_rows":  len(history),
    }


def activate_strategy(version: int) -> dict:
    """Activate a strategy by version. Deactivates whatever is currently
    active. Idempotent — activating the already-active version is a no-op.
    """
    init_db()
    now = _now_iso()
    conn = get_connection()
    try:
        # 1. Confirm the target exists.
        row = conn.execute(
            "SELECT version, activated_at, deactivated_at "
            "FROM prediction_strategies WHERE version = ?",
            (version,),
        ).fetchone()
        if not row:
            return {"activated": False, "reason": "version_not_found"}
        # Active = activated_at IS NOT NULL AND deactivated_at IS NULL.
        # A freshly proposed row has activated_at NULL and is NOT considered
        # active — activating it is the meaningful state change here.
        if row["activated_at"] is not None and row["deactivated_at"] is None:
            return {"activated": True, "no_op": True, "version": version}

        # 2. Deactivate everything currently active.
        conn.execute(
            "UPDATE prediction_strategies SET deactivated_at = ? "
            "WHERE activated_at IS NOT NULL AND deactivated_at IS NULL",
            (now,),
        )
        # 3. Activate the target.
        conn.execute(
            "UPDATE prediction_strategies "
            "SET activated_at = ?, deactivated_at = NULL WHERE version = ?",
            (now, version),
        )
        conn.commit()
    finally:
        conn.close()
    return {"activated": True, "version": version, "activated_at": now}


def list_strategies() -> list[dict]:
    """All strategies (active + retired) in version order, oldest first."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT version, name, description, config_json, created_at, "
            "       activated_at, deactivated_at "
            "FROM prediction_strategies ORDER BY version"
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        try:
            cfg = json.loads(r["config_json"])
        except Exception:
            cfg = {}
        out.append({
            "version":         int(r["version"]),
            "name":            r["name"],
            "description":     r["description"],
            "config":          cfg,
            "created_at":      r["created_at"],
            "activated_at":    r["activated_at"],
            "deactivated_at":  r["deactivated_at"],
            "is_active":       r["deactivated_at"] is None and r["activated_at"] is not None,
        })
    return out


# ── Phase 6: Prediction Skills playbook ─────────────────────────────────


import os
from pathlib import Path


_SKILLS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "predictions" / "skills.md"
_SKILLS_VERSION_TAG = "<!-- prediction-skills-v1 -->"

_SKILLS_TEMPLATE = f"""{_SKILLS_VERSION_TAG}
# Prediction Playbook

_This file is maintained by Claude. The weekly review reads completed
predictions + actuals and rewrites this playbook with new observations.
The playbook is fed back into strategy proposals so each iteration
builds on the prior week's evidence._

## Active patterns (currently believed)

_Patterns confirmed by recent data. Each entry should cite the evidence
window and approximate hit-rate impact._

- (none yet — needs ≥7 days of completed predictions to populate)

## Hypotheses under test

_Patterns we suspect but haven't confirmed. These can be carried over
multiple reviews while evidence accumulates._

- (none yet)

## Invalidated patterns

_Patterns we used to believe that the data has refuted. Keep these
listed so Claude doesn't re-propose strategies based on them._

- (none yet)

## Per-regime notes

### Bull regime
- (no data yet)

### Bear regime
- (no data yet)

### Neutral / unclear
- (no data yet)

## Per-sector notes

_Which sectors over- or under-perform under the current strategy mix._

- (no data yet)

## Open questions

_Things Claude wants to investigate but doesn't have enough data on yet._

- (none yet)

---
_Last updated: never_
"""


def _ensure_skills_file() -> Path:
    """Create the skills file with the default template if missing.

    The parent directory is created on first call. Returns the path.
    """
    _SKILLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _SKILLS_PATH.exists():
        _SKILLS_PATH.write_text(_SKILLS_TEMPLATE, encoding="utf-8")
    return _SKILLS_PATH


def _read_skills() -> str:
    """Read the current playbook. Auto-creates on first read."""
    p = _ensure_skills_file()
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("predictions: failed to read skills file: %r", e)
        return _SKILLS_TEMPLATE


def _write_skills(content: str) -> None:
    """Atomically replace the playbook with `content`.

    Writes to a temp file in the same directory then renames — that
    way an interrupted write can never leave a half-written playbook
    on disk.
    """
    p = _ensure_skills_file()
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, p)


def get_skills() -> dict:
    """Return the current playbook + metadata for the UI."""
    p = _ensure_skills_file()
    content = _read_skills()
    try:
        mtime = p.stat().st_mtime
        from datetime import datetime
        last_updated = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except Exception:
        last_updated = None
    return {
        "content":      content,
        "last_updated": last_updated,
        "path":         str(p),
    }


def _build_skills_update_prompt(current_skills: str, history: list[dict],
                                 by_strategy: dict) -> str:
    """Compose the prompt for Claude's weekly playbook rewrite.

    Pulls in the existing playbook, the recent prediction record, and
    per-strategy hit rates. Asks Claude to rewrite the playbook in place,
    promoting confirmed hypotheses, retiring invalidated ones, and adding
    new observations from the data.
    """
    # Compress recent history into a per-day summary with regime + signal
    # contributions so Claude sees the dimensions to slice on.
    by_date: dict[str, list[dict]] = {}
    for r in history:
        by_date.setdefault(r["date"], []).append(r)

    history_lines: list[str] = []
    for date in sorted(by_date.keys(), reverse=True):
        rows = by_date[date]
        rows.sort(key=lambda r: r["rank"])
        # Pull pulse + signal contributions from the first pick (same for all).
        pulse = rows[0].get("pulse_snapshot") or {}
        regime = pulse.get("regime") or "?"
        top_sectors = (pulse.get("top_sectors") or [])[:3]
        avg_return = sum((r.get("actual_change_pct") or 0) for r in rows) / max(len(rows), 1)
        hits_25 = sum(1 for r in rows if (r.get("universe_rank") or 999) <= 25)
        hits_10 = sum(1 for r in rows if (r.get("universe_rank") or 999) <= 10)
        history_lines.append(
            f"{date}  regime={regime}  top_sectors={','.join(top_sectors) or '—'}  "
            f"avg_actual={avg_return:+.2f}%  hits10={hits_10}/{len(rows)}  hits25={hits_25}/{len(rows)}"
        )
        for r in rows[:5]:
            comp = r.get("components") or {}
            comp_bits = []
            if comp.get("sector_match"):
                comp_bits.append("sector_match")
            if (comp.get("bubble_signal") or 0) > 0:
                comp_bits.append("undervalued")
            elif (comp.get("bubble_signal") or 0) < 0:
                comp_bits.append("overheated")
            if (comp.get("analyst_signal") or 0) > 0:
                comp_bits.append("analyst_up")
            if (comp.get("congress_signal") or 0) > 0:
                comp_bits.append("congress_buy")
            history_lines.append(
                f"   #{r['rank']:>2} {r['symbol']:<8}  actual={r.get('actual_change_pct') or 0:+.2f}%  "
                f"rank={r.get('universe_rank') or '?'}/{r.get('universe_size') or '?'}  "
                f"({', '.join(comp_bits) or 'momentum only'})"
            )

    by_strat_lines = [
        f"  v{v}: {b['predictions']} preds, {b['hits']} hits, "
        f"hit_rate={b['hit_rate']*100:.1f}%"
        for v, b in (by_strategy or {}).items()
    ]

    return f"""You are maintaining the prediction playbook (a markdown file)
for a daily top-10 gainers predictor.

CURRENT PLAYBOOK (verbatim):
```
{current_skills}
```

RECENT PREDICTION RECORD (most-recent-first, summary + top 5 picks per day):
{chr(10).join(history_lines) or '(no completed predictions yet)'}

PER-STRATEGY HIT RATES:
{chr(10).join(by_strat_lines) or '(none)'}

Rewrite the playbook in place. Rules:
  1. Keep the same SECTION HEADERS so the file stays parseable.
  2. The first line MUST be exactly: {_SKILLS_VERSION_TAG}
  3. Be SPECIFIC — every claim should be quantified (hit-rate impact,
     sector, regime) and cite evidence ("12 of 14 picks in Technology
     during bull regime hit top-25").
  4. Be concise — promote confirmed hypotheses, retire invalidated ones.
     Don't bloat the file with low-signal noise.
  5. If you don't have enough data for a section, say so plainly
     (e.g. "Not enough bear-regime days yet — only 1 sampled").
  6. The bottom MUST end with a "_Last updated: ..._" line with today's
     ISO date.

Return ONLY the new markdown content. No backticks, no preamble. The
content MUST start with the version tag line {_SKILLS_VERSION_TAG}."""


def _load_history_with_context(window_days: int = 30) -> list[dict]:
    """Like _completed_predictions_window but also pulls pulse + components.

    Each row gets pulse_snapshot (dict) and components (dict) parsed from
    JSON so the prompt builder doesn't have to.
    """
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT dp.prediction_date     AS date,
                   dp.rank                AS rank,
                   dp.symbol              AS symbol,
                   dp.score               AS predicted_score,
                   dp.reasoning           AS reasoning,
                   dp.strategy_version    AS strategy_version,
                   dp.pulse_snapshot_json AS pulse_snapshot_json,
                   dp.components_json     AS components_json,
                   dpa.change_pct         AS actual_change_pct,
                   dpa.universe_rank      AS universe_rank,
                   dpa.universe_size      AS universe_size
              FROM daily_predictions dp
              JOIN daily_prediction_actuals dpa
                ON dp.prediction_date = dpa.prediction_date
               AND dp.symbol = dpa.symbol
             WHERE dpa.universe_rank IS NOT NULL
             ORDER BY dp.prediction_date DESC, dp.rank
             LIMIT ?
            """,
            (window_days * 10,),
        ).fetchall()
    finally:
        conn.close()

    out = []
    for r in rows:
        row = dict(r)
        try:
            row["pulse_snapshot"] = json.loads(row["pulse_snapshot_json"]) if row.get("pulse_snapshot_json") else {}
        except Exception:
            row["pulse_snapshot"] = {}
        try:
            row["components"] = json.loads(row["components_json"]) if row.get("components_json") else {}
        except Exception:
            row["components"] = {}
        out.append(row)
    return out


def update_prediction_skills(*, window_days: int = 30, force: bool = False) -> dict:
    """Ask Claude to rewrite the playbook from current data.

    Returns {updated: bool, reason: str | None}. On success, the new
    content is written to data/predictions/skills.md atomically.
    """
    history = _load_history_with_context(window_days)
    if not history and not force:
        return {
            "updated": False,
            "reason": "no_completed_predictions_in_window",
            "history_rows": 0,
        }

    accuracy = get_accuracy_window(window_days=window_days, hit_threshold=25)
    current = _read_skills()

    prompt = _build_skills_update_prompt(current, history, accuracy.get("by_strategy") or {})

    try:
        # No retries — if Claude fails, fall through cleanly. The current
        # playbook stays as-is rather than being half-overwritten.
        raw = ask_claude_json(prompt, model="haiku", timeout=120, retries=0)
    except Exception as e:
        logger.info("predictions: skills update Claude call failed: %r", e)
        raw = None

    # Claude is asked for raw text, not JSON — but ask_claude_json tries
    # to JSON-decode. We handle either shape: if it came back as a dict
    # with a "content" key (alternate response shape) use that; if it's a
    # bare string with the version tag, use it; otherwise reject.
    if isinstance(raw, dict) and isinstance(raw.get("content"), str):
        new_content = raw["content"]
    elif isinstance(raw, str):
        new_content = raw
    else:
        # Fall back to direct ask_claude (returns string)
        from src.utils.claude_cli import ask_claude
        try:
            new_content = ask_claude(prompt, model="haiku", timeout=120) or ""
        except Exception as e:
            logger.info("predictions: skills update text-mode call failed: %r", e)
            new_content = ""

    if _SKILLS_VERSION_TAG not in new_content:
        return {
            "updated": False,
            "reason": "claude_response_missing_version_tag",
            "history_rows": len(history),
        }

    # Trim anything before the version tag (Claude sometimes adds
    # explanatory preamble despite being asked not to).
    tag_idx = new_content.find(_SKILLS_VERSION_TAG)
    if tag_idx > 0:
        new_content = new_content[tag_idx:]

    _write_skills(new_content)
    return {
        "updated":      True,
        "history_rows": len(history),
        "bytes":        len(new_content.encode("utf-8")),
    }
