#!/usr/bin/env python3
"""Trading Analysis Platform — CLI entry point.

Usage:
    python main.py AAPL              Analyze a stock
    python main.py AAPL TSLA MSFT    Analyze multiple stocks
    python main.py --scan            Scan all watchlist stocks
    python main.py --schedule        Start scheduler daemon
    python main.py --add AAPL TSLA   Add stocks to watchlist
    python main.py --watchlist       Show watchlist
    python main.py --alerts          Show recent alerts
    python main.py --server          Start FastAPI server
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Trading Stock Analysis Platform")
    parser.add_argument("symbols", nargs="*", help="Stock ticker(s) to analyze")
    parser.add_argument("--server", action="store_true", help="Start FastAPI server")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--no-export", action="store_true", help="Skip HTML/JSON export")
    parser.add_argument("--pdf", action="store_true", help="Also generate PDF report")
    parser.add_argument("--scan", action="store_true", help="Scan all watchlist stocks")
    parser.add_argument("--schedule", action="store_true", help="Start scheduler daemon")
    parser.add_argument("--schedule-hours", type=int, default=24, help="Hours between scans (default: 24)")
    parser.add_argument("--add", nargs="+", metavar="SYMBOL", help="Add stock(s) to watchlist")
    parser.add_argument("--remove", nargs="+", metavar="SYMBOL", help="Remove stock(s) from watchlist")
    parser.add_argument("--watchlist", action="store_true", help="Show current watchlist")
    parser.add_argument("--alerts", action="store_true", help="Show recent alerts")
    args = parser.parse_args()

    from src.utils.db import init_db
    init_db()

    if args.server:
        _run_server(args.port)
        return

    if args.add:
        _add_to_watchlist(args.add)
        return

    if args.remove:
        _remove_from_watchlist(args.remove)
        return

    if args.watchlist:
        _show_watchlist()
        return

    if args.alerts:
        _show_alerts()
        return

    if args.scan:
        from src.scheduler import run_watchlist_scan
        run_watchlist_scan(pdf=args.pdf)
        return

    if args.schedule:
        from src.scheduler import start_scheduler
        start_scheduler(schedule_hours=args.schedule_hours, pdf=args.pdf)
        return

    if not args.symbols:
        parser.print_help()
        print("\nExamples:")
        print("  python main.py AAPL              Analyze Apple")
        print("  python main.py AAPL TSLA         Analyze multiple stocks")
        print("  python main.py --add AAPL TSLA   Add to watchlist")
        print("  python main.py --scan            Scan watchlist")
        print("  python main.py --schedule        Auto-scan daily")
        print("  python main.py --alerts          Show alerts")
        print("  python main.py --server          Start API server")
        return

    from src.orchestrator import analyze_stock

    for symbol in args.symbols:
        print(f"\n{'='*60}")
        print(f"  Analyzing {symbol.upper()}")
        print(f"{'='*60}\n")

        try:
            report = analyze_stock(symbol, export=not args.no_export, pdf=args.pdf)
            _print_summary(report)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    print(f"\n{'='*60}")
    print("  Done.")
    print(f"{'='*60}")


def _print_summary(report) -> None:
    print(f"\n  Verdict:    {report.verdict.value}")
    print(f"  Confidence: {report.confidence}")
    print(f"  Risk:       {report.risk_rating.value}/5")
    print(f"  Price:      ${report.current_price}")
    print(f"  Sentiment:  {report.sentiment_score}")

    print(f"\n  Reasoning:")
    for r in report.reasoning:
        print(f"    - {r}")

    if report.risks:
        print(f"\n  Risks:")
        for r in report.risks:
            print(f"    ! {r}")

    print(f"\n  Sections: {', '.join(s.title for s in report.sections)}")
    print(f"\n  {report.DISCLAIMER}")


def _add_to_watchlist(symbols: list[str]) -> None:
    from src.utils.db import add_watchlist_item
    for s in symbols:
        add_watchlist_item(s.upper())
        print(f"  Added {s.upper()} to watchlist")


def _remove_from_watchlist(symbols: list[str]) -> None:
    from src.utils.db import remove_watchlist_item
    for s in symbols:
        remove_watchlist_item(s.upper())
        print(f"  Removed {s.upper()} from watchlist")


def _show_watchlist() -> None:
    from src.utils.db import get_watchlist
    watchlist = get_watchlist()
    if not watchlist:
        print("  Watchlist is empty. Add stocks: python main.py --add AAPL TSLA")
        return
    print(f"\n  Watchlist ({len(watchlist)} stocks):")
    for item in watchlist:
        print(f"    {item['symbol']}  (added {item['added_at'][:10]})")


def _show_alerts() -> None:
    from src.utils.db import get_alerts
    alerts = get_alerts(limit=20)
    if not alerts:
        print("  No alerts yet. Run a scan: python main.py --scan")
        return
    print(f"\n  Recent Alerts ({len(alerts)}):")
    for a in alerts:
        icon = "!!!" if a["severity"] == "critical" else " ! " if a["severity"] == "warning" else "   "
        print(f"    [{icon}] {a['symbol']} | {a['alert_type']} | {a['message']} ({a['created_at'][:16]})")


def _run_server(port: int) -> None:
    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn not installed. Run: pip install uvicorn")
        sys.exit(1)

    print(f"Starting Trading Analysis API on http://localhost:{port}")
    print(f"  POST /analyze/AAPL  — Analyze a stock")
    print(f"  GET  /reports       — List reports")
    print(f"  GET  /watchlist     — View watchlist")
    print(f"  GET  /alerts        — View alerts")
    print(f"  GET  /health        — Health check")
    print()
    uvicorn.run("src.app:app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    main()
