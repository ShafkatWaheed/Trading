"""Scheduled watchlist scanning with alert detection."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from src.orchestrator import analyze_stock
from src.alerts import detect_alerts
from src.utils.db import init_db, get_watchlist, get_alerts
from src.reports.exporter import export_json


def run_watchlist_scan(pdf: bool = False) -> dict:
    """Scan all watchlist stocks, generate reports, detect alerts.

    Returns summary dict with results per symbol and alerts.
    """
    init_db()
    watchlist = get_watchlist()

    if not watchlist:
        print("  Watchlist is empty. Add stocks with: python main.py --add AAPL")
        return {"scanned": 0, "alerts": []}

    print(f"\n  Scanning {len(watchlist)} stocks...")
    print(f"  Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")

    results: list[dict] = []
    all_alerts: list[dict] = []

    def _scan_one(item: dict) -> tuple[dict, list]:
        """Scan a single symbol and return (result_row, alert_list)."""
        symbol = item["symbol"]
        try:
            report = analyze_stock(symbol, export=True, pdf=pdf)

            # Serialize report for alert comparison
            report_json = json.dumps({
                "verdict": report.verdict.value,
                "confidence": report.confidence,
                "risk_rating": report.risk_rating.value,
                "sentiment_score": str(report.sentiment_score),
                "sections": [
                    {"title": s.title, "content": s.content, "data": s.data}
                    for s in report.sections
                ],
            }, default=str)

            alerts = detect_alerts(symbol, report_json)

            row = {
                "symbol": symbol,
                "verdict": report.verdict.value,
                "confidence": report.confidence,
                "risk": report.risk_rating.value,
                "alerts": len(alerts),
            }
            alert_str = f" | {len(alerts)} alert(s)" if alerts else ""
            print(f"  ✓ {symbol}: {report.verdict.value} (confidence: {report.confidence}){alert_str}", flush=True)

            return row, [
                {
                    "symbol": a.symbol,
                    "type": a.alert_type,
                    "message": a.message,
                    "severity": a.severity,
                }
                for a in alerts
            ]
        except Exception as e:
            print(f"  ✗ {symbol}: ERROR {e}", flush=True)
            return {"symbol": symbol, "verdict": "ERROR", "error": str(e)}, []

    # Scan up to 4 stocks in parallel (I/O-bound work, no CPU contention)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_scan_one, item) for item in watchlist]
        for future in as_completed(futures):
            row, alerts = future.result()
            results.append(row)
            all_alerts.extend(alerts)

    # Print summary
    _print_scan_summary(results, all_alerts)

    # Save alerts summary
    if all_alerts:
        _save_alerts_json(all_alerts)

    return {"scanned": len(results), "results": results, "alerts": all_alerts}


def start_scheduler(schedule_hours: int = 24, pdf: bool = False) -> None:
    """Start APScheduler to run watchlist scans on interval."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        print("ERROR: APScheduler not installed. Run: pip install apscheduler")
        return

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_watchlist_scan,
        trigger=IntervalTrigger(hours=schedule_hours),
        kwargs={"pdf": pdf},
        id="watchlist_scan",
        name="Watchlist Scanner",
        next_run_time=datetime.utcnow(),  # Run immediately on start
    )

    print(f"\n  Scheduler started — scanning every {schedule_hours} hours")
    print(f"  Press Ctrl+C to stop\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n  Scheduler stopped.")
        scheduler.shutdown()


def run_agent_cycle() -> dict:
    """Run one AI agent trading cycle. Called by scheduler."""
    from src.agent import TradingAgent
    init_db()
    try:
        agent = TradingAgent()
        result = agent.run_cycle()
        print(f"  Agent cycle complete: {result.get('trades_executed', 0)} trades, portfolio ${result.get('portfolio_value', 0):,.0f}")
        return result
    except Exception as e:
        print(f"  Agent cycle error: {e}")
        return {"error": str(e)}


