"""Agent service: status, config, personalities, positions, equity, decisions, run."""
from __future__ import annotations

from datetime import datetime, timedelta
from src.utils.db import get_connection, init_db


# ── Status ───────────────────────────────────────────────────────


def get_status() -> dict:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, last_run, rebalance_frequency, starting_capital "
            "FROM agent_config WHERE id=1"
        ).fetchone()
        if not row:
            return {
                "enabled": False, "last_run": None, "portfolio_value": 0.0,
                "open_positions": 0, "rebalance_frequency": "manual",
                "next_run": None, "overdue": False,
            }

        eq_row = conn.execute(
            "SELECT total_value FROM agent_equity ORDER BY date DESC LIMIT 1"
        ).fetchone()
        portfolio_value = float(eq_row["total_value"]) if eq_row else float(row["starting_capital"] or 0)

        open_count = conn.execute(
            "SELECT COUNT(*) AS c FROM agent_positions WHERE status='open'"
        ).fetchone()
        n_positions = int(open_count["c"]) if open_count else 0

        # Compute next-run / overdue
        next_run = None
        overdue = False
        freq = (row["rebalance_frequency"] or "manual").lower()
        last_run = row["last_run"]
        if freq != "manual" and last_run:
            try:
                last_dt = datetime.strptime(last_run[:16], "%Y-%m-%d %H:%M")
                interval_map = {"daily": 1, "weekly": 7, "monthly": 30}
                days = interval_map.get(freq, 7)
                next_dt = last_dt + timedelta(days=days)
                next_run = next_dt.strftime("%Y-%m-%d %H:%M")
                overdue = datetime.utcnow() > next_dt
            except Exception:
                pass

        return {
            "enabled": (row["status"] or "stopped").lower() == "running",
            "last_run": row["last_run"],
            "portfolio_value": portfolio_value,
            "open_positions": n_positions,
            "rebalance_frequency": freq,
            "next_run": next_run,
            "overdue": overdue,
        }
    finally:
        conn.close()


# ── Config ───────────────────────────────────────────────────────


def get_config() -> dict:
    init_db()
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM agent_config WHERE id=1").fetchone()
        if not row:
            return {
                "starting_capital": 100_000, "current_cash": 100_000,
                "risk_per_trade": 0.02, "max_positions": 8,
                "max_buys_per_cycle": 3, "min_opportunity_score": 60,
                "stop_loss_pct": 12.0, "rebalance_frequency": "weekly",
                "status": "stopped",
            }
        d = dict(row)
        return {
            "starting_capital": float(d.get("starting_capital") or 100_000),
            "current_cash": float(d.get("current_cash") or 0),
            "risk_per_trade": float(d.get("risk_per_trade") or 0.02),
            "max_positions": int(d.get("max_positions") or 8),
            "max_buys_per_cycle": int(d.get("max_buys_per_cycle") or 3),
            "min_opportunity_score": int(d.get("min_opportunity_score") or 60),
            "stop_loss_pct": float(d.get("stop_loss_pct") or 12.0),
            "rebalance_frequency": d.get("rebalance_frequency") or "weekly",
            "status": d.get("status") or "stopped",
            "last_run": d.get("last_run"),
        }
    finally:
        conn.close()


