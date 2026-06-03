"""Market-wide earnings calendar for the next N days.

Pulls the full earnings calendar from Finnhub, filters to symbols in
`stocks_universe`, enriches with sector + (optionally cached) pre-earnings
setup verdict, and groups by date.

Cached 30 min — calendar refreshes within the day as companies confirm
report timing (BMO/AMC).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import logging

from src.utils.db import cache_get, cache_set, get_connection

logger = logging.getLogger(__name__)

_CACHE_TTL_MINUTES = 30
_VALID_WINDOWS = (3, 7, 14)


def _weekday(d: str) -> str:
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%a")
    except Exception:
        return ""


def get_earnings_week(days: int = 7, *, force: bool = False) -> dict:
    """Market-wide earnings calendar for the next N days.

    Returns:
      {
        "days_window": int,
        "as_of": "YYYY-MM-DD",
        "by_day": [
          {
            "date": "YYYY-MM-DD",
            "weekday": "Mon",
            "count": int,
            "companies": [
              {
                "symbol": str,
                "name": str | None,
                "sector": str | None,
                "hour": "bmo" | "amc" | None,
                "eps_estimate": float | None,
                "revenue_estimate": float | None,
                "pre_earnings_verdict": str | None,
                "pre_earnings_score": float | None,
              }, ...
            ]
          }, ...
        ],
        "total_companies": int,
        "coverage_note": str,
      }
    """
    if days not in _VALID_WINDOWS:
        days = 7

    cache_key = f"earnings_week:v1:{days}"
    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    today = date.today()
    end_date = today + timedelta(days=days)

    try:
        from src.data.finnhub import get_earnings_calendar
        rows = get_earnings_calendar(days_ahead=days) or []
    except Exception as e:
        logger.warning("earnings-week: finnhub fetch failed %r", e)
        return _empty(days, note=f"Finnhub fetch failed: {e}")

    if not rows:
        return _empty(days, note="No earnings reported by Finnhub for this window")

    # Build universe + sector lookup
    conn = get_connection()
    try:
        universe = {
            r["symbol"]: {"name": r["name"]}
            for r in conn.execute("SELECT symbol, name FROM stocks_universe").fetchall()
        }
        sector_by_symbol = {}
        for r in conn.execute(
            """
            SELECT si.symbol, ind.sector
            FROM stock_industry si
            JOIN industries ind ON ind.code = si.industry_code
            WHERE si.is_primary = 1
            """
        ).fetchall():
            sector_by_symbol[r["symbol"]] = r["sector"]
    finally:
        conn.close()

    # Group by date — dedupe (symbol, date) since Finnhub may return multiple
    # listings per company (separate share classes, ADR, etc.) for the same
    # report date.
    by_day: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for r in rows:
        sym = (r.get("symbol") or "").upper().strip()
        if not sym or sym not in universe:
            continue
        d_str = r.get("date")
        if not d_str:
            continue
        try:
            d = datetime.strptime(d_str[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        if d < today or d > end_date:
            continue
        key = (sym, d.isoformat())
        if key in seen:
            continue
        seen.add(key)

        # Look up pre-earnings verdict if cached (don't trigger fresh compute
        # here — we'd be doing 50+ heavy fetches just to render a calendar).
        pes_cached = cache_get(f"pre_earnings_setup:v1:{sym}")
        pes_verdict = None
        pes_score = None
        if isinstance(pes_cached, dict):
            v = pes_cached.get("verdict")
            if v not in (None, "insufficient_data", "no_earnings_imminent"):
                pes_verdict = v
                pes_score = pes_cached.get("score")

        # Look up market cap from the bubble-score fundamentals cache (already
        # populated for any stock that's been deep-dived). Cache-only — we
        # don't fan out 76 yf.Ticker() fetches just to render the calendar.
        market_cap = None
        bs_cached = cache_get(f"bubble:fundamentals:v1:{sym}")
        if isinstance(bs_cached, dict):
            mc = bs_cached.get("market_cap")
            if mc is not None:
                try:
                    market_cap = float(mc)
                except (TypeError, ValueError):
                    market_cap = None

        by_day[d.isoformat()].append({
            "symbol": sym,
            "name": universe[sym].get("name"),
            "sector": sector_by_symbol.get(sym),
            "hour": (r.get("hour") or "").lower() or None,
            "eps_estimate": r.get("epsEstimate"),
            "revenue_estimate": r.get("revenueEstimate"),
            "market_cap": market_cap,
            "pre_earnings_verdict": pes_verdict,
            "pre_earnings_score": pes_score,
        })

    # Sort each day's companies: those with a verdict first (more interesting),
    # then by market cap desc (mega-caps first), then by sector, then alphabetical
    out_days = []
    total = 0
    for d_str in sorted(by_day.keys()):
        companies = by_day[d_str]
        companies.sort(key=lambda c: (
            0 if c.get("pre_earnings_verdict") else 1,
            -1 * (c.get("market_cap") or 0),
            c.get("sector") or "zzz",
            c["symbol"],
        ))
        out_days.append({
            "date": d_str,
            "weekday": _weekday(d_str),
            "count": len(companies),
            "companies": companies,
        })
        total += len(companies)

    payload = {
        "days_window": days,
        "as_of": today.isoformat(),
        "by_day": out_days,
        "total_companies": total,
        "coverage_note": (
            f"Filtered to {total} companies in the tracked universe over the next {days} days. "
            f"Pre-earnings verdicts only shown when the per-symbol setup is already cached."
        ),
        "from_cache": False,
    }
    if total > 0:
        try:
            cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_MINUTES)
        except Exception:
            pass

    # Background prewarm: if any companies are missing a cached pre-earnings
    # setup, kick a single dedup-keyed background job that computes them all.
    # Next request to /market/earnings-this-week sees a populated calendar.
    # Dedup key is per-window so multiple concurrent /earnings-week requests
    # don't spawn duplicate prewarm jobs.
    try:
        missing_syms = [
            c["symbol"] for d in out_days for c in d["companies"]
            if c.get("pre_earnings_verdict") is None
        ]
        if missing_syms:
            from api.services._background_jobs import kick
            kick(
                f"earnings_week_prewarm:v1:{days}",
                _prewarm_pre_earnings,
                missing_syms,
            )
    except Exception as e:
        logger.info("earnings-week: failed to kick prewarm: %r", e)

    return payload


def daily_prewarm() -> dict:
    """Refresh the 7d earnings calendar and prewarm pre-earnings setup for
    every company in it. Called by the daily scheduler (6:30am ET).

    Returns the prewarm summary stats so logs show what happened.
    """
    logger.info("daily prewarm: fetching fresh 7d earnings calendar")
    payload = get_earnings_week(days=7, force=True)
    symbols = [
        c["symbol"]
        for d in (payload.get("by_day") or [])
        for c in (d.get("companies") or [])
    ]
    logger.info("daily prewarm: %d symbols to warm", len(symbols))
    return _prewarm_pre_earnings(symbols)


def _prewarm_pre_earnings(symbols: list[str]) -> dict:
    """Background prewarm of `pre_earnings_setup_service.get_pre_earnings_setup`
    for every symbol in the list. Bounded concurrency to avoid hammering
    downstream APIs.

    Returns summary stats (processed/succeeded/failed/skipped). Called from
    a background thread via `_background_jobs.kick`, so the caller doesn't
    block on this.
    """
    from concurrent.futures import ThreadPoolExecutor
    from api.services import pre_earnings_setup_service

    processed = 0
    succeeded = 0
    failed = 0

    def _one(sym: str) -> bool:
        try:
            pre_earnings_setup_service.get_pre_earnings_setup(sym)
            return True
        except Exception as e:
            logger.info("earnings-week prewarm: %s failed %r", sym, e)
            return False

    # Modest concurrency: each task pulls earnings calendar, history, options,
    # estimate revisions, short interest, news — be polite to upstream APIs.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for ok in pool.map(_one, symbols):
            processed += 1
            if ok:
                succeeded += 1
            else:
                failed += 1

    logger.info(
        "earnings-week prewarm done: %d processed, %d succeeded, %d failed",
        processed, succeeded, failed,
    )

    # Invalidate the earnings_week cache so the next request rebuilds with the
    # newly-populated verdicts.
    try:
        from src.utils.db import get_connection
        conn = get_connection()
        try:
            conn.execute("DELETE FROM cache WHERE key LIKE 'earnings_week:v1:%'")
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass

    return {"processed": processed, "succeeded": succeeded, "failed": failed}


def _empty(days: int, *, note: str) -> dict:
    return {
        "days_window": days,
        "as_of": date.today().isoformat(),
        "by_day": [],
        "total_companies": 0,
        "coverage_note": note,
        "from_cache": False,
    }
