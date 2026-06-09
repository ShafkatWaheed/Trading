"""yfinance options provider — free fallback when paid sources (Polygon) fail.

Returns the same OptionsSummary dataclass shape that PolygonProvider produces,
so the analysis layer (src.analysis.options_flow.analyze) can consume either
source interchangeably.

Coverage tradeoffs vs Polygon:
  • Put/call ratio (volume + OI)   ✓
  • Total call / put volume + OI   ✓
  • Avg implied volatility          ✓ (volume-weighted across active strikes)
  • Max pain                        ✓ (computed from open interest per expiration)
  • Unusual activity                ✓ (filter: volume > 2 * OI AND volume > 100)
  • Underlying price                ✓
  • IV rank / percentile            ✗ (yfinance doesn't expose historical IV)
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.models.data_types import OptionsChain, OptionContract, OptionsSummary, UnusualActivity
from src.utils.db import cache_get, cache_set, log_api_call


_CACHE_TTL_MINUTES = 30
_EXPIRATIONS_TO_SCAN = 3        # nearest 3 — covers weekly + next monthly
_UNUSUAL_VOL_MIN = 100          # contract must have at least this volume
_UNUSUAL_VOI_RATIO = 2.0        # volume / open_interest threshold
_MAX_UNUSUAL = 8


def _safe_decimal(v) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        d = Decimal(str(v))
        if d.is_nan():
            return None
        return d
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> int:
    """NaN-safe int coercion — yfinance returns NaN for empty volume / OI cells."""
    if v is None:
        return 0
    try:
        f = float(v)
        if f != f:  # NaN check (NaN is the only value not equal to itself)
            return 0
        return int(f)
    except (TypeError, ValueError):
        return 0


def _safe_float(v) -> float:
    """NaN-safe float coercion — returns 0.0 on NaN or non-convertible input."""
    if v is None:
        return 0.0
    try:
        f = float(v)
        if f != f:
            return 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


def _max_pain_for_expiration(calls_df, puts_df) -> Optional[Decimal]:
    """For each candidate settlement strike S, compute total option-writer
    payout. Strike that MINIMIZES total payout = max pain.

    Pure open-interest based — matches the standard definition. Volume-based
    variants exist but OI is more stable.
    """
    if calls_df is None or puts_df is None:
        return None
    strikes = set()
    if hasattr(calls_df, "strike"):
        strikes.update(float(x) for x in calls_df["strike"].tolist())
    if hasattr(puts_df, "strike"):
        strikes.update(float(x) for x in puts_df["strike"].tolist())
    if not strikes:
        return None

    # Precompute (strike, oi) lists for the inner loop
    call_rows = [
        (_safe_float(r["strike"]), _safe_int(r.get("openInterest", 0)))
        for _, r in calls_df.iterrows()
    ]
    put_rows = [
        (_safe_float(r["strike"]), _safe_int(r.get("openInterest", 0)))
        for _, r in puts_df.iterrows()
    ]

    best_strike = None
    best_payout = None
    for s in sorted(strikes):
        # Calls in-the-money when S > strike → writer pays (S - strike) * oi
        call_pain = sum(max(s - cs, 0.0) * oi for cs, oi in call_rows)
        # Puts in-the-money when S < strike → writer pays (strike - S) * oi
        put_pain  = sum(max(ps - s, 0.0) * oi for ps, oi in put_rows)
        total = call_pain + put_pain
        if best_payout is None or total < best_payout:
            best_payout = total
            best_strike = s
    return Decimal(str(best_strike)) if best_strike is not None else None


def _classify_unusual_sentiment(contract_type: str, strike: float,
                                 spot: float) -> str:
    """Heuristic sentiment for an unusual contract.

    Calls bought above the money = bullish bet (buying upside).
    Puts bought below the money = bearish bet (buying downside).
    ATM either side = neutral. Deep ITM/OTM flipped = often hedging, mark neutral.
    """
    ct = (contract_type or "").lower()
    if not spot or spot <= 0:
        return "neutral"
    moneyness = strike / spot
    if ct == "call":
        if moneyness > 1.02:
            return "bullish"
        if moneyness < 0.95:
            return "neutral"  # deep ITM call = often hedging, not directional
        return "neutral"
    if ct == "put":
        if moneyness < 0.98:
            return "bearish"
        if moneyness > 1.05:
            return "neutral"  # deep ITM put = hedging
        return "neutral"
    return "neutral"


def get_options_summary(symbol: str) -> OptionsSummary:
    """Cached options summary built from yfinance chains.

    Raises on hard failure (no ticker, no expirations); the caller handles
    that by falling back to the "unavailable" payload.
    """
    sym = symbol.upper()
    cache_key = f"yf_options:v1:{sym}"
    cached = cache_get(cache_key)
    if cached:
        # Re-hydrate from dict (cached as plain dict, not dataclass)
        return _dict_to_summary(cached)

    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("yfinance not installed") from e

    t = yf.Ticker(sym)

    # 1. Underlying price
    info = t.info or {}
    spot_raw = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
    if not spot_raw:
        raise ValueError(f"No spot price for {sym}")
    spot = Decimal(str(spot_raw))

    # 2. Expirations
    expirations = list(t.options or [])
    if not expirations:
        raise ValueError(f"No options expirations for {sym}")

    target_expirations = expirations[:_EXPIRATIONS_TO_SCAN]
    log_api_call("yfinance", f"options/{sym}/{len(target_expirations)}exp", "success")

    # 3. Aggregate chains
    total_call_vol = 0
    total_put_vol  = 0
    total_call_oi  = 0
    total_put_oi   = 0
    iv_weighted_sum = 0.0
    iv_weight       = 0.0
    unusual: list[UnusualActivity] = []
    nearest_max_pain: Optional[Decimal] = None

    for i, exp in enumerate(target_expirations):
        try:
            chain = t.option_chain(exp)
        except Exception:
            continue
        calls = chain.calls
        puts  = chain.puts

        # Aggregate volumes + OI
        if hasattr(calls, "volume"):
            total_call_vol += int(calls["volume"].fillna(0).sum())
            total_call_oi  += int(calls["openInterest"].fillna(0).sum())
        if hasattr(puts, "volume"):
            total_put_vol += int(puts["volume"].fillna(0).sum())
            total_put_oi  += int(puts["openInterest"].fillna(0).sum())

        # Volume-weighted IV across active contracts
        for df, ct in ((calls, "call"), (puts, "put")):
            for _, row in df.iterrows():
                vol = _safe_int(row.get("volume", 0))
                if vol <= 0:
                    continue
                iv = _safe_float(row.get("impliedVolatility", 0))
                if iv > 0:
                    iv_weighted_sum += iv * vol
                    iv_weight       += vol

                # Unusual activity: V/OI surge + meaningful volume
                oi = _safe_int(row.get("openInterest", 0))
                if vol >= _UNUSUAL_VOL_MIN and oi > 0 and (vol / oi) >= _UNUSUAL_VOI_RATIO:
                    strike = _safe_float(row.get("strike", 0))
                    last_price = _safe_float(row.get("lastPrice", 0))
                    premium = Decimal(str(last_price * vol * 100))  # contract multiplier
                    unusual.append(UnusualActivity(
                        underlying=sym,
                        contract_type=ct,
                        strike=Decimal(str(strike)),
                        expiration=exp,
                        volume=vol,
                        open_interest=oi,
                        volume_oi_ratio=Decimal(str(round(vol / oi, 2))),
                        implied_volatility=Decimal(str(round(iv, 4))),
                        premium=premium,
                        sentiment=_classify_unusual_sentiment(ct, strike, float(spot)),
                        timestamp=datetime.utcnow().isoformat() + "Z",
                    ))

        # Max pain from the nearest expiration only (most actionable)
        if i == 0:
            nearest_max_pain = _max_pain_for_expiration(calls, puts)

    # Cap + sort unusual by premium descending — biggest dollar bets first
    unusual.sort(key=lambda u: float(u.premium), reverse=True)
    unusual = unusual[:_MAX_UNUSUAL]

    # P/C ratio — fall back to OI if volume is zero (illiquid pre-market reads)
    if total_call_vol > 0:
        pcr = Decimal(str(round(total_put_vol / total_call_vol, 3)))
    elif total_call_oi > 0:
        pcr = Decimal(str(round(total_put_oi / total_call_oi, 3)))
    else:
        pcr = Decimal("1.0")

    avg_iv = Decimal(str(round(iv_weighted_sum / iv_weight, 4))) if iv_weight > 0 else Decimal("0")

    summary = OptionsSummary(
        underlying=sym,
        underlying_price=spot,
        put_call_ratio=pcr,
        total_call_volume=total_call_vol,
        total_put_volume=total_put_vol,
        total_call_oi=total_call_oi,
        total_put_oi=total_put_oi,
        avg_iv=avg_iv,
        iv_rank=None,         # yfinance doesn't expose historical IV
        iv_percentile=None,
        max_pain=nearest_max_pain,
        unusual_activity=unusual,
        sentiment="",
    )
    summary.compute_sentiment()

    try:
        cache_set(cache_key, _summary_to_dict(summary), ttl_minutes=_CACHE_TTL_MINUTES)
    except Exception:
        pass
    return summary


# ── Options chain (free fallback for contract_selector) ──────────────


def _row_to_contract(row, ctype: str, sym: str, exp: str) -> OptionContract:
    """Convert a single DataFrame row to an OptionContract.

    yfinance has no greeks — delta stays None; all Decimal fields coerced via
    _safe_decimal with Decimal("0") fallback so the dataclass never gets None
    in required fields.
    """
    symbol = str(row.get("contractSymbol") or f"{sym}{ctype}{row.get('strike')}")
    return OptionContract(
        symbol=symbol,
        underlying=sym.upper(),
        contract_type=ctype,
        strike=_safe_decimal(row.get("strike")) or Decimal("0"),
        expiration=exp,
        bid=_safe_decimal(row.get("bid")) or Decimal("0"),
        ask=_safe_decimal(row.get("ask")) or Decimal("0"),
        last_price=_safe_decimal(row.get("lastPrice")) or Decimal("0"),
        volume=_safe_int(row.get("volume")),
        open_interest=_safe_int(row.get("openInterest")),
        implied_volatility=_safe_decimal(row.get("impliedVolatility")) or Decimal("0"),
        delta=None,  # yfinance does not provide greeks
    )


def get_options_chain(
    symbol: str,
    *,
    dte_target: int = 35,
    max_expirations: int = 3,
    now_date: str | None = None,
) -> list[OptionsChain]:
    """Build OptionsChain list from yfinance (free, no API key required).

    Selects up to *max_expirations* expirations whose DTE is closest to
    *dte_target*. Returns [] when the ticker has no listed options (e.g.
    micro-caps like MNTS) or on any hard failure — never fabricates data.
    """
    sym = symbol.upper()
    try:
        import yfinance as yf

        t = yf.Ticker(sym)

        # ── Underlying spot price ─────────────────────────────────────
        spot: Decimal | None = None
        fast_info = getattr(t, "fast_info", None)
        if fast_info is not None:
            raw = None
            try:
                raw = fast_info["lastPrice"]
            except (KeyError, TypeError):
                pass
            if raw is None:
                raw = getattr(fast_info, "last_price", None)
            spot = _safe_decimal(raw)
        if not spot:
            info = t.info or {}
            raw_info = (
                info.get("regularMarketPrice")
                or info.get("currentPrice")
                or info.get("previousClose")
            )
            spot = _safe_decimal(raw_info)
        spot = spot or Decimal("0")

        # ── Expirations ───────────────────────────────────────────────
        exps = list(t.options or [])
        if not exps:
            log_api_call("yfinance", f"options_chain/{sym}", "ok")
            return []

        today = (
            datetime.strptime(now_date, "%Y-%m-%d").date()
            if now_date
            else datetime.utcnow().date()
        )

        # Only consider non-expired expirations; sort by proximity to dte_target
        valid_exps = []
        for exp in exps:
            try:
                dte = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
            except ValueError:
                continue
            if dte >= 0:
                valid_exps.append((abs(dte - dte_target), exp))
        valid_exps.sort(key=lambda x: x[0])
        chosen = [exp for _, exp in valid_exps[:max_expirations]]

        if not chosen:
            log_api_call("yfinance", f"options_chain/{sym}", "ok")
            return []

        # ── Build one OptionsChain per chosen expiration ──────────────
        chains: list[OptionsChain] = []
        for exp in chosen:
            try:
                oc = t.option_chain(exp)
            except Exception:
                continue
            calls = [
                _row_to_contract(row, "call", sym, exp)
                for _, row in oc.calls.iterrows()
            ]
            puts = [
                _row_to_contract(row, "put", sym, exp)
                for _, row in oc.puts.iterrows()
            ]
            chains.append(
                OptionsChain(
                    underlying=sym,
                    underlying_price=spot,
                    expiration=exp,
                    calls=calls,
                    puts=puts,
                )
            )

        log_api_call("yfinance", f"options_chain/{sym}", "ok")
        return chains

    except Exception as e:
        log_api_call(
            "yfinance",
            f"options_chain/{sym}",
            "error",
            error=str(e)[:120],
        )
        return []


# ── (de)serialization helpers ───────────────────────────────────────


def _summary_to_dict(s: OptionsSummary) -> dict:
    return {
        "underlying": s.underlying,
        "underlying_price": str(s.underlying_price),
        "put_call_ratio": str(s.put_call_ratio),
        "total_call_volume": s.total_call_volume,
        "total_put_volume": s.total_put_volume,
        "total_call_oi": s.total_call_oi,
        "total_put_oi": s.total_put_oi,
        "avg_iv": str(s.avg_iv),
        "iv_rank": str(s.iv_rank) if s.iv_rank is not None else None,
        "iv_percentile": str(s.iv_percentile) if s.iv_percentile is not None else None,
        "max_pain": str(s.max_pain) if s.max_pain is not None else None,
        "sentiment": s.sentiment,
        "unusual_activity": [
            {
                "underlying": u.underlying,
                "contract_type": u.contract_type,
                "strike": str(u.strike),
                "expiration": u.expiration,
                "volume": u.volume,
                "open_interest": u.open_interest,
                "volume_oi_ratio": str(u.volume_oi_ratio),
                "implied_volatility": str(u.implied_volatility),
                "premium": str(u.premium),
                "sentiment": u.sentiment,
                "timestamp": u.timestamp,
            }
            for u in s.unusual_activity
        ],
    }


def _dict_to_summary(d: dict) -> OptionsSummary:
    s = OptionsSummary(
        underlying=d["underlying"],
        underlying_price=Decimal(d["underlying_price"]),
        put_call_ratio=Decimal(d["put_call_ratio"]),
        total_call_volume=d["total_call_volume"],
        total_put_volume=d["total_put_volume"],
        total_call_oi=d.get("total_call_oi", 0),
        total_put_oi=d.get("total_put_oi", 0),
        avg_iv=Decimal(d["avg_iv"]),
        iv_rank=Decimal(d["iv_rank"]) if d.get("iv_rank") else None,
        iv_percentile=Decimal(d["iv_percentile"]) if d.get("iv_percentile") else None,
        max_pain=Decimal(d["max_pain"]) if d.get("max_pain") else None,
        sentiment=d.get("sentiment", ""),
    )
    s.unusual_activity = [
        UnusualActivity(
            underlying=u["underlying"],
            contract_type=u["contract_type"],
            strike=Decimal(u["strike"]),
            expiration=u["expiration"],
            volume=u["volume"],
            open_interest=u["open_interest"],
            volume_oi_ratio=Decimal(u["volume_oi_ratio"]),
            implied_volatility=Decimal(u["implied_volatility"]),
            premium=Decimal(u["premium"]),
            sentiment=u["sentiment"],
            timestamp=u["timestamp"],
        )
        for u in d.get("unusual_activity", [])
    ]
    return s