def update_config(**fields) -> dict:
    """Patch agent_config with the given fields. Returns updated config."""
    init_db()
    conn = get_connection()
    try:
        # Ensure row exists
        existing = conn.execute("SELECT id FROM agent_config WHERE id=1").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO agent_config (id, starting_capital, current_cash, status, created_at) "
                "VALUES (1, 100000, 100000, 'stopped', ?)",
                (datetime.utcnow().isoformat(),),
            )

        allowed = {
            "starting_capital", "current_cash", "risk_per_trade",
            "max_positions", "max_buys_per_cycle", "min_opportunity_score",
            "stop_loss_pct", "rebalance_frequency",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if updates:
            cols = ", ".join(f"{k}=?" for k in updates.keys())
            values = list(updates.values()) + [1]
            conn.execute(f"UPDATE agent_config SET {cols} WHERE id=?", values)
            conn.commit()
    finally:
        conn.close()

    return get_config()


def reset(starting_capital: float = 100_000, risk_per_trade: float = 0.02,
          max_positions: int = 8, max_buys_per_cycle: int = 3,
          min_opportunity_score: int = 60, stop_loss_pct: float = 12.0) -> dict:
    from src.agent import reset_agent
    reset_agent(
        capital=starting_capital, risk_pct=risk_per_trade,
        max_pos=max_positions, max_buys=max_buys_per_cycle,
        min_score=min_opportunity_score, stop_pct=stop_loss_pct,
    )
    return get_config()


# ── Personalities ────────────────────────────────────────────────


def get_personalities() -> dict:
    """Return all 8 agent personalities + Risk Manager."""
    from src.personalities import AGENT_PERSONALITIES, RISK_MANAGER

    OPINION = {"momentum", "value", "contrarian", "macro"}
    items = []
    for key, p in AGENT_PERSONALITIES.items():
        items.append({
            "key": key,
            "name": p.get("name", key),
            "icon": p.get("icon", "🤖"),
            "color": p.get("color", "#9ca3af"),
            "tagline": p.get("tagline", ""),
            "philosophy": p.get("philosophy", ""),
            "strengths": list(p.get("strengths") or []),
            "weaknesses": list(p.get("weaknesses") or []),
            "prioritizes": list(p.get("prioritizes") or []),
            "avoids": list(p.get("avoids") or []),
            "backtest_signals": list(p.get("backtest_signals") or []),
            "risk_tolerance": p.get("risk_tolerance", ""),
            "ideal_market": p.get("ideal_market", ""),
            "historical_edge": p.get("historical_edge", ""),
            "kind": "opinion" if key in OPINION else "data",
        })

    rm = {
        "name": RISK_MANAGER.get("name", "Risk Manager"),
        "icon": RISK_MANAGER.get("icon", "🛡"),
        "color": RISK_MANAGER.get("color", "#ef4444"),
        "tagline": RISK_MANAGER.get("tagline", ""),
        "philosophy": RISK_MANAGER.get("philosophy", ""),
        "checks": list(RISK_MANAGER.get("checks") or []),
    }

    return {"agents": items, "risk_manager": rm}


# ── Positions / Equity / Decisions ────────────────────────────────


def list_open_positions() -> list[dict]:
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol, direction, shares, entry_price, entry_date, stop_loss, target, "
            "exit_price, pnl, pnl_percent, ai_reasoning, status "
            "FROM agent_positions WHERE status='open' ORDER BY entry_date DESC"
        ).fetchall()
    finally:
        conn.close()

    out = []
    for r in rows:
        try:
            entry = float(r["entry_price"])
            shares = float(r["shares"])
            pnl = float(r["pnl"]) if r["pnl"] is not None else 0.0
            pnl_pct = float(r["pnl_percent"]) if r["pnl_percent"] is not None else 0.0
            current = entry * (1 + pnl_pct / 100.0)
            out.append({
                "symbol": r["symbol"],
                "direction": r["direction"] or "long",
                "shares": shares,
                "entry_price": entry,
                "entry_date": r["entry_date"],
                "stop_loss": float(r["stop_loss"]) if r["stop_loss"] is not None else None,
                "target": float(r["target"]) if r["target"] is not None else None,
                "current_price": current,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "ai_reasoning": r["ai_reasoning"] or "",
            })
        except Exception:
            continue
    return out


