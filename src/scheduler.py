"""Scheduled watchlist scanning with alert detection."""

import json
import time
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

    for i, item in enumerate(watchlist):
        symbol = item["symbol"]
        print(f"  [{i+1}/{len(watchlist)}] {symbol}...", end=" ", flush=True)

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

            # Detect alerts by comparing with previous report
            alerts = detect_alerts(symbol, report_json)

            result = {
                "symbol": symbol,
                "verdict": report.verdict.value,
                "confidence": report.confidence,
                "risk": report.risk_rating.value,
                "alerts": len(alerts),
            }
            results.append(result)

            alert_str = f" | {len(alerts)} alert(s)" if alerts else ""
            print(f"{report.verdict.value} (confidence: {report.confidence}){alert_str}")

            for a in alerts:
                all_alerts.append({
                    "symbol": a.symbol,
                    "type": a.alert_type,
                    "message": a.message,
                    "severity": a.severity,
                })

        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"symbol": symbol, "verdict": "ERROR", "error": str(e)})

        # Rate limit: wait between stocks to avoid API throttling
        if i < len(watchlist) - 1:
            time.sleep(5)

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


def start_agent_scheduler() -> None:
    """Start background agent scheduler based on config frequency."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        print("APScheduler not installed")
        return

    from src.utils.db import get_connection

    # Read frequency from config
    conn = get_connection()
    row = conn.execute("SELECT rebalance_frequency, last_run FROM agent_config WHERE id=1").fetchone()
    conn.close()

    if not row:
        return

    freq = row["rebalance_frequency"] if row else "manual"
    if freq == "manual":
        return

    interval_map = {"daily": 24, "weekly": 168, "monthly": 720}
    hours = interval_map.get(freq, 168)

    # Check if overdue
    last_run = row["last_run"] if row else None
    run_now = False
    if last_run:
        try:
            from datetime import datetime as dt, timedelta
            last_dt = dt.strptime(last_run[:16], "%Y-%m-%d %H:%M")
            if dt.utcnow() > last_dt + timedelta(hours=hours):
                run_now = True
        except Exception:
            run_now = True
    else:
        run_now = True

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_agent_cycle,
        trigger=IntervalTrigger(hours=hours),
        id="agent_cycle",
        name=f"AI Agent ({freq})",
        next_run_time=datetime.utcnow() if run_now else None,
        replace_existing=True,
    )
    scheduler.start()
    print(f"  Agent scheduler started — running {freq} (every {hours}h)")


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
