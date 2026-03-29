"""AI Trading Agent — Autonomous paper trading using Claude.

Uses all platform data sources + 12 Deep Dive indicators.
Claude CLI makes decisions, agent executes paper trades.
"""

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from src.utils.db import get_connection, init_db


@dataclass
class AgentConfig:
    starting_capital: float = 100000
    current_cash: float = 100000
    risk_per_trade: float = 0.02
    max_positions: int = 5
    rebalance_frequency: str = "weekly"
    status: str = "stopped"
    last_run: str | None = None


@dataclass
class AgentPosition:
    id: int = 0
    symbol: str = ""
    direction: str = "long"
    shares: int = 0
    entry_price: float = 0
    entry_date: str = ""
    stop_loss: float | None = None
    target: float | None = None
    status: str = "open"
    exit_price: float | None = None
    exit_date: str | None = None
    pnl: float | None = None
    pnl_percent: float | None = None
    ai_reasoning: str = ""


class TradingAgent:
    """Autonomous AI trading agent."""

    def __init__(self) -> None:
        init_db()
        self.config = self._load_config()
        self.positions = self._load_positions()

    def run_cycle(self) -> dict:
        """Run one full agent cycle. Returns detailed step-by-step results."""
        run_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        steps = {}

        # Step 1: Analyze market
        market = self._analyze_market()
        self._log_decision(run_date, "market_analysis", None, "completed", market.get("summary", ""))
        steps["market"] = market

        # Step 2: Check existing positions (stop losses, signal flips)
        closed = self._monitor_positions(run_date)
        steps["closed_positions"] = closed

        # Step 3: AI-guided discovery
        candidates = self._discover_stocks(market)
        self._log_decision(run_date, "discovery", None, f"found {len(candidates)} candidates",
                          ", ".join(c["symbol"] for c in candidates[:5]))
        steps["candidates"] = candidates

        # Get AI discovery reasoning from the latest decision log
        discovery_decisions = [d for d in self._get_recent_decisions(run_date) if d.get("step") == "ai_discovery"]
        steps["discovery_reasoning"] = discovery_decisions[0]["reasoning"] if discovery_decisions else ""
        steps["discovery_focus"] = discovery_decisions[0]["decision"] if discovery_decisions else ""

        # Step 4: Deep dive top picks
        analyses = self._deep_dive(candidates[:5])
        steps["analyses"] = analyses

        # Step 5: AI decides
        trades = self._ai_decide(run_date, market, analyses)
        steps["trade_decisions"] = trades

        # Step 6: Execute paper trades
        executed = self._execute(run_date, trades)
        steps["executed"] = executed
        steps["checklists"] = getattr(self, "_last_checklists", {})

        # Step 7: Log equity
        equity = self._log_equity(run_date)
        steps["equity"] = equity

        # Update last run
        self._update_last_run(run_date)

        return {
            "run_date": run_date,
            "steps": steps,
            "market_regime": market.get("regime", "unknown"),
            "candidates_found": len(candidates),
            "positions_closed": len(closed),
            "trades_executed": len(executed),
            "portfolio_value": equity.get("total_value", 0),
            "cash": self.config.current_cash,
            "return_pct": equity.get("cumulative_return", 0),
        }

    def _get_recent_decisions(self, run_date: str) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM agent_decisions WHERE run_date = ? ORDER BY created_at DESC", (run_date,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Step 1: Market Analysis ────────────────────────────

    def _analyze_market(self) -> dict:
        try:
            from src.data.gateway import DataGateway
            gw = DataGateway()
            snapshot = gw.get_macro_snapshot()

            result = {"regime": "normal", "summary": ""}
            if snapshot:
                result["vix"] = float(snapshot.vix) if snapshot.vix else None
                result["fed_rate"] = float(snapshot.fed_funds_rate) if snapshot.fed_funds_rate else None
                result["unemployment"] = float(snapshot.unemployment_rate) if snapshot.unemployment_rate else None
                result["gdp_growth"] = float(snapshot.gdp_growth) if snapshot.gdp_growth else None
                result["cpi"] = float(snapshot.cpi_yoy) if snapshot.cpi_yoy else None

                if snapshot.vix and float(snapshot.vix) > 30:
                    result["regime"] = "high_volatility"
                elif snapshot.yield_spread_10y2y and float(snapshot.yield_spread_10y2y) < 0:
                    result["regime"] = "recession_warning"

                parts = []
                if result.get("vix"):
                    parts.append(f"VIX: {result['vix']:.1f}")
                if result.get("fed_rate"):
                    parts.append(f"Fed: {result['fed_rate']:.2f}%")
                if result.get("regime"):
                    parts.append(f"Regime: {result['regime']}")
                result["summary"] = " | ".join(parts)

            return result
        except Exception as e:
            return {"regime": "unknown", "summary": f"Error: {str(e)[:50]}"}

    # ── Step 2: Monitor Positions ──────────────────────────

    def _monitor_positions(self, run_date: str) -> list[dict]:
        closed = []
        for pos in self.positions:
            if pos.status != "open":
                continue

            try:
                current_price = self._get_current_price(pos.symbol)
                if current_price is None:
                    continue

                # Check stop loss
                if pos.stop_loss and current_price <= pos.stop_loss:
                    self._close_position(pos, current_price, run_date, "Stop loss hit")
                    closed.append({"symbol": pos.symbol, "reason": "stop_loss", "pnl_pct": pos.pnl_percent})

                # Check target
                elif pos.target and current_price >= pos.target:
                    self._close_position(pos, current_price, run_date, "Target reached")
                    closed.append({"symbol": pos.symbol, "reason": "target", "pnl_pct": pos.pnl_percent})

            except Exception:
                continue

        return closed

    # ── Step 3: Discover Stocks ────────────────────────────

    def _discover_stocks(self, market: dict) -> list[dict]:
        try:
            from src.analysis import technical
            from src.analysis.opportunity import compute_opportunity
            from src.data.gateway import DataGateway
            from dashboard import STOCK_DB

            gw = DataGateway()

            # Step 1: Ask Claude which sectors/stocks to focus on
            ai_guidance = self._ai_discover_guidance(market)

            # Step 2: Build prioritized universe from AI guidance
            favored_sectors = ai_guidance.get("favor_sectors", [])
            avoid_sectors = ai_guidance.get("avoid_sectors", [])
            specific_tickers = ai_guidance.get("specific_tickers", [])
            min_score = ai_guidance.get("min_score", 50)

            # Prioritize: AI-specific picks → favored sectors → rest
            universe_ordered = []

            # First: any specific tickers Claude recommended
            for sym in specific_tickers:
                if sym in STOCK_DB and sym not in universe_ordered:
                    universe_ordered.append(sym)

            # Second: stocks in favored sectors
            for sym, (name, sector, kw) in STOCK_DB.items():
                if sym in universe_ordered:
                    continue
                if any(f.lower() in sector.lower() or f.lower() in kw.lower() for f in favored_sectors):
                    universe_ordered.append(sym)

            # Third: rest (excluding avoided sectors)
            for sym, (name, sector, kw) in STOCK_DB.items():
                if sym in universe_ordered:
                    continue
                if any(a.lower() in sector.lower() for a in avoid_sectors):
                    continue
                universe_ordered.append(sym)

            universe = universe_ordered[:40]

            # Step 3: Score each stock
            results = []
            already_holding = {p.symbol for p in self.positions if p.status == "open"}

            for sym in universe:
                if sym in already_holding:
                    continue
                try:
                    hist = gw.get_historical(sym, period_days=60)
                    if hist is None or hist.empty:
                        continue
                    tech = technical.analyze(sym, hist)
                    score = compute_opportunity(sym, tech)

                    if score.total_score < min_score:
                        continue

                    sector = STOCK_DB.get(sym, ("", "", ""))[1]
                    is_favored = any(f.lower() in sector.lower() for f in favored_sectors)
                    is_specific = sym in specific_tickers

                    results.append({
                        "symbol": sym,
                        "score": score.total_score + (10 if is_specific else 5 if is_favored else 0),
                        "raw_score": score.total_score,
                        "strategy": score.strategy,
                        "label": score.label,
                        "sector": sector,
                        "ai_pick": is_specific,
                    })
                except Exception:
                    continue

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:10]
        except Exception:
            return []

    def _ai_discover_guidance(self, market: dict) -> dict:
        """Ask Claude which sectors and stocks to focus on — uses full market context."""
        try:
            from dashboard import STOCK_DB
            from src.utils.db import cache_get

            sectors = sorted(set(s for _, (_, s, _) in STOCK_DB.items()))
            tickers_with_info = [f"{sym} ({name}, {sector})" for sym, (name, sector, _) in list(STOCK_DB.items())[:50]]

            # Gather all available context
            # 1. Geopolitical events
            geo_events = cache_get("geo:events") or []
            geo_summary = ""
            if geo_events:
                geo_parts = []
                for e in geo_events[:4]:
                    geo_parts.append(f"- {e.get('type', '').replace('_', ' ').title()}: {e.get('title', '')[:80]} (severity: {e.get('severity', 'moderate')})")
                geo_summary = "\n".join(geo_parts)

            # 2. Disruption themes
            disruption = cache_get("geo:disruption_themes") or []
            disrupt_summary = ""
            if disruption:
                disrupt_parts = []
                for t in disruption[:4]:
                    disrupt_parts.append(f"- {t.get('name', '')}: {t.get('level', 'EMERGING')} intensity")
                disrupt_summary = "\n".join(disrupt_parts)

            # 3. Sector flows (if cached)
            sector_flow_text = ""
            sector_flows = cache_get("sector:flows")
            if sector_flows and isinstance(sector_flows, list):
                gaining = [f for f in sector_flows if f.get("change", 0) > 0]
                losing = [f for f in sector_flows if f.get("change", 0) < 0]
                if gaining:
                    sector_flow_text += "Money flowing IN: " + ", ".join(f"{f['sector']} ({f['change']:+.1f}%)" for f in gaining[:3])
                if losing:
                    sector_flow_text += "\nMoney flowing OUT: " + ", ".join(f"{f['sector']} ({f['change']:+.1f}%)" for f in losing[:3])

            # 4. Current portfolio
            open_positions = [p for p in self.positions if p.status == "open"]
            portfolio_text = ""
            if open_positions:
                portfolio_text = "Currently holding: " + ", ".join(f"{p.symbol} ({p.shares} shares)" for p in open_positions)
            else:
                portfolio_text = "No current positions — starting fresh."

            prompt = f"""You are a professional portfolio strategist managing a ${self.config.current_cash:,.0f} paper portfolio. Analyze ALL the data below and tell me where to find the best trading opportunities right now.

═══ MACROECONOMIC CONDITIONS ═══
{json.dumps(market, indent=2, default=str)}

═══ GEOPOLITICAL RISKS ═══
{geo_summary if geo_summary else "No major geopolitical events detected."}

═══ TECHNOLOGY DISRUPTION ═══
{disrupt_summary if disrupt_summary else "No major disruption themes active."}

═══ SECTOR MONEY FLOW ═══
{sector_flow_text if sector_flow_text else "No sector flow data available."}

═══ CURRENT PORTFOLIO ═══
{portfolio_text}

═══ AVAILABLE STOCKS ═══
{chr(10).join(tickers_with_info)}

═══ YOUR TASK ═══
Based on ALL the above data:
1. Which sectors should I focus on and why?
2. Which sectors should I avoid and why?
3. Which 5 specific tickers are best positioned right now?
4. What minimum quality score should I require? (50=normal, 60=selective, 70=very picky)

Consider:
- Macro regime (risk-on or risk-off?)
- Geopolitical risks (which sectors are exposed?)
- Disruption themes (who benefits, who loses?)
- Sector flows (follow the money)
- Portfolio diversification (don't double up on sectors I already hold)

Respond in this EXACT JSON format (no other text):
{{
  "favor_sectors": ["Sector1", "Sector2"],
  "avoid_sectors": ["Sector3"],
  "specific_tickers": ["AAPL", "NVDA", "LLY", "XOM", "UNH"],
  "min_score": 55,
  "reasoning": "2-3 sentences explaining your strategy based on the data above"
}}"""

            env = dict(os.environ)
            env.pop("CLAUDECODE", None)

            proc = subprocess.run(
                ["claude", "-p", prompt, "--model", "haiku"],
                capture_output=True, text=True, timeout=30, env=env,
            )
            response = proc.stdout.strip()

            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                # Log the AI's reasoning
                self._log_decision(
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
                    "ai_discovery",
                    None,
                    f"Focus: {', '.join(data.get('favor_sectors', []))}",
                    data.get("reasoning", ""),
                )
                return data

        except Exception:
            pass

        # Fallback: no bias
        return {"favor_sectors": [], "avoid_sectors": [], "specific_tickers": [], "min_score": 50}

    # ── Step 4: Deep Dive ──────────────────────────────────

    def _deep_dive(self, candidates: list[dict]) -> dict:
        analyses = {}
        skip_sections = ("company overview", "signal confluence")
        bullish_words = ("buy", "bullish", "positive", "tailwind", "accumulating", "upgrade", "strong buy", "beneficiary")
        bearish_words = ("sell", "bearish", "negative", "risk", "distributing", "headwind", "downgrade", "at risk", "high risk")

        for c in candidates:
            try:
                from src.orchestrator import analyze_stock
                report = analyze_stock(c["symbol"], export=False)
                if not report:
                    continue

                # Build per-signal breakdown
                signals = []
                bull = 0
                bear = 0
                for s in report.sections:
                    if any(skip in s.title.lower() for skip in skip_sections):
                        continue

                    cl = s.content.lower()
                    # Determine direction from score first, then keywords
                    score_val = s.data.get("score", s.data.get("overall", None))
                    try:
                        sn = float(score_val) if score_val is not None else None
                    except (ValueError, TypeError):
                        sn = None

                    if sn is not None:
                        direction = "bullish" if sn > 0.1 else "bearish" if sn < -0.1 else "neutral"
                    elif any(w in cl for w in bullish_words):
                        direction = "bullish"
                    elif any(w in cl for w in bearish_words):
                        direction = "bearish"
                    else:
                        direction = "neutral"

                    if direction == "bullish":
                        bull += 1
                    elif direction == "bearish":
                        bear += 1

                    # Extract key data points per signal
                    detail = s.content[:120]
                    key_data = {}
                    for k, v in s.data.items():
                        if k in ("factors", "strengths", "weaknesses", "events", "top_posts", "top_holders", "notable", "themes"):
                            continue
                        if isinstance(v, (list, dict)):
                            continue
                        if v is not None and str(v) not in ("", "None", "[]"):
                            key_data[k] = v

                    signals.append({
                        "name": s.title,
                        "direction": direction,
                        "detail": detail,
                        "data": key_data,
                    })

                total = bull + bear + (len(signals) - bull - bear)

                # Run backtest on top signals
                backtest_summary = []
                try:
                    from src.analysis.backtester import backtest_all_signals
                    from src.data.gateway import DataGateway
                    bt_gw = DataGateway()
                    bt_hist = bt_gw.get_historical(c["symbol"], period_days=365)
                    if bt_hist is not None and not bt_hist.empty and len(bt_hist) >= 60:
                        bt_results = backtest_all_signals(c["symbol"], bt_hist, hold_days=21)
                        for r in sorted(bt_results, key=lambda x: x.win_rate, reverse=True)[:5]:
                            if r.total_trades > 0:
                                backtest_summary.append({
                                    "signal": r.signal_name.replace("_", " ").title(),
                                    "win_rate": f"{r.win_rate * 100:.0f}%",
                                    "avg_return": f"{r.avg_return:+.1f}%",
                                    "trades": r.total_trades,
                                    "grade": r.grade,
                                })
                except Exception:
                    pass

                analyses[c["symbol"]] = {
                    "verdict": report.verdict.value,
                    "confidence": report.confidence,
                    "risk": report.risk_rating.value,
                    "price": float(report.current_price),
                    "sentiment": float(report.sentiment_score),
                    "bullish_signals": bull,
                    "bearish_signals": bear,
                    "total_signals": total,
                    "reasoning": report.reasoning[:3],
                    "signals": signals,
                    "backtest": backtest_summary,
                }
            except Exception:
                continue
            time.sleep(0.5)
        return analyses

    # ── Step 5: AI Decision ────────────────────────────────

    def _ai_decide(self, run_date: str, market: dict, analyses: dict) -> list[dict]:
        if not analyses:
            return []

        # Build portfolio summary
        open_positions = [p for p in self.positions if p.status == "open"]
        positions_text = ""
        if open_positions:
            for p in open_positions:
                cur = self._get_current_price(p.symbol) or p.entry_price
                pnl = ((cur - p.entry_price) / p.entry_price) * 100
                positions_text += f"  - {p.symbol}: {p.shares} shares @ ${p.entry_price:.2f} (now ${cur:.2f}, {pnl:+.1f}%)\n"
        else:
            positions_text = "  No open positions.\n"

        # Build candidates summary with FULL signal details
        candidates_text = ""
        for sym, data in analyses.items():
            candidates_text += (
                f"\n  ═══ {sym} ═══\n"
                f"  Verdict: {data['verdict']} | Confidence: {data['confidence']} | Risk: {data['risk']}/5 | Price: ${data['price']:.2f}\n"
                f"  Signals: {data['bullish_signals']} bullish / {data['bearish_signals']} bearish / {data['total_signals']} total\n"
            )
            # Add each signal's detail
            for sig in data.get("signals", []):
                dir_icon = "🟢" if sig["direction"] == "bullish" else "🔴" if sig["direction"] == "bearish" else "🟡"
                candidates_text += f"    {dir_icon} {sig['name']}: {sig['detail'][:100]}\n"
                if sig.get("data"):
                    data_str = " | ".join(f"{k}={v}" for k, v in list(sig["data"].items())[:5])
                    candidates_text += f"       Data: {data_str}\n"

            # Add backtest track record
            bt = data.get("backtest", [])
            if bt:
                candidates_text += f"    ── Historical Signal Accuracy (21-day hold) ──\n"
                for b in bt:
                    candidates_text += f"    {b['grade']} {b['signal']}: {b['win_rate']} win rate, {b['avg_return']} avg return ({b['trades']} trades)\n"

            candidates_text += "\n"

        prompt = f"""You are an autonomous AI trading agent managing a paper portfolio.

MARKET CONTEXT:
{json.dumps(market, indent=2, default=str)}

PORTFOLIO:
  Cash: ${self.config.current_cash:,.2f}
  Max risk per trade: {self.config.risk_per_trade * 100:.0f}% (${self.config.current_cash * self.config.risk_per_trade:,.0f})
  Max positions: {self.config.max_positions}
  Open positions:
{positions_text}
STOCK CANDIDATES (analyzed with 12 indicators):
{candidates_text}
RULES:
- Only trade if signal alignment is strong (7+ of 12 signals agree)
- PRIORITIZE signals with proven track records — if backtest shows 70%+ win rate, trust that signal more
- AVOID signals with poor track records — if backtest shows <40% win rate, discount that signal
- Follow the money — favor sectors with positive money flow, avoid sectors with outflows
- Set stop loss on every trade (use support level from technical data, or -8% max)
- Set target (use resistance level from technical data, or +15% max)
- Position size based on risk per trade and stop loss distance
- Maximum {self.config.max_positions} open positions at once
- Keep at least 20% in cash
- If market regime is high_volatility or recession_warning, be defensive
- If insider cluster buy detected AND backtest confirms insider buys work on this stock, increase conviction
- If analyst consensus is Strong Buy with 20%+ upside, that's a strong confirming signal
- If sector money flow is negative for a stock's sector, reduce conviction even if other signals are bullish

Respond in this EXACT JSON format (no other text):
{{
  "trades": [
    {{"symbol": "AAPL", "action": "BUY", "shares": 50, "stop_loss": 240.00, "target": 280.00, "reason": "Strong momentum with 9/12 bullish signals"}},
    {{"symbol": "NVDA", "action": "SELL", "reason": "Signal flipped bearish, take profit"}}
  ],
  "skip_reason": "Optional explanation if no trades"
}}"""

        try:
            env = dict(os.environ)
            env.pop("CLAUDECODE", None)

            proc = subprocess.run(
                ["claude", "-p", prompt, "--model", "haiku"],
                capture_output=True, text=True, timeout=60, env=env,
            )
            response = proc.stdout.strip()

            # Extract JSON from response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                trades = data.get("trades", [])

                for t in trades:
                    self._log_decision(run_date, "ai_trade", t.get("symbol"),
                                      t.get("action", "HOLD"), t.get("reason", ""))

                return trades

        except Exception as e:
            self._log_decision(run_date, "ai_error", None, "error", str(e)[:100])

        return []

    # ── Step 6: Execute Trades ─────────────────────────────

    def _execute(self, run_date: str, trades: list[dict]) -> list[dict]:
        executed = []
        self._last_checklists = {}  # Store checklists for dashboard display

        for trade in trades:
            sym = trade.get("symbol", "")
            action = trade.get("action", "").upper()

            if action == "BUY":
                # Run checklist before execution
                price = self._get_current_price(sym)
                if price:
                    passed, checks = self._pre_trade_check(sym, price, run_date)
                    self._last_checklists[sym] = {"passed": passed, "checks": checks, "action": "BUY"}

                result = self._execute_buy(sym, trade, run_date)
                if result:
                    executed.append(result)

            elif action == "SELL":
                result = self._execute_sell(sym, trade, run_date)
                if result:
                    executed.append(result)

        return executed

    def _pre_trade_check(self, symbol: str, price: float, run_date: str) -> tuple[bool, list[str]]:
        """Run pre-trade checklist. Returns (pass, list of warnings/failures)."""
        checks = []
        all_pass = True

        # Check 1: Risk budget — total open risk must not exceed 10% of starting capital
        total_open_risk = sum(
            p.entry_price * p.shares * 0.08
            for p in self.positions if p.status == "open"
        )
        risk_budget = self.config.starting_capital * 0.10
        remaining = risk_budget - total_open_risk
        new_risk = price * self.config.risk_per_trade * 100  # Approximate
        if new_risk > remaining:
            checks.append(f"FAIL: Risk budget exceeded — trade risk ${new_risk:,.0f} > remaining ${remaining:,.0f}")
            all_pass = False
        else:
            checks.append(f"PASS: Risk budget OK — ${remaining:,.0f} remaining")

        # Check 2: Sector concentration — max 3 in same sector
        stock_sector = "Unknown"
        try:
            from dashboard import STOCK_DB
            if symbol in STOCK_DB:
                stock_sector = STOCK_DB[symbol][1]
        except Exception:
            pass

        same_sector = sum(
            1 for p in self.positions
            if p.status == "open" and self._get_sector(p.symbol) == stock_sector and stock_sector != "Unknown"
        )
        if same_sector >= 3:
            checks.append(f"WARN: Already holding {same_sector} {stock_sector} stocks — high concentration but not blocking if signals are strong")
        elif same_sector >= 2:
            checks.append(f"WARN: Holding {same_sector} {stock_sector} stocks — consider diversifying")
        else:
            checks.append(f"PASS: {stock_sector} — no concentration issue")

        # Check 3: Earnings within 5 days
        try:
            from src.data.gateway import DataGateway
            gw = DataGateway()
            earnings = gw.get_earnings_calendar(symbol)
            if earnings:
                from datetime import datetime as dt_check, timedelta
                now = dt_check.utcnow()
                for e in earnings[:1]:
                    edate = e.get("date", "")
                    if edate:
                        edt = dt_check.strptime(edate[:10], "%Y-%m-%d")
                        days_to = (edt - now).days
                        if 0 <= days_to <= 5:
                            checks.append(f"WARN: Earnings in {days_to} days — expect 5-15% move, use smaller size")
                        elif 0 <= days_to <= 14:
                            checks.append(f"WARN: Earnings in {days_to} days")
                        else:
                            checks.append("PASS: No upcoming earnings within 14 days")
                        break
                else:
                    checks.append("PASS: No upcoming earnings")
            else:
                checks.append("PASS: No earnings data")
        except Exception:
            checks.append("PASS: Earnings check skipped")

        # Check 4: Max positions
        open_count = sum(1 for p in self.positions if p.status == "open")
        if open_count >= self.config.max_positions:
            checks.append(f"FAIL: Already at max positions ({open_count}/{self.config.max_positions})")
            all_pass = False
        else:
            checks.append(f"PASS: {open_count}/{self.config.max_positions} positions used")

        # Check 5: Cash reserve — keep 20%
        if self.config.current_cash < self.config.starting_capital * 0.20:
            checks.append("FAIL: Cash below 20% reserve — cannot open new positions")
            all_pass = False
        else:
            checks.append(f"PASS: Cash reserve OK (${self.config.current_cash:,.0f})")

        return all_pass, checks

    def _get_sector(self, symbol: str) -> str:
        try:
            from dashboard import STOCK_DB
            if symbol in STOCK_DB:
                return STOCK_DB[symbol][1]
        except Exception:
            pass
        return "Unknown"

    def _execute_buy(self, symbol: str, trade: dict, run_date: str) -> dict | None:
        price = self._get_current_price(symbol)
        if not price:
            return None

        # Run pre-trade checklist
        passed, check_results = self._pre_trade_check(symbol, price, run_date)

        # Log checklist results
        self._log_decision(run_date, "pre_trade_check", symbol,
                          "PASSED" if passed else "BLOCKED",
                          " | ".join(check_results))

        if not passed:
            self._log_decision(run_date, "trade_blocked", symbol,
                              "SKIP", f"Pre-trade checklist failed: {' | '.join(r for r in check_results if 'FAIL' in r)}")
            return None

        shares = trade.get("shares", 0)
        if shares <= 0:
            stop = trade.get("stop_loss", price * 0.92)
            risk_per_share = price - stop
            if risk_per_share <= 0:
                risk_per_share = price * 0.08
            risk_amount = self.config.current_cash * self.config.risk_per_trade
            shares = int(risk_amount / risk_per_share)

        cost = shares * price
        if cost > self.config.current_cash * 0.8:
            shares = int((self.config.current_cash * 0.8) / price)
            cost = shares * price

        if shares <= 0:
            return None

        # Execute
        self.config.current_cash -= cost
        self._save_cash()

        pos = AgentPosition(
            symbol=symbol, direction="long", shares=shares,
            entry_price=price, entry_date=run_date,
            stop_loss=trade.get("stop_loss", round(price * 0.92, 2)),
            target=trade.get("target", round(price * 1.15, 2)),
            status="open", ai_reasoning=trade.get("reason", ""),
        )
        pos.id = self._save_position(pos)
        self.positions.append(pos)

        return {"symbol": symbol, "action": "BUY", "shares": shares, "price": price}

    def _execute_sell(self, symbol: str, trade: dict, run_date: str) -> dict | None:
        for pos in self.positions:
            if pos.symbol == symbol and pos.status == "open":
                price = self._get_current_price(symbol) or pos.entry_price
                self._close_position(pos, price, run_date, trade.get("reason", "AI sell signal"))
                return {"symbol": symbol, "action": "SELL", "shares": pos.shares, "price": price, "pnl_pct": pos.pnl_percent}
        return None

    # ── Step 7: Log Equity ─────────────────────────────────

    def _log_equity(self, run_date: str) -> dict:
        total_invested = 0
        for pos in self.positions:
            if pos.status == "open":
                cur = self._get_current_price(pos.symbol) or pos.entry_price
                total_invested += cur * pos.shares

        total_value = self.config.current_cash + total_invested
        cumulative = ((total_value - self.config.starting_capital) / self.config.starting_capital) * 100

        # Benchmark (S&P 500)
        benchmark = None
        try:
            import yfinance as yf
            spy = yf.Ticker("SPY")
            benchmark = spy.info.get("regularMarketPrice")
        except Exception:
            pass

        date_str = run_date[:10]
        conn = get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO agent_equity (date, total_value, cash, invested, cumulative_return, benchmark_value) VALUES (?, ?, ?, ?, ?, ?)",
            (date_str, total_value, self.config.current_cash, total_invested, cumulative, benchmark),
        )
        conn.commit()
        conn.close()

        return {"total_value": total_value, "cash": self.config.current_cash, "invested": total_invested, "cumulative_return": cumulative}

    # ── Helpers ────────────────────────────────────────────

    def _get_current_price(self, symbol: str) -> float | None:
        try:
            from src.data.gateway import DataGateway
            gw = DataGateway()
            quote = gw.get_quote(symbol)
            return float(quote.price) if quote and quote.price else None
        except Exception:
            return None

    def _close_position(self, pos: AgentPosition, exit_price: float, date: str, reason: str) -> None:
        pos.status = "closed"
        pos.exit_price = exit_price
        pos.exit_date = date
        pos.pnl = (exit_price - pos.entry_price) * pos.shares
        pos.pnl_percent = ((exit_price - pos.entry_price) / pos.entry_price) * 100

        self.config.current_cash += exit_price * pos.shares
        self._save_cash()

        conn = get_connection()
        conn.execute(
            "UPDATE agent_positions SET status=?, exit_price=?, exit_date=?, pnl=?, pnl_percent=? WHERE id=?",
            (pos.status, pos.exit_price, pos.exit_date, pos.pnl, pos.pnl_percent, pos.id),
        )
        conn.commit()
        conn.close()

        self._log_decision(date, "close_position", pos.symbol, f"SELL ({reason})",
                          f"P/L: {pos.pnl_percent:+.1f}%")

    def _save_position(self, pos: AgentPosition, source: str = "ai") -> int:
        conn = get_connection()
        cursor = conn.execute(
            "INSERT INTO agent_positions (symbol, direction, shares, entry_price, entry_date, stop_loss, target, status, ai_reasoning, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pos.symbol, pos.direction, pos.shares, pos.entry_price, pos.entry_date, pos.stop_loss, pos.target, pos.status, pos.ai_reasoning, source),
        )
        conn.commit()
        pos_id = cursor.lastrowid
        conn.close()
        return pos_id

    def _save_cash(self) -> None:
        conn = get_connection()
        conn.execute("UPDATE agent_config SET current_cash=? WHERE id=1", (self.config.current_cash,))
        conn.commit()
        conn.close()

    def _update_last_run(self, run_date: str) -> None:
        conn = get_connection()
        conn.execute("UPDATE agent_config SET last_run=? WHERE id=1", (run_date,))
        conn.commit()
        conn.close()

    def _log_decision(self, run_date: str, step: str, symbol: str | None, decision: str, reasoning: str) -> None:
        conn = get_connection()
        conn.execute(
            "INSERT INTO agent_decisions (run_date, step, symbol, decision, reasoning) VALUES (?, ?, ?, ?, ?)",
            (run_date, step, symbol, decision, reasoning),
        )
        conn.commit()
        conn.close()

    def _load_config(self) -> AgentConfig:
        conn = get_connection()
        row = conn.execute("SELECT * FROM agent_config WHERE id=1").fetchone()
        if not row:
            conn.execute(
                "INSERT INTO agent_config (id, starting_capital, current_cash, risk_per_trade, max_positions, rebalance_frequency, status, created_at) VALUES (1, 100000, 100000, 0.02, 5, 'weekly', 'stopped', ?)",
                (datetime.utcnow().isoformat(),),
            )
            conn.commit()
            conn.close()
            return AgentConfig()
        conn.close()
        return AgentConfig(
            starting_capital=row["starting_capital"], current_cash=row["current_cash"],
            risk_per_trade=row["risk_per_trade"], max_positions=row["max_positions"],
            rebalance_frequency=row["rebalance_frequency"], status=row["status"],
            last_run=row["last_run"],
        )

    def _load_positions(self) -> list[AgentPosition]:
        conn = get_connection()
        rows = conn.execute("SELECT * FROM agent_positions WHERE status='open'").fetchall()
        conn.close()
        return [AgentPosition(
            id=r["id"], symbol=r["symbol"], direction=r["direction"],
            shares=r["shares"], entry_price=r["entry_price"], entry_date=r["entry_date"],
            stop_loss=r["stop_loss"], target=r["target"], status=r["status"],
            ai_reasoning=r["ai_reasoning"] or "",
        ) for r in rows]


