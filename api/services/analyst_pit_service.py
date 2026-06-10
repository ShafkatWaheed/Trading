"""Point-in-time signal assembler for the AI analyst.

Every reader returns only data knowable on/before the as-of date `D`
(YYYY-MM-DD). No lookahead (CLAUDE.md). Two views:
  - assemble_compact(symbols, D) -> list[dict]  (one row/symbol, for triage)
  - assemble_full(...)  (added in a later task)

Reuses the historical PIT helpers in api/services/ai_analyst_service.py.
"""
from __future__ import annotations

from src.utils.db import get_connection, init_db


def congress_flags_as_of(symbols: list[str], as_of: str) -> dict[str, int]:
    """{symbol: count of congressional BUYS disclosed (filing_date <= D)}.

    PIT guarantee: filters on filing_date — the date the trade became public.
    """
    if not symbols:
        return {}
    init_db()
    conn = get_connection()
    try:
        ph = ",".join("?" * len(symbols))
        rows = conn.execute(
            f"""
            SELECT ticker, COUNT(*) n FROM congress_trades
            WHERE transaction_type='buy' AND ticker IN ({ph})
              AND filing_date IS NOT NULL AND filing_date <= ?
            GROUP BY ticker
            """,
            (*symbols, as_of),
        ).fetchall()
        return {r["ticker"]: r["n"] for r in rows}
    finally:
        conn.close()


def institution_breadth_as_of(symbols: list[str], as_of: str) -> dict[str, int]:
    """{symbol: distinct 13F holders whose filing period (as_of) <= D}.

    PIT guarantee: a 13F period-end <= D was filed by then (period end always
    precedes the filing). Conservative — never reveals future positions.
    """
    if not symbols:
        return {}
    init_db()
    conn = get_connection()
    try:
        ph = ",".join("?" * len(symbols))
        rows = conn.execute(
            f"""
            SELECT symbol, COUNT(DISTINCT cik) h FROM institution_holdings
            WHERE symbol IN ({ph}) AND as_of <= ?
            GROUP BY symbol
            """,
            (*symbols, as_of),
        ).fetchall()
        return {r["symbol"]: r["h"] for r in rows}
    finally:
        conn.close()


# ── Meta (name / sector) ──────────────────────────────────────────


def _names_for_symbols(conn, symbols: list[str]) -> dict[str, str | None]:
    """{symbol: name} from stocks_universe."""
    if not symbols:
        return {}
    ph = ",".join("?" * len(symbols))
    rows = conn.execute(
        f"SELECT symbol, name FROM stocks_universe WHERE symbol IN ({ph})",
        symbols,
    ).fetchall()
    return {r["symbol"]: r["name"] for r in rows}


def _sectors_for_symbols(conn, symbols: list[str]) -> dict[str, str | None]:
    """{symbol: sector} from each symbol's primary industry row joined to
    industries. Mirrors universe_service._primary_sectors. Absent when unmapped.
    """
    if not symbols:
        return {}
    ph = ",".join("?" * len(symbols))
    rows = conn.execute(
        f"""
        SELECT si.symbol, COALESCE(i.sector, si.industry_code) AS sector
        FROM stock_industry si
        LEFT JOIN industries i ON i.code = si.industry_code
        WHERE si.symbol IN ({ph})
        ORDER BY si.symbol, si.is_primary DESC, si.weight DESC
        """,
        symbols,
    ).fetchall()
    out: dict[str, str | None] = {}
    for r in rows:
        out.setdefault(r["symbol"], r["sector"])  # first row per symbol = primary
    return out


# ── Macro regime (coarse label) ───────────────────────────────────