def get_equity_curve() -> dict:
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT date, total_value, cash, invested, cumulative_return, benchmark_value "
            "FROM agent_equity ORDER BY date ASC"
        ).fetchall()
    finally:
        conn.close()

    points = []
    for r in rows:
        try:
            points.append({
                "date": str(r["date"]),
                "total_value": float(r["total_value"] or 0),
                "cash": float(r["cash"] or 0),
                "invested": float(r["invested"] or 0),
                "cumulative_return": float(r["cumulative_return"] or 0),
                "benchmark_value": float(r["benchmark_value"]) if r["benchmark_value"] is not None else None,
            })
        except Exception:
            continue

    # Performance metrics
    metrics = {
        "total_return": 0.0,
        "annualized_return": 0.0,
        "max_drawdown": 0.0,
        "sharpe_ratio": 0.0,
        "alpha": 0.0,
    }
    if len(points) >= 2:
        first = points[0]["total_value"] or 1
        last = points[-1]["total_value"]
        metrics["total_return"] = ((last - first) / first) * 100.0 if first else 0.0
        try:
            from datetime import datetime as dt
            d0 = dt.strptime(points[0]["date"][:10], "%Y-%m-%d")
            d1 = dt.strptime(points[-1]["date"][:10], "%Y-%m-%d")
            days = max(1, (d1 - d0).days)
            metrics["annualized_return"] = ((last / first) ** (365 / days) - 1) * 100.0 if first else 0.0
        except Exception:
            pass

        # Max drawdown
        peak = points[0]["total_value"]
        max_dd = 0.0
        for p in points:
            v = p["total_value"]
            if v > peak: peak = v
            dd = (v - peak) / peak * 100.0 if peak else 0.0
            if dd < max_dd: max_dd = dd
        metrics["max_drawdown"] = max_dd

        # Sharpe (annualized) — daily returns
        rets = []
        for i in range(1, len(points)):
            prev = points[i - 1]["total_value"] or 1
            r = (points[i]["total_value"] - prev) / prev if prev else 0.0
            rets.append(r)
        if rets:
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / len(rets)
            std = var ** 0.5
            metrics["sharpe_ratio"] = (mean / std) * (252 ** 0.5) if std > 0 else 0.0

        # Alpha vs benchmark (if available)
        if points[-1].get("benchmark_value") is not None and points[0].get("benchmark_value") not in (None, 0):
            b0 = points[0]["benchmark_value"]
            b1 = points[-1]["benchmark_value"]
            bench_ret = ((b1 - b0) / b0) * 100.0 if b0 else 0.0
            metrics["alpha"] = metrics["total_return"] - bench_ret

    return {"points": points, "metrics": metrics}