# ── Public functions for dashboard ─────────────────────

def get_agent_config() -> dict:
    init_db()
    conn = get_connection()
    row = conn.execute("SELECT * FROM agent_config WHERE id=1").fetchone()
    conn.close()
    if not row:
        return {"starting_capital": 100000, "current_cash": 100000, "status": "stopped"}
    return dict(row)


def get_agent_positions(status: str = "all") -> list[dict]:
    conn = get_connection()
    if status == "all":
        rows = conn.execute("SELECT * FROM agent_positions ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute("SELECT * FROM agent_positions WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_agent_decisions(limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM agent_decisions ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_agent_equity() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM agent_equity ORDER BY date ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_human_trade(symbol: str, direction: str, shares: int, entry_price: float,
                    stop_loss: float | None = None, target: float | None = None,
                    reasoning: str = "") -> int:
    """Add a manual (human) trade to the agent portfolio."""
    init_db()
    conn = get_connection()

    # Deduct cash
    cost = shares * entry_price
    conn.execute("UPDATE agent_config SET current_cash = current_cash - ? WHERE id = 1", (cost,))

    cursor = conn.execute(
        "INSERT INTO agent_positions (symbol, direction, shares, entry_price, entry_date, stop_loss, target, status, ai_reasoning, source) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, 'human')",
        (symbol.upper(), direction, shares, entry_price, datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
         stop_loss or round(entry_price * 0.92, 2), target or round(entry_price * 1.15, 2), reasoning),
    )
    trade_id = cursor.lastrowid

    # Log decision
    conn.execute(
        "INSERT INTO agent_decisions (run_date, step, symbol, decision, reasoning, source) VALUES (?, 'human_trade', ?, ?, ?, 'human')",
        (datetime.utcnow().strftime("%Y-%m-%d %H:%M"), symbol.upper(), f"BUY {shares} @ ${entry_price:.2f}", reasoning),
    )

    conn.commit()
    conn.close()
    return trade_id


def reset_agent(capital: float = 100000, risk_pct: float = 0.02, max_pos: int = 5) -> None:
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM agent_positions")
    conn.execute("DELETE FROM agent_decisions")
    conn.execute("DELETE FROM agent_equity")
    conn.execute(
        "INSERT OR REPLACE INTO agent_config (id, starting_capital, current_cash, risk_per_trade, max_positions, rebalance_frequency, status, created_at) VALUES (1, ?, ?, ?, ?, 'weekly', 'stopped', ?)",
        (capital, capital, risk_pct, max_pos, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