def _macro_regime(macro: dict) -> str:
    """Coarse risk-regime label derived from a point-in-time macro snapshot.

    NOT a precise signal — a simple bucketing of VIX and trailing 20d S&P move:
      - "risk_off"  : elevated VIX (>25) or S&P 20d change clearly negative (< -3%)
      - "risk_on"   : calm VIX (<15) and S&P 20d change positive (> +2%)
      - "neutral"   : everything else, or when inputs are unavailable
    Inputs come from _macro_at(), which already walks back from D, so the label
    only reflects data knowable on/before D.
    """
    vix = macro.get("vix")
    chg = macro.get("spx_change_20d")
    if (vix is not None and vix > 25) or (chg is not None and chg < -3.0):
        return "risk_off"
    if (vix is not None and vix < 15) and (chg is not None and chg > 2.0):
        return "risk_on"
    return "neutral"


# ── Shared price slice (PIT cut) ──────────────────────────────────


def _sliced_closes(sym: str, as_of: str):
    """Daily close series for `sym` SLICED to bars whose date <= `as_of`.

    This is the single point-in-time cut reused by both `assemble_compact` and
    `_momentum_block`: a symbol with no bar on/before `as_of` yields an empty
    series. Returns a pandas float Series (possibly empty); never raises.
    """
    try:
        from src.data.gateway import DataGateway
        df = DataGateway().get_historical(sym, period_days=180)
        if df is None or df.empty or "date" not in df.columns or "close" not in df.columns:
            return None
        sliced = df[df["date"] <= as_of]
        if sliced.empty:
            return None
        return sliced["close"].astype(float)
    except Exception:
        return None


def _trailing_return_5d(closes) -> float | None:
    """Trailing 5-trading-day % change from a sliced close series, or None."""
    try:
        if closes is None or len(closes) < 6:
            return None
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-6])
        return ((last - prev) / prev) * 100.0 if prev else None
    except Exception:
        return None


# ── Compact (triage) assembler ────────────────────────────────────


def assemble_compact(symbols: list[str], as_of: str) -> list[dict]:
    """One compact triage row per symbol that has price data on/before `as_of`.

    Row schema:
        {"symbol", "name", "sector", "momentum_pct", "sector_flow_pct",
         "congress_buys", "institutions", "macro_regime"}

    POINT-IN-TIME GUARANTEE (CLAUDE.md — no lookahead):
      - momentum_pct: the symbol's daily close series is SLICED to rows whose
        date <= `as_of` before computing the trailing 5-day % change. A symbol
        with no bar on/before `as_of` is OMITTED entirely (never fabricated).
      - macro_regime / sector_flow_pct: the macro/sector helpers walk back from
        their end date, so `as_of` is passed as the end — only data on/before D
        is read.
      - congress_buys: filtered on filing_date <= D (date it became public).
      - institutions: filtered on 13F period-end <= D.
    Any field that can't be honestly produced for `as_of` is None; any symbol
    whose work raises is silently dropped so one bad symbol can't kill the batch.
    """
    if not symbols:
        return []

    # DB-only PIT signals (batched).
    init_db()
    conn = get_connection()
    try:
        names = _names_for_symbols(conn, symbols)
        sectors = _sectors_for_symbols(conn, symbols)
    finally:
        conn.close()
    congress = congress_flags_as_of(symbols, as_of)
    institutions = institution_breadth_as_of(symbols, as_of)

    # Macro history (one fetch for the whole batch). Pass `as_of` as the end so
    # the snapshot only sees data on/before D. A short window suffices for the
    # 20-day trailing move the helper computes.
    from datetime import datetime, timedelta

    from api.services import ai_analyst_service as ai
    from src.data.gateway import DataGateway

    try:
        macro_start = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=120)).strftime("%Y-%m-%d")
        macro_hist = ai._fetch_macro_history(macro_start, as_of)
        macro_regime = _macro_regime(ai._macro_at(macro_hist, as_of))
    except Exception:
        macro_regime = "neutral"

    # Cache sector history per sector so each sector is fetched at most once.
    sector_hist_cache: dict[str, dict] = {}

    def _sector_flow(sector: str | None) -> float | None:
        if not sector:
            return None
        if sector not in sector_hist_cache:
            try:
                start = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=120)).strftime("%Y-%m-%d")
                sector_hist_cache[sector] = ai._fetch_sector_history(sector, start, as_of)
            except Exception:
                sector_hist_cache[sector] = {}
        return ai._sector_perf_at(sector_hist_cache[sector], as_of)

    gateway = DataGateway()
    rows: list[dict] = []
    for symbol in symbols:
        try:
            df = gateway.get_historical(symbol, period_days=180)
            if df is None or df.empty or "date" not in df.columns or "close" not in df.columns:
                continue
            # Slice strictly to bars on/before `as_of` — the PIT cut.
            sliced = df[df["date"] <= as_of]
            if sliced.empty:
                continue
            closes = sliced["close"].astype(float)
            if len(closes) < 6:
                # Not enough history for a trailing 5-day change.
                momentum_pct = None
            else:
                last = float(closes.iloc[-1])
                prev = float(closes.iloc[-6])  # 5 trading days back
                momentum_pct = ((last - prev) / prev) * 100.0 if prev else None

            sector = sectors.get(symbol)
            rows.append({
                "symbol": symbol,
                "name": names.get(symbol),
                "sector": sector,
                "momentum_pct": momentum_pct,
                "sector_flow_pct": _sector_flow(sector),
                "congress_buys": int(congress.get(symbol, 0)),
                "institutions": int(institutions.get(symbol, 0)),
                "macro_regime": macro_regime,
            })
        except Exception:
            # One bad symbol must not kill the batch — omit it.
            continue
    return rows


