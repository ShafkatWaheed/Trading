"""Backtest service: single signal, all-signals, multi-stock."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from src.analysis.backtester import (
    SIGNALS, SIGNAL_CATEGORIES, backtest_signal, backtest_all_signals,
)
from src.data.gateway import DataGateway
from api.constants import PERIOD_DAYS as _PERIOD_DAYS


def _trade_to_dict(t) -> dict:
    return {
        "entry_date": str(getattr(t, "entry_date", "")),
        "entry_price": float(getattr(t, "entry_price", 0)),
        "exit_date": str(getattr(t, "exit_date", "")),
        "exit_price": float(getattr(t, "exit_price", 0)),
        "pnl_percent": float(getattr(t, "pnl_percent", 0)),
        "hold_days": int(getattr(t, "hold_days", 0)),
        "outcome": str(getattr(t, "outcome", "loss")),
    }


def _result_to_dict(r) -> dict:
    return {
        "signal_name": r.signal_name,
        "description": SIGNALS.get(r.signal_name, {}).get("description", ""),
        "category": SIGNALS.get(r.signal_name, {}).get("category", ""),
        "direction": SIGNALS.get(r.signal_name, {}).get("direction", "buy"),
        "win_rate": float(getattr(r, "win_rate", 0) or 0),
        "avg_return": float(getattr(r, "avg_return", 0) or 0),
        "total_trades": int(getattr(r, "total_trades", 0) or 0),
        "max_gain": float(getattr(r, "max_gain", 0) or 0),
        "max_loss": float(getattr(r, "max_loss", 0) or 0),
        "grade": str(getattr(r, "grade", "")),
        "trades": [_trade_to_dict(t) for t in (getattr(r, "trades", []) or [])],
    }


def list_signals() -> dict:
    """Return the SIGNALS catalog and category groupings."""
    catalog = []
    for name, meta in SIGNALS.items():
        catalog.append({
            "name": name,
            "label": name.replace("_", " ").title(),
            "description": meta.get("description", ""),
            "direction": meta.get("direction", "buy"),
            "category": meta.get("category", ""),
        })
    return {
        "signals": catalog,
        "categories": list(SIGNAL_CATEGORIES.keys()),
        "category_signals": {k: list(v) for k, v in SIGNAL_CATEGORIES.items()},
    }


def _resolve_hist(symbol: str, hold_days: int):
    gw = DataGateway()
    return gw.get_historical(symbol, period_days=max(365, hold_days * 5))


def run_all_signals(symbol: str, period: str = "1M", category: str = "All Signals") -> dict:
    """Backtest every signal on one stock. Returns results sorted by win-rate × avg_return."""
    period = period if period in _PERIOD_DAYS else "1M"
    hold_days = _PERIOD_DAYS[period]
    symbol = symbol.upper()

    hist = _resolve_hist(symbol, hold_days)
    if hist is None or hist.empty or len(hist) < 60:
        return {
            "symbol": symbol, "period": period, "hold_days": hold_days,
            "results": [], "error": "Not enough historical data",
            "category": category,
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }

    results = backtest_all_signals(symbol, hist, hold_days)
    results = [r for r in results if r.total_trades > 0]

    if category and category != "All Signals":
        allowed = set(SIGNAL_CATEGORIES.get(category, []))
        results = [r for r in results if r.signal_name in allowed]

    rows = [_result_to_dict(r) for r in results]
    # Default sort: expected value (win_rate * avg_return)
    rows.sort(key=lambda r: r["win_rate"] * r["avg_return"], reverse=True)

    return {
        "symbol": symbol,
        "period": period,
        "hold_days": hold_days,
        "category": category,
        "results": rows,
        "available_periods": list(_PERIOD_DAYS.keys()),
        "available_categories": list(SIGNAL_CATEGORIES.keys()),
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }


def run_single(symbol: str, signal: str, period: str = "1M") -> dict:
    """Backtest one signal on one stock — returns full trade list + price history for charting."""
    period = period if period in _PERIOD_DAYS else "1M"
    hold_days = _PERIOD_DAYS[period]
    symbol = symbol.upper()

    hist = _resolve_hist(symbol, hold_days)
    if hist is None or hist.empty or len(hist) < 60:
        return {"symbol": symbol, "signal": signal, "period": period, "hold_days": hold_days,
                "result": None, "candles": [], "error": "Not enough historical data"}

    result = backtest_signal(symbol, hist, signal, hold_days)

    # Trim history to last ~365 trading days for chart
    trim = min(252, len(hist))
    sub = hist.tail(trim)
    candles = [
        {
            "date": str(d),
            "open": float(o), "high": float(h), "low": float(l), "close": float(c),
            "volume": float(v),
        }
        for d, o, h, l, c, v in zip(
            sub["date"].tolist(),
            sub["open"].astype(float).tolist(),
            sub["high"].astype(float).tolist(),
            sub["low"].astype(float).tolist(),
            sub["close"].astype(float).tolist(),
            sub["volume"].astype(float).tolist(),
        )
    ]

    return {
        "symbol": symbol,
        "signal": signal,
        "signal_label": signal.replace("_", " ").title(),
        "signal_description": SIGNALS.get(signal, {}).get("description", ""),
        "period": period,
        "hold_days": hold_days,
        "result": _result_to_dict(result),
        "candles": candles,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }


def run_multi_stock(symbols: list[str], signal: str, period: str = "1M") -> dict:
    """Backtest one signal across multiple stocks (parallel)."""
    period = period if period in _PERIOD_DAYS else "1M"
    hold_days = _PERIOD_DAYS[period]
    syms = list(dict.fromkeys([s.upper().strip() for s in symbols if s.strip()]))[:8]

    if not syms:
        return {"signal": signal, "period": period, "hold_days": hold_days, "rows": []}

    def _one(sym: str) -> dict:
        try:
            hist = _resolve_hist(sym, hold_days)
            if hist is None or hist.empty or len(hist) < 60:
                return {"symbol": sym, "error": "Not enough data"}
            r = backtest_signal(sym, hist, signal, hold_days)
            return {"symbol": sym, **{k: v for k, v in _result_to_dict(r).items() if k != "trades"}}
        except Exception as e:
            return {"symbol": sym, "error": str(e)}

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(8, len(syms))) as pool:
        futures = {pool.submit(_one, s): s for s in syms}
        for f in futures:
            try:
                rows.append(f.result(timeout=120))
            except Exception as e:
                rows.append({"symbol": futures[f], "error": str(e)})

    order = {s: i for i, s in enumerate(syms)}
    rows.sort(key=lambda r: order.get(r["symbol"], 999))

    return {
        "signal": signal,
        "signal_label": signal.replace("_", " ").title(),
        "signal_description": SIGNALS.get(signal, {}).get("description", ""),
        "period": period,
        "hold_days": hold_days,
        "rows": rows,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }


# Keep old single-trade signature for legacy /backtest endpoint
def run_signal_backtest(symbol: str, signal: str, hold_days: int = 20) -> dict:
    period = "1M"
    for k, v in _PERIOD_DAYS.items():
        if v == hold_days:
            period = k
            break
    out = run_single(symbol, signal, period=period)
    r = out.get("result") or {}
    return {
        "symbol": out["symbol"],
        "signal": out["signal"],
        "win_rate": r.get("win_rate", 0),
        "avg_return": r.get("avg_return", 0),
        "total_trades": r.get("total_trades", 0),
        "trades": [
            {
                "entry_date": t["entry_date"],
                "entry_price": t["entry_price"],
                "exit_date": t["exit_date"],
                "exit_price": t["exit_price"],
                "return_pct": t["pnl_percent"],
            }
            for t in (r.get("trades") or [])
        ],
    }