def get_recent_decisions(limit: int = 30) -> list[dict]:
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT run_date, symbol, decision, reasoning FROM agent_decisions "
            "ORDER BY run_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "timestamp": str(r["run_date"]),
                "symbol": r["symbol"] or "",
                "action": r["decision"] or "",
                "quantity": None,
                "reason": r["reasoning"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_chain_of_thought(limit_runs: int = 5) -> dict:
    """Group agent_decisions by run_date so each "run" shows its full step-by-step thinking."""
    init_db()
    conn = get_connection()
    try:
        # Most recent N distinct run_dates
        run_rows = conn.execute(
            "SELECT DISTINCT run_date FROM agent_decisions "
            "WHERE run_date IS NOT NULL ORDER BY run_date DESC LIMIT ?",
            (limit_runs,),
        ).fetchall()
        run_dates = [r["run_date"] for r in run_rows]

        runs = []
        for run_date in run_dates:
            steps = conn.execute(
                "SELECT step, symbol, decision, reasoning, created_at "
                "FROM agent_decisions WHERE run_date = ? ORDER BY id ASC",
                (run_date,),
            ).fetchall()
            runs.append({
                "run_date": run_date,
                "steps": [
                    {
                        "step": s["step"] or "",
                        "symbol": s["symbol"] or "",
                        "decision": s["decision"] or "",
                        "reasoning": s["reasoning"] or "",
                        "created_at": str(s["created_at"] or ""),
                    }
                    for s in steps
                ],
            })
        return {"runs": runs}
    finally:
        conn.close()


# ── Status / lifecycle controls ───────────────────────────────────


def stop_agent() -> dict:
    """Mark the agent as stopped. Background scheduler reads this on next tick."""
    init_db()
    conn = get_connection()
    try:
        conn.execute("UPDATE agent_config SET status='stopped' WHERE id=1")
        conn.commit()
        return {"ok": True, "status": "stopped"}
    finally:
        conn.close()


def resume_agent() -> dict:
    init_db()
    conn = get_connection()
    try:
        conn.execute("UPDATE agent_config SET status='running' WHERE id=1")
        conn.commit()
        return {"ok": True, "status": "running"}
    finally:
        conn.close()


# ── Run cycle ────────────────────────────────────────────────────


def run_single_cycle() -> dict:
    """Run one TradingAgent cycle. Returns summary."""
    from src.agent import TradingAgent
    init_db()
    try:
        agent = TradingAgent()
        result = agent.run_cycle() or {}
        return {
            "ok": True,
            "trades_executed": int(result.get("trades_executed", 0)),
            "portfolio_value": float(result.get("portfolio_value", 0)),
            "summary": result.get("summary", ""),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def run_multi_cycle(rm_picks: int = 5, min_score: int = 60) -> dict:
    """Run a MultiAgentSystem cycle. Returns the full decision tree."""
    from src.multi_agent import MultiAgentSystem
    from src.data.gateway import DataGateway

    init_db()
    try:
        gw = DataGateway()
        snapshot = gw.get_macro_snapshot()
        macro_ctx = ""
        if snapshot:
            try:
                macro_ctx = (
                    f"VIX: {snapshot.vix}, Regime: "
                    f"{'recession_warning' if getattr(snapshot, 'yield_curve_inverted', False) else 'normal'}"
                )
            except Exception:
                pass

        try:
            flows = gw.get_sector_flows("1mo") or []
            inflowing = [f["sector"] for f in flows if f.get("change_pct", 0) > 0][:4]
        except Exception:
            inflowing = []
        if not inflowing:
            inflowing = ["Technology", "Healthcare", "Financials"]

        # Pull STOCK_DB without importing dashboard (mirror of discover_service)
        from api.services.discover_service import _load_stock_meta
        meta = _load_stock_meta()
        stock_db: dict = {}
        for sym, info in meta.items():
            sec = info.get("sector", "Other")
            stock_db.setdefault(sec, {})[sym] = (info.get("name") or sym, sec, "")

        existing = [p["symbol"] for p in list_open_positions()]
        risk_config = {
            "max_picks": rm_picks, "min_score": min_score,
            "min_backtest": 55, "max_sector_pct": 30, "duplicate_action": "half",
        }
        mas = MultiAgentSystem(risk_config)
        result = mas.run_cycle(inflowing, macro_ctx, stock_db, existing_positions=existing)

        # Shape the result
        agent_picks = {}
        for agent_key, sector_picks in (result.agent_picks or {}).items():
            agent_picks[agent_key] = []
            for sector, pick in (sector_picks or {}).items():
                if pick is None:
                    continue
                agent_picks[agent_key].append({
                    "sector": sector,
                    "symbol": getattr(pick, "symbol", ""),
                    "score": float(getattr(pick, "combined_score", 0) or 0),
                    "reasoning": getattr(pick, "reasoning", "") or "",
                })

        sector_winners = {}
        for sector, pick in (result.sector_winners or {}).items():
            if pick is None:
                continue
            sector_winners[sector] = {
                "symbol": getattr(pick, "symbol", ""),
                "agent": getattr(pick, "agent_key", ""),
                "score": float(getattr(pick, "combined_score", 0) or 0),
            }

        final_portfolio = []
        for pick in (result.final_portfolio or []):
            final_portfolio.append({
                "symbol": getattr(pick, "symbol", ""),
                "agent": getattr(pick, "agent_key", ""),
                "score": float(getattr(pick, "combined_score", 0) or 0),
                "reasoning": getattr(pick, "reasoning", "") or "",
            })

        return {
            "ok": True,
            "timestamp": result.timestamp,
            "macro_context": macro_ctx,
            "sectors_analyzed": list(inflowing),
            "agent_picks": agent_picks,
            "sector_winners": sector_winners,
            "final_portfolio": final_portfolio,
            "risk_manager_reasoning": result.risk_manager_reasoning or "",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
