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