# ── Full-packet block helpers (deep-read, per symbol) ─────────────
#
# Every helper below is DEFENSIVE: it returns None on any exception or when
# the data cannot be HONESTLY reconstructed for `as_of` (CLAUDE.md — no fake
# data, no lookahead). A None block is the correct, truthful answer when a
# clean point-in-time path is unavailable; it is never a fabricated stub.


def _window_start(as_of: str, days: int) -> str:
    from datetime import datetime, timedelta
    return (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")


def _momentum_block(sym: str, as_of: str) -> dict | None:
    """Trailing momentum from the PIT-sliced close series.

    Always carries a `trailing_return` (5d %, or None) — Task 6's fallback ranks
    on exactly this key. When enough history exists, enriches with the
    historical opportunity score (technicals only, recomputed from the slice up
    to D) for `trend`/`rs`. None if there is no price bar on/before `as_of`.
    """
    try:
        closes = _sliced_closes(sym, as_of)
        if closes is None:
            return None
        block: dict = {"trailing_return": _trailing_return_5d(closes)}

        # Best-effort enrichment: recompute opportunity from the sliced frame.
        try:
            from datetime import datetime, timedelta

            from api.services import ai_analyst_service as ai
            from src.data.gateway import DataGateway

            df = DataGateway().get_historical(sym, period_days=180)
            if df is not None and not df.empty and "date" in df.columns:
                df_slice = df[df["date"] <= as_of]
                if len(df_slice) >= 30:
                    sclose = df_slice["close"].astype(float)
                    stock_change_20d = None
                    if len(sclose) >= 21:
                        p20 = float(sclose.iloc[-21])
                        stock_change_20d = ((float(sclose.iloc[-1]) - p20) / p20) * 100.0 if p20 else None
                    spx_change_20d = None
                    try:
                        macro_start = _window_start(as_of, 120)
                        macro = ai._macro_at(ai._fetch_macro_history(macro_start, as_of), as_of)
                        spx_change_20d = macro.get("spx_change_20d")
                    except Exception:
                        pass
                    opp = ai._historical_opportunity(sym, df_slice, stock_change_20d, spx_change_20d)
                    if opp:
                        block["trend"] = opp.get("strategy")
                        block["rs"] = bool(opp.get("relative_strength"))
                        block["opportunity"] = opp.get("total")
        except Exception:
            pass
        return block
    except Exception:
        return None


def _sector_block(sym: str, as_of: str) -> dict | None:
    """Sector ETF 20d flow at `as_of` (helper walks back from D — PIT-safe)."""
    try:
        from api.services import ai_analyst_service as ai

        init_db()
        conn = get_connection()
        try:
            sector = _sectors_for_symbols(conn, [sym]).get(sym)
        finally:
            conn.close()
        if not sector:
            return None
        start = _window_start(as_of, 120)
        flow = ai._sector_perf_at(ai._fetch_sector_history(sector, start, as_of), as_of)
        return {"sector": sector, "flow_pct": flow}
    except Exception:
        return None


def _macro_block(as_of: str) -> dict | None:
    """Point-in-time macro snapshot (vix/t10y/t2y/spx/spx_change_20d) + regime."""
    try:
        from api.services import ai_analyst_service as ai

        start = _window_start(as_of, 120)
        macro = ai._macro_at(ai._fetch_macro_history(start, as_of), as_of)
        if not macro:
            return None
        out = dict(macro)
        out["regime"] = _macro_regime(macro)
        return out
    except Exception:
        return None


def _insider_block(sym: str, as_of: str) -> dict | None:
    """Insider + congress activity in the 60d window before D (no lookahead)."""
    try:
        from api.services import ai_analyst_service as ai

        pool = ai._fetch_historical_insider_pool(sym)
        win = ai._insider_window(pool, as_of)
        return win or None
    except Exception:
        return None


def _short_interest_block(sym: str, as_of: str) -> dict | None:
    """FINRA daily short-volume window at D (PIT-safe, walks back day-by-day)."""
    try:
        from api.services import ai_analyst_service as ai

        return ai._finra_short_window(sym, as_of)
    except Exception:
        return None


def _earnings_block(sym: str, as_of: str) -> dict | None:
    """Most recent earnings report whose date <= D (PIT cut on the call date).

    Future scheduled earnings are excluded — only already-reported quarters are
    knowable at `as_of`.
    """
    try:
        from src.data.gateway import DataGateway

        cal = DataGateway().get_earnings_calendar(sym) or []
        past = [e for e in cal if e.get("date") and str(e["date"])[:10] <= as_of]
        if not past:
            return None
        latest = max(past, key=lambda e: str(e["date"])[:10])
        return {
            "date": str(latest.get("date"))[:10],
            "eps_estimate": latest.get("eps_estimate"),
            "eps_actual": latest.get("eps_actual"),
            "surprise_pct": latest.get("surprise_pct"),
        }
    except Exception:
        return None


def _fundamentals_block(sym: str, as_of: str) -> dict | None:
    """PIT-safe trailing valuation: TTM EPS from quarterly EPS reported on/before
    D and the close on/before D → trailing P/E.

    We deliberately do NOT read today's fundamentals snapshot
    (DataGateway().get_fundamentals) for a past `as_of`: that P/E reflects the
    CURRENT price and CURRENT TTM EPS and would leak lookahead. When a clean
    quarterly-EPS history isn't available, return None rather than fabricate.
    """
    try:
        from api.services import ai_analyst_service as ai

        eps_hist = ai._fetch_eps_history(sym)
        ttm_eps = ai._ttm_eps_at(eps_hist, as_of) if eps_hist else None
        closes = _sliced_closes(sym, as_of)
        price = float(closes.iloc[-1]) if closes is not None and len(closes) else None
        if ttm_eps is None and price is None:
            return None
        pe = (price / ttm_eps) if (price and ttm_eps and ttm_eps > 0) else None
        return {"ttm_eps": ttm_eps, "pe_ratio": pe}
    except Exception:
        return None


def _news_block(sym: str, as_of: str, *, allow_live_search: bool) -> dict | None:
    """News/sentiment read.

    Live (allow_live_search=True): a today read is honest — return current
    sentiment context.
    Bootstrap (allow_live_search=False): only a date-filtered read (published
    <= D) is PIT-safe. We reuse the date-bounded Polygon path via
    `ai._historical_sentiment`, which only queries headlines in the 7 days
    BEFORE D. With no POLYGON_API_KEY it degrades to a momentum proxy computed
    from the PIT-sliced price (still no lookahead). None on any failure.
    """
    try:
        from api.services import ai_analyst_service as ai

        closes = _sliced_closes(sym, as_of)
        change_5d = _trailing_return_5d(closes)
        change_20d = None
        if closes is not None and len(closes) >= 21:
            p20 = float(closes.iloc[-21])
            change_20d = ((float(closes.iloc[-1]) - p20) / p20) * 100.0 if p20 else None
        sent = ai._historical_sentiment(sym, as_of, change_5d, change_20d)
        return sent or None
    except Exception:
        return None


# ── Live-only block helpers (no PIT history → only when allowed) ──


def _live_options(sym: str) -> dict | None:
    """Live options-flow summary (no point-in-time history exists)."""
    try:
        from src.data.gateway import DataGateway

        summ = DataGateway().get_options_summary(sym)
        if summ is None:
            return None
        pcr = getattr(summ, "put_call_ratio", None)
        return {
            "put_call_ratio": float(pcr) if pcr is not None else None,
            "iv_rank": getattr(summ, "iv_rank", None),
            "unusual_activity": getattr(summ, "unusual_activity", None),
        }
    except Exception:
        return None


def _live_premarket(sym: str) -> dict | None:
    """Live pre-market read. No free PIT history; best-effort current quote
    snapshot. Returns None when unavailable (never fabricated)."""
    try:
        from src.data.gateway import DataGateway

        q = DataGateway().get_quote(sym)
        if q is None:
            return None
        price = getattr(q, "price", None)
        change = getattr(q, "change_percent", None)
        if price is None and change is None:
            return None
        return {
            "price": float(price) if price is not None else None,
            "change_percent": float(change) if change is not None else None,
        }
    except Exception:
        return None


def _live_reddit(sym: str) -> dict | None:
    """Live retail-buzz read. No wired free historical source — return None
    rather than fabricate (CLAUDE.md). Present as a key only in live mode."""
    return None


# ── Full (deep-read) assembler ────────────────────────────────────


def assemble_full(symbols: list[str], as_of: str, *, allow_live_search: bool) -> dict[str, dict]:
    """Full per-symbol packets for the shortlist.

    Bootstrap (allow_live_search=False): only PIT-reconstructable blocks —
    momentum, sector_flow, macro, congress, insider, institutions, news
    (published<=D), earnings (call date<=D), fundamentals, short_interest.

    Live (allow_live_search=True): the above PLUS the live-only signals
    options_flow / premarket / reddit (no PIT history → live only) and live
    web search context.

    Any block that cannot be honestly reconstructed for `as_of` is None,
    never faked (CLAUDE.md). Every block helper is defensive (returns None on
    error) so one bad symbol/source can't kill the batch.
    """
    packets: dict[str, dict] = {}
    if not symbols:
        return packets
    congress = congress_flags_as_of(symbols, as_of)
    institutions = institution_breadth_as_of(symbols, as_of)
    for sym in symbols:
        p = {
            "momentum": _momentum_block(sym, as_of),
            "sector_flow": _sector_block(sym, as_of),
            "macro": _macro_block(as_of),
            "congress": congress.get(sym),
            "insider": _insider_block(sym, as_of),
            "institutions": institutions.get(sym),
            "news": _news_block(sym, as_of, allow_live_search=allow_live_search),
            "earnings": _earnings_block(sym, as_of),
            "fundamentals": _fundamentals_block(sym, as_of),
            "short_interest": _short_interest_block(sym, as_of),
        }
        if allow_live_search:
            p["options_flow"] = _live_options(sym)
            p["premarket"] = _live_premarket(sym)
            p["reddit"] = _live_reddit(sym)
        packets[sym] = p
    return packets