def _configure_agent_job(scheduler) -> tuple[str, int] | None:
    """Read agent_config and attach the agent_cycle job to `scheduler`.

    Returns (frequency_label, hours) when a job was scheduled, None when the
    config is missing or set to "manual" (no-op).
    """
    try:
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        print("APScheduler not installed")
        return None

    from src.utils.db import get_connection

    conn = get_connection()
    row = conn.execute("SELECT rebalance_frequency, last_run FROM agent_config WHERE id=1").fetchone()
    conn.close()

    if not row:
        return None

    freq = row["rebalance_frequency"] or "manual"
    if freq == "manual":
        return None

    interval_map = {"daily": 24, "weekly": 168, "monthly": 720}
    hours = interval_map.get(freq, 168)

    # If the last run is older than `hours`, fire immediately on startup.
    last_run = row["last_run"]
    run_now = True
    if last_run:
        try:
            from datetime import datetime as dt, timedelta
            last_dt = dt.strptime(last_run[:16], "%Y-%m-%d %H:%M")
            run_now = dt.utcnow() > last_dt + timedelta(hours=hours)
        except Exception:
            run_now = True

    scheduler.add_job(
        run_agent_cycle,
        trigger=IntervalTrigger(hours=hours),
        id="agent_cycle",
        name=f"AI Agent ({freq})",
        next_run_time=datetime.utcnow() if run_now else None,
        replace_existing=True,
    )
    return freq, hours


