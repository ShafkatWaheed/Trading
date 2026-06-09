"""Smart-money flow — institutional + insider + congressional activity for a stock.

Combines three independent sources, each best-effort (one failing doesn't kill
the others). Cached for 6h since 13F is quarterly and Form 4 / congressional
filings trickle in daily.

Also exposes `get_sector_tape(window_days)` — a market-wide rollup of 13F
holdings deltas by sector. Used by the market pulse page and brief Phase A.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from src.utils.db import cache_get, cache_set, get_connection
from api.services import ownership_service

_CACHE_TTL_MINUTES = 6 * 60
_TAPE_CACHE_TTL_MINUTES = 6 * 60
# A summary whose section(s) errored (e.g. a transient SEC 500) is cached only
# briefly so it self-heals on the next view instead of sticking for the full TTL.
_ERROR_CACHE_TTL_MINUTES = 5


def _to_float(v) -> float | None:
    try:
        if v is None:
            return None
        if isinstance(v, Decimal):
            return float(v)
        return float(v)
    except (TypeError, ValueError):
        return None


# ── Institutional (top holders + recent additions/trims) ──────────


def _institutional_section(symbol: str) -> dict:
    out: dict = {
        "top_holders": [],
        "total_known_holders": 0,
        "error": None,
    }
    try:
        data = ownership_service.top_holders(symbol, max_results=10)
        out["total_known_holders"] = data.get("total", 0)
        for h in data.get("holders", []):
            out["top_holders"].append({
                "name":              h.get("institution_name") or h.get("cik"),
                "type":              h.get("institution_type"),
                "value_usd":         _to_float(h.get("value_usd")),
                "pct_outstanding":   _to_float(h.get("pct_outstanding")),
                "pct_portfolio":     _to_float(h.get("pct_portfolio")),
                "as_of":             h.get("as_of"),
            })
    except Exception as e:
        out["error"] = f"Institutional fetch failed: {e}"
    return out


# ── Insider (last 90d Form 4) ─────────────────────────────────────


def _insider_section(symbol: str) -> dict:
    out: dict = {
        "total_trades": 0,
        "total_buys": 0,
        "total_sells": 0,
        "unique_insiders": 0,
        "cluster_buy": False,
        "buy_value_usd": None,
        "sell_value_usd": None,
        "net_value_usd": None,
        "signal": "",
        "recent_trades": [],
        "error": None,
    }
    try:
        from src.data.sec_edgar import SECEdgarProvider
        prov = SECEdgarProvider()
        s = prov.get_insider_summary(symbol, days=90)
        buy_v = _to_float(s.buy_value) or 0.0
        sell_v = _to_float(s.sell_value) or 0.0
        out.update({
            "total_trades":     s.total_trades,
            "total_buys":       s.total_buys,
            "total_sells":      s.total_sells,
            "unique_insiders":  s.unique_insiders,
            "cluster_buy":      bool(s.cluster_buy),
            "buy_value_usd":    buy_v,
            "sell_value_usd":   sell_v,
            "net_value_usd":    buy_v - sell_v,
            "signal":           s.signal or "",
        })
        for t in (s.recent_trades or [])[:10]:
            out["recent_trades"].append({
                "filer":             t.filer_name,
                "title":             t.filer_title,
                "transaction":       t.transaction_type,
                "shares":            t.shares,
                "price":             _to_float(t.price),
                "value_usd":         _to_float(t.total_value),
                "transaction_date":  t.transaction_date,
                "filing_date":       t.filing_date,
            })
    except Exception as e:
        out["error"] = f"Insider fetch failed: {e}"
    return out


# ── Congressional (Capitol Trades, last 180d) ─────────────────────


def _congress_section(symbol: str) -> dict:
    out: dict = {
        "total_trades": 0,
        "total_buys": 0,
        "total_sells": 0,
        "unique_politicians": 0,
        "net_sentiment": "neutral",
        "top_buyers": [],
        "top_sellers": [],
        "recent_trades": [],
        "party_breakdown": {},
        # New: surfaced from src.analysis.congress_signal.analyze()
        "signal_score": 0,
        "signal_label": "no_data",
        "bipartisan": False,
        "signal_factors": [],
        "error": None,
    }
    try:
        from src.analysis import congress_signal as cs_analysis
        from src.data.congress import CongressDataProvider
        prov = CongressDataProvider()
        s = prov.get_summary(symbol, days=180)
        cs_score = cs_analysis.analyze(s)
        out.update({
            "total_trades":       s.total_trades,
            "total_buys":         s.total_buys,
            "total_sells":        s.total_sells,
            "unique_politicians": s.unique_politicians,
            "net_sentiment":      s.net_sentiment or "neutral",
            "top_buyers":         list(s.top_buyers)[:25],
            "top_sellers":        list(s.top_sellers)[:25],
            "party_breakdown":    s.party_breakdown or {},
            "signal_score":       cs_score.score,
            "signal_label":       cs_score.signal,
            "bipartisan":         cs_score.bipartisan,
            "signal_factors":     cs_score.factors,
        })
        for t in (s.recent_trades or [])[:50]:
            out["recent_trades"].append({
                "politician":        t.politician,
                "party":             t.party,
                "chamber":           t.chamber,
                "state":             t.state,
                "transaction":       t.transaction_type,
                "amount_range":      t.amount_range,
                "amount_low_usd":    _to_float(t.amount_low),
                "amount_high_usd":   _to_float(t.amount_high),
                "trade_date":        t.trade_date,
                "filed_date":        t.filed_date,
                "days_to_file":      t.days_to_file,
                "committees":        list(t.committees) if t.committees else [],
            })
    except Exception as e:
        out["error"] = f"Congressional fetch failed: {e}"
    return out


# ── Composite read-out ────────────────────────────────────────────


def _summary_signal(institutional: dict, insider: dict, congress: dict) -> str:
    """One-line plain-English readout combining all three signals."""
    parts: list[str] = []

    # Insider weight
    if insider["cluster_buy"]:
        parts.append("multiple insiders buying together (cluster-buy)")
    elif insider["total_buys"] > insider["total_sells"] and (insider["net_value_usd"] or 0) > 0:
        parts.append(f"insiders net buying (${insider['net_value_usd']:,.0f})")
    elif insider["total_sells"] > insider["total_buys"] and (insider["net_value_usd"] or 0) < 0:
        parts.append(f"insiders net selling (${abs(insider['net_value_usd']):,.0f})")

    # Congress weight
    if congress["net_sentiment"] in ("strong_buy", "buy"):
        parts.append(f"{congress['unique_politicians']} politicians buying")
    elif congress["net_sentiment"] in ("strong_sell", "sell"):
        parts.append(f"{congress['unique_politicians']} politicians selling")

    # Institutional weight
    if institutional["total_known_holders"] > 0:
        parts.append(f"{institutional['total_known_holders']} institutional holders tracked")

    return "; ".join(parts) if parts else "No notable smart-money activity in the tracking window."


_VALID_WINDOWS = (90, 180, 365)


def get_sector_tape(window_days: int = 180, *, force: bool = False) -> dict:
    """Sector-level 13F net dollar flow over the trailing window.

    For each institution in `institution_holdings`, find the most recent
    snapshot inside the window (`now`) and the most recent snapshot strictly
    before the window starts (`then`). Per-symbol delta is `now - then`;
    new positions count as full adds, dropped positions as full trims.

    Sectors with no qualifying delta data (no institutions with both
    snapshots) are still surfaced with `net_dollar_flow=None` and a
    `coverage_note`, so the caller can see "no flow signal here" instead of
    confusing "$0".

    Args:
        window_days: 90 / 180 / 365 (others rejected).
        force: bypass cache.

    Returns:
        {
          "window_days": int,
          "as_of": "YYYY-MM-DD",
          "sectors": [
            {
              "sector": str,
              "net_dollar_flow": float | None,   # USD; None when no delta data
              "adds_count": int,                  # CIK,sym pairs with delta>0
              "drops_count": int,                 # CIK,sym pairs with delta<0
              "direction": "inflow"|"outflow"|"neutral"|"no_data",
              "top_added":   [{"symbol", "delta_usd", "filings"}],   # top 5
              "top_trimmed": [{"symbol", "delta_usd", "filings"}],   # top 3
            }, ...
          ],
          "ciks_with_delta_data": int,
          "ciks_total": int,
          "coverage_note": str,
        }
    """
    if window_days not in _VALID_WINDOWS:
        window_days = 180

    cache_key = f"smart_money:sector_tape:v2:{window_days}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    window_start = (datetime.utcnow() - timedelta(days=window_days)).strftime("%Y-%m-%d")

    conn = get_connection()
    try:
        # symbol -> sector (primary mapping only)
        sector_by_symbol = dict(
            conn.execute(
                """
                SELECT si.symbol, ind.sector
                FROM stock_industry si
                JOIN industries ind ON ind.code = si.industry_code
                WHERE si.is_primary = 1
                """
            ).fetchall()
        )

        # cik -> type (so we can split "passive" index funds from "active" managers).
        # Passive = index_fund. Active = everything else (active_mgr, hedge_fund,
        # sovereign, pension). Passive flow mostly reflects cap-weighting math;
        # active flow reflects conviction. Splitting these is the single biggest
        # signal-quality improvement on the tape.
        cik_type = dict(
            conn.execute("SELECT cik, type FROM institutions").fetchall()
        )

        # Per CIK: latest snapshot date INSIDE the window, and latest STRICTLY
        # BEFORE the window.
        cik_anchors: dict[str, dict] = {}
        # Use all snapshots regardless of `source` — both '13F' (from the loader)
        # and 'hand' (from authoritative manual seeds of public 13F filings)
        # represent real holdings. CLAUDE.md prohibits FABRICATED data, not
        # legitimate data tagged via a different ingestion path.
        for row in conn.execute(
            """
            SELECT cik, MAX(as_of) AS t_end
            FROM institution_holdings
            WHERE as_of >= ?
            GROUP BY cik
            """,
            (window_start,),
        ).fetchall():
            cik_anchors.setdefault(row["cik"], {})["t_end"] = row["t_end"]

        for row in conn.execute(
            """
            SELECT cik, MAX(as_of) AS t_start
            FROM institution_holdings
            WHERE as_of < ?
            GROUP BY cik
            """,
            (window_start,),
        ).fetchall():
            cik_anchors.setdefault(row["cik"], {})["t_start"] = row["t_start"]

        ciks_total = len(cik_anchors)
        ciks_with_delta = sum(1 for v in cik_anchors.values() if v.get("t_end") and v.get("t_start"))

        # Build THREE parallel aggregates in one pass: all / active / passive.
        # Each is `sector -> {net, adds, drops, per_symbol}`.
        views = {
            "all":     {},
            "active":  {},
            "passive": {},
        }
        view_cik_counts = {"all": 0, "active": 0, "passive": 0}

        for cik, anchors in cik_anchors.items():
            t_end = anchors.get("t_end")
            t_start = anchors.get("t_start")
            if not (t_end and t_start):
                continue

            # Determine which view(s) this CIK contributes to
            ctype = cik_type.get(cik)
            target_views = ["all", "passive" if ctype == "index_fund" else "active"]
            for v in target_views:
                view_cik_counts[v] += 1

            now_pos = dict(
                conn.execute(
                    "SELECT symbol, value_usd FROM institution_holdings "
                    "WHERE cik=? AND as_of=? AND value_usd IS NOT NULL",
                    (cik, t_end),
                ).fetchall()
            )
            then_pos = dict(
                conn.execute(
                    "SELECT symbol, value_usd FROM institution_holdings "
                    "WHERE cik=? AND as_of=? AND value_usd IS NOT NULL",
                    (cik, t_start),
                ).fetchall()
            )

            all_symbols = set(now_pos) | set(then_pos)
            for sym in all_symbols:
                sector = sector_by_symbol.get(sym)
                if not sector:
                    continue
                delta = float(now_pos.get(sym, 0.0)) - float(then_pos.get(sym, 0.0))
                if delta == 0.0:
                    continue
                for v in target_views:
                    bucket = views[v].setdefault(sector, {
                        "net": 0.0, "adds": 0, "drops": 0,
                        "per_symbol": {},
                    })
                    bucket["net"] += delta
                    if delta > 0:
                        bucket["adds"] += 1
                    else:
                        bucket["drops"] += 1
                    sym_entry = bucket["per_symbol"].setdefault(sym, {"delta": 0.0, "filings": 0})
                    sym_entry["delta"] += delta
                    sym_entry["filings"] += 1
        # Keep `deltas_by_sector` as a local alias to the "all" view for the
        # existing top-level formatting code below.
        deltas_by_sector = views["all"]
    finally:
        conn.close()

    def _format_view(deltas: dict) -> list[dict]:
        out = []
        for sector in sorted(deltas.keys(), key=lambda s: abs(deltas[s]["net"]), reverse=True):
            bucket = deltas[sector]
            per_sym = sorted(
                ({"symbol": s, "delta_usd": v["delta"], "filings": v["filings"]}
                 for s, v in bucket["per_symbol"].items()),
                key=lambda x: x["delta_usd"], reverse=True,
            )
            top_added = [x for x in per_sym if x["delta_usd"] > 0][:5]
            top_trimmed = [x for x in reversed(per_sym) if x["delta_usd"] < 0][:3]
            net = bucket["net"]
            direction = "inflow" if net > 0 else "outflow" if net < 0 else "neutral"
            out.append({
                "sector": sector,
                "net_dollar_flow": net,
                "adds_count": bucket["adds"],
                "drops_count": bucket["drops"],
                "direction": direction,
                "top_added": top_added,
                "top_trimmed": top_trimmed,
            })
        return out

    out_sectors          = _format_view(views["all"])
    out_sectors_active   = _format_view(views["active"])
    out_sectors_passive  = _format_view(views["passive"])

    coverage_note = (
        f"Based on {ciks_with_delta} of {ciks_total} institutions with sequential snapshots "
        f"in the trailing {window_days}d window. 45-day 13F disclosure lag applies."
    )
    if ciks_with_delta == 0:
        coverage_note = (
            f"No institutions have sequential 13F snapshots in the trailing {window_days}d "
            f"window yet — flow tape requires 2+ filings per CIK. Backfill in progress."
        )

    payload = {
        "window_days": window_days,
        "as_of": datetime.utcnow().strftime("%Y-%m-%d"),
        "sectors": out_sectors,              # backward-compat: == by_flow_type.all
        "by_flow_type": {
            "all":     {"sectors": out_sectors,         "ciks_count": view_cik_counts["all"]},
            "active":  {"sectors": out_sectors_active,  "ciks_count": view_cik_counts["active"]},
            "passive": {"sectors": out_sectors_passive, "ciks_count": view_cik_counts["passive"]},
        },
        "ciks_with_delta_data": ciks_with_delta,
        "ciks_total": ciks_total,
        "coverage_note": coverage_note,
        "from_cache": False,
    }

    if out_sectors:
        try:
            cache_set(cache_key, payload, ttl_minutes=_TAPE_CACHE_TTL_MINUTES)
        except Exception:
            pass
    return payload


def get_smart_money(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    cache_key = f"smart_money:v1:{symbol}"

    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    institutional = _institutional_section(symbol)
    insider       = _insider_section(symbol)
    congress      = _congress_section(symbol)

    payload = {
        "symbol":        symbol,
        "institutional": institutional,
        "insider":       insider,
        "congress":      congress,
        "summary":       _summary_signal(institutional, insider, congress),
        "last_updated":  datetime.utcnow().isoformat() + "Z",
        "from_cache":    False,
    }

    sections_errored = any(
        isinstance(sec, dict) and sec.get("error")
        for sec in (institutional, insider, congress)
    )
    ttl = _ERROR_CACHE_TTL_MINUTES if sections_errored else _CACHE_TTL_MINUTES
    try:
        cache_set(cache_key, payload, ttl_minutes=ttl)
    except Exception:
        pass
    return payload
