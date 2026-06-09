"""FastAPI entry point.

Run with:  uvicorn api.main:app --port 8000 --reload
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import HealthResponse
from api.routes import (
    market, discover, stocks, backtest, agent, watchlist, compare, alerts, simulation,
    data_sources, universe, news_impact, graph, freshness, earnings, graph_relevance,
    refresh, track_record, context_search, brief, daily_picks, journal, flows,
    predictions,
)

app = FastAPI(
    title="Trading Analysis API",
    version="0.1.0",
    description="Stock research and analysis. Backend for the Next.js frontend.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _start_schedulers() -> None:
    """Kick off daemon-thread schedulers. Idempotent across reloads.

    `earnings_prewarm` runs daily at 6:30am ET — refreshes the 7d calendar
    and warms `pre_earnings_setup` for every company in it. By the time the
    market opens (9:30 ET) the calendar shows verdicts for every report.
    """
    try:
        from api.services._scheduler import schedule_daily_at
        from api.services.earnings_week_service import daily_prewarm
        schedule_daily_at(6, 30, daily_prewarm, name="earnings_prewarm")
    except Exception as e:
        # Never fail startup on scheduler error — the lazy prewarm path in
        # earnings_week_service still kicks in on first request.
        import logging
        logging.getLogger(__name__).warning("scheduler startup failed: %r", e)

    # Congressional trades refresh (House + Senate) — nightly at 6:00 ET so
    # /flows + congress_signal serve fresh data. Source is Quiver Quantitative:
    # the House Clerk PDFs and Senate eFD portal (Akamai) plus Capitol Trades
    # (CloudFront) were all unreliable / IP-blocked, so one Quiver job covers
    # both chambers into the unified congress_trades table.
    try:
        from api.services._scheduler import schedule_daily_at
        from src.data.quiver_congress import refresh as _refresh_congress

        def _refresh_congress_trades():
            try:
                _refresh_congress()
            except Exception:
                pass

        schedule_daily_at(6, 0, _refresh_congress_trades, name="congress_refresh")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("congress refresh scheduler failed: %r", e)

    # Opportunity-score precompute — nightly at 5:30 ET so discover_service and
    # daily_picks have a fresh scored universe (precomputed_scores). Without this
    # the universe goes stale after 24h and the Daily Picks page empties out
    # (the grounded agents have no candidates to screen).
    try:
        from api.services._scheduler import schedule_daily_at
        from src.scheduler import refresh_scores as _refresh_scores, _tier_ab_symbols

        def _refresh_opportunity_scores():
            try:
                _refresh_scores(symbols=_tier_ab_symbols())
            except Exception:
                pass
            # Pre-warm the daily-picks payload (incl. option contracts) right
            # after scoring, so the first morning load is served from cache
            # instead of a ~3-minute cold regeneration.
            try:
                from api.services import daily_picks_service
                daily_picks_service.get_daily_picks(force=True)
            except Exception:
                pass

        schedule_daily_at(5, 30, _refresh_opportunity_scores, name="opportunity_scores_refresh")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("opportunity scores scheduler failed: %r", e)

    # Daily top-10 predictions — generate pre-open at 6:30 ET, record actuals
    # after market close at 16:15 ET. Both calls degrade gracefully on
    # failure (the routes can lazy-generate on first request).
    try:
        from datetime import datetime, timezone
        from api.services._scheduler import schedule_daily_at
        from api.services import predictions_service

        def _generate_predictions_today():
            try:
                today = datetime.now(tz=timezone.utc).date().isoformat()
                predictions_service.generate_predictions_for_date(today)
            except Exception:
                pass

        def _record_predictions_actuals():
            try:
                today = datetime.now(tz=timezone.utc).date().isoformat()
                predictions_service.record_actuals_for_date(today)
            except Exception:
                pass

        schedule_daily_at(6, 30, _generate_predictions_today, name="predictions_generate")
        schedule_daily_at(16, 15, _record_predictions_actuals, name="predictions_actuals")

        # Weekly Claude strategy review at Sunday 7am ET. The cron helper
        # only supports daily — we wrap it and short-circuit on non-Sundays.
        # Proposal is saved as deactivated; user activates via the UI.
        def _weekly_strategy_review():
            try:
                if datetime.now().weekday() != 6:    # 6 = Sunday
                    return
                predictions_service.review_and_propose_strategy(window_days=14)
            except Exception:
                pass

        schedule_daily_at(7, 0, _weekly_strategy_review, name="predictions_strategy_review")

        # Weekly playbook (skills.md) update at Sunday 7:30 ET. Runs AFTER
        # the strategy review so the new proposal can land in the playbook
        # context when Claude does its next weekly pass.
        def _weekly_skills_update():
            try:
                if datetime.now().weekday() != 6:    # 6 = Sunday
                    return
                predictions_service.update_prediction_skills(window_days=30)
            except Exception:
                pass

        schedule_daily_at(7, 30, _weekly_skills_update, name="predictions_skills_update")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("predictions scheduler failed: %r", e)

    # Startup self-heal — an out-of-hours restart misses the 5:30 ET scoring job,
    # leaving the universe stale and daily-picks empty. If scores are stale at
    # boot, score Tier A+B once in a daemon thread (non-blocking — startup must
    # not wait on the ~minutes-long scoring run).
    try:
        import logging
        import threading
        from src.scheduler import (
            refresh_scores as _refresh_scores,
            _tier_ab_symbols,
            scores_need_refresh,
        )

        if scores_need_refresh():
            def _startup_score_selfheal():
                try:
                    _refresh_scores(symbols=_tier_ab_symbols())
                except Exception:
                    pass
                # Warm daily-picks too, so the page is ready right after an
                # out-of-hours restart, not on the user's first (cold) load.
                try:
                    from api.services import daily_picks_service
                    daily_picks_service.get_daily_picks(force=True)
                except Exception:
                    pass

            threading.Thread(
                target=_startup_score_selfheal,
                name="startup_score_selfheal",
                daemon=True,
            ).start()
            logging.getLogger(__name__).info(
                "startup self-heal: scores stale, scoring Tier A+B in background"
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("startup score self-heal failed: %r", e)

app.include_router(market.router)
app.include_router(discover.router)
app.include_router(stocks.router)
app.include_router(backtest.router)
app.include_router(agent.router)
app.include_router(watchlist.router)
app.include_router(compare.router)
app.include_router(alerts.router)
app.include_router(simulation.router)
app.include_router(data_sources.router)
app.include_router(universe.router)
app.include_router(news_impact.router)
app.include_router(graph.router)
app.include_router(freshness.router)
app.include_router(earnings.router)
app.include_router(graph_relevance.router)
app.include_router(refresh.router)
app.include_router(track_record.router)
app.include_router(context_search.router)
app.include_router(brief.router)
app.include_router(daily_picks.router)
app.include_router(journal.router)
app.include_router(flows.router)
app.include_router(predictions.router)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> dict:
    return {"status": "ok", "service": "trading-api", "version": "0.1.0"}


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "Trading Analysis API",
        "docs": "/docs",
        "health": "/health",
    }