def start_agent_scheduler() -> None:
    """Background agent scheduler — embed in a host process (returns immediately)."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        print("APScheduler not installed")
        return

    scheduler = BackgroundScheduler()
    info = _configure_agent_job(scheduler)
    if info is None:
        return
    freq, hours = info
    scheduler.start()
    print(f"  Agent scheduler started — running {freq} (every {hours}h)")


def run_agent_scheduler() -> None:
    """Blocking agent scheduler — owns the process. Run as a standalone worker.

    Usage: python -m src.scheduler agent
    """
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        print("ERROR: APScheduler not installed. Run: pip install apscheduler")
        return

    scheduler = BlockingScheduler()
    info = _configure_agent_job(scheduler)
    if info is None:
        print("Agent scheduler not started — agent_config.rebalance_frequency is 'manual' or missing.")
        print("Set it to 'daily' / 'weekly' / 'monthly' via the API or DB to enable automated cycles.")
        return
    freq, hours = info

    print(f"\n  Agent scheduler started — running {freq} (every {hours}h)")
    print("  Press Ctrl+C to stop\n")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n  Agent scheduler stopped.")
        scheduler.shutdown()


def _print_scan_summary(results: list[dict], alerts: list[dict]) -> None:
    print(f"\n{'='*60}")
    print(f"  SCAN COMPLETE — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")
    print(f"\n  Stocks scanned: {len(results)}")

    # Verdict summary
    verdicts = {}
    for r in results:
        v = r.get("verdict", "ERROR")
        verdicts[v] = verdicts.get(v, 0) + 1
    for v, count in sorted(verdicts.items()):
        print(f"    {v}: {count}")

    # Alerts
    if alerts:
        print(f"\n  ALERTS ({len(alerts)}):")
        for a in alerts:
            icon = "!!!" if a["severity"] == "critical" else "!" if a["severity"] == "warning" else " "
            print(f"    [{icon}] {a['symbol']}: {a['message']}")
    else:
        print(f"\n  No alerts — all verdicts unchanged.")

    print(f"\n{'='*60}")


def _save_alerts_json(alerts: list[dict]) -> None:
    from pathlib import Path
    output_dir = Path("reports")
    output_dir.mkdir(exist_ok=True)
    filename = f"alerts_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    path = output_dir / filename
    path.write_text(json.dumps(alerts, indent=2))
    print(f"  Alerts saved: {path}")


# ──────────────────────────────────────────────────────────────────
# Phase 3: Pre-fetch jobs — keep cache warm so users see fresh data
# without waiting for synchronous fetches on page load.
# ──────────────────────────────────────────────────────────────────


def _all_target_symbols() -> list[str]:
    """Watchlist symbols + STOCK_DB symbols (deduplicated)."""
    from src.data.stock_db import STOCK_DB

    init_db()
    syms = {item["symbol"] for item in get_watchlist()}
    syms.update(STOCK_DB.keys())
    return sorted(syms)


def _fan_out(fn, symbols: list[str], max_workers: int = 6, label: str = "") -> None:
    """Run fn(symbol) for each symbol in parallel; log results."""
    ok, fail = 0, 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fn, s): s for s in symbols}
        for fut in as_completed(futures):
            try:
                fut.result()
                ok += 1
            except Exception:
                fail += 1
    if label:
        print(f"  [{label}] ok={ok} fail={fail} ({len(symbols)} symbols)")


def refresh_prices() -> None:
    """Re-cache historical prices for all target symbols. Runs every 15 min during market hours."""
    from src.data.gateway import DataGateway

    def _one(sym: str) -> None:
        gw = DataGateway()
        gw.get_historical(sym, period_days=252)

    _fan_out(_one, _all_target_symbols(), max_workers=6, label="prices")


def refresh_fundamentals() -> None:
    """Re-cache fundamentals (P/E, EPS, growth) for all target symbols. Daily 4:30 PM ET."""
    from src.data.gateway import DataGateway

    def _one(sym: str) -> None:
        gw = DataGateway()
        gw.get_fundamentals(sym)

    _fan_out(_one, _all_target_symbols(), max_workers=4, label="fundamentals")


def refresh_macro() -> None:
    """Re-cache macro snapshot (Fed rates, CPI, VIX, GDP). Daily 7 AM ET."""
    from src.data.gateway import DataGateway
    try:
        gw = DataGateway()
        gw.get_macro_snapshot()
        print("  [macro] refreshed")
    except Exception as e:
        print(f"  [macro] error: {e}")


def refresh_insider() -> None:
    """Re-cache SEC Form 4, 13F, congressional trades. Every 6 hours."""
    from src.data.gateway import DataGateway

    def _one(sym: str) -> None:
        gw = DataGateway()
        try:
            gw.get_insider_summary(sym)
        except Exception:
            pass
        try:
            gw.get_institutional_summary(sym)
        except Exception:
            pass
        try:
            gw.get_congress_summary(sym)
        except Exception:
            pass

    _fan_out(_one, _all_target_symbols(), max_workers=4, label="insider")


def refresh_news() -> None:
    """Re-cache stock news + sentiment. Hourly during market hours."""
    from src.data.gateway import DataGateway

    def _one(sym: str) -> None:
        gw = DataGateway()
        gw.get_stock_news(sym)

    _fan_out(_one, _all_target_symbols(), max_workers=4, label="news")


def refresh_options() -> None:
    """Re-cache options flow + unusual activity. Every 30 min during market hours."""
    from src.data.gateway import DataGateway

    def _one(sym: str) -> None:
        gw = DataGateway()
        try:
            gw.get_options_summary(sym)
        except Exception:
            pass

    _fan_out(_one, _all_target_symbols(), max_workers=4, label="options")


def refresh_scores() -> None:
    """Pre-compute opportunity scores → write to precomputed_scores table. Daily 5 PM ET."""
    from src.analysis import technical
    from src.analysis.opportunity import compute_opportunity
    from src.data.gateway import DataGateway
    from src.utils.db import save_precomputed_score

    def _one(sym: str) -> None:
        gw = DataGateway()
        hist = gw.get_historical(sym, period_days=252)
        if hist is None or hist.empty:
            return
        tech = technical.analyze(sym, hist)
        score = compute_opportunity(sym, tech)
        save_precomputed_score(sym, {
            "total_score": score.total_score,
            "volume_score": score.volume_score,
            "price_score": score.price_score,
            "flow_score": score.flow_score,
            "risk_reward_score": score.risk_reward_score,
            "risk_reward_ratio": score.risk_reward_ratio,
            "strategy": score.strategy,
            "secondary_strategies": score.secondary_strategies,
            "label": score.label,
        })

    _fan_out(_one, _all_target_symbols(), max_workers=4, label="scores")


def cleanup_old_cache() -> None:
    """Delete expired cache rows. Runs Sunday 3 AM."""
    from src.utils.db import get_connection
    conn = get_connection()
    try:
        before = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        conn.execute("DELETE FROM cache WHERE expires_at < datetime('now')")
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        print(f"  [cleanup] removed {before - after} expired rows ({after} remaining)")
    finally:
        conn.close()


def evaluate_ai_decisions() -> None:
    """Grade pending AI decisions against current prices. Runs daily after market close."""
    try:
        from api.services import decisions_outcome_service
        result = decisions_outcome_service.evaluate_pending_decisions()
        print(
            f"  [ai-evaluator] candidates={result['candidates']} "
            f"evaluated={result['evaluated']} correct={result['correct']} "
            f"pending={result['skipped_pending']} no_price={result['skipped_no_price']}"
        )
    except Exception as e:
        print(f"  [ai-evaluator] ERROR: {e}")


def start_prefetch_scheduler() -> None:
    """Boot a BlockingScheduler with all pre-fetch jobs. Run as separate process.

    Usage: python -m src.scheduler  (entry point picks this up)
    """
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        print("ERROR: APScheduler not installed. Run: pip install apscheduler")
        return

    scheduler = BlockingScheduler(timezone="America/New_York")

    # Market-hours intra-day jobs (Mon-Fri, 9:30 AM - 4:00 PM ET)
    scheduler.add_job(
        refresh_prices,
        trigger=CronTrigger(day_of_week="mon-fri", hour="9-15", minute="*/15"),
        id="refresh_prices", name="Refresh Prices (every 15min)",
    )
    scheduler.add_job(
        refresh_news,
        trigger=CronTrigger(day_of_week="mon-fri", hour="9-15", minute=0),
        id="refresh_news", name="Refresh News (hourly)",
    )
    scheduler.add_job(
        refresh_options,
        trigger=CronTrigger(day_of_week="mon-fri", hour="9-15", minute="0,30"),
        id="refresh_options", name="Refresh Options (every 30min)",
    )

    # Daily jobs
    scheduler.add_job(
        refresh_macro,
        trigger=CronTrigger(hour=7, minute=0),
        id="refresh_macro", name="Refresh Macro (daily 7 AM ET)",
    )
    scheduler.add_job(
        refresh_fundamentals,
        trigger=CronTrigger(day_of_week="mon-fri", hour=16, minute=30),
        id="refresh_fundamentals", name="Refresh Fundamentals (daily 4:30 PM ET)",
    )
    scheduler.add_job(
        refresh_scores,
        trigger=CronTrigger(day_of_week="mon-fri", hour=17, minute=0),
        id="refresh_scores", name="Pre-compute Scores (daily 5 PM ET)",
    )

    # Multi-times-per-day jobs
    scheduler.add_job(
        refresh_insider,
        trigger=IntervalTrigger(hours=6),
        id="refresh_insider", name="Refresh Insider/Congress (every 6h)",
    )

    # Weekly cleanup
    scheduler.add_job(
        cleanup_old_cache,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="cleanup_cache", name="Cleanup Expired Cache (Sunday 3 AM)",
    )

    # Grade pending AI decisions whose prediction window has passed.
    # Runs after market close so price_at_call → price_now uses post-session settle.
    scheduler.add_job(
        evaluate_ai_decisions,
        trigger=CronTrigger(day_of_week="mon-fri", hour=17, minute=15),
        id="evaluate_ai_decisions", name="AI Decisions Outcome Evaluator (daily 5:15 PM ET)",
    )

    print("\n  Pre-fetch scheduler started — 8 jobs registered:")
    for job in scheduler.get_jobs():
        print(f"    • {job.name}")
    print("\n  Press Ctrl+C to stop\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n  Pre-fetch scheduler stopped.")
        scheduler.shutdown()


if __name__ == "__main__":
    # Entry point: python -m src.scheduler [prefetch|agent]
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "prefetch"
    if cmd == "prefetch":
        start_prefetch_scheduler()
    elif cmd == "agent":
        run_agent_scheduler()
    else:
        sys.exit(f"unknown command: {cmd!r}. Use 'prefetch' (default) or 'agent'.")
