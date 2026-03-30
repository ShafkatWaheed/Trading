"""Personality-Based Multi-Agent Trading System.

4 personality agents + 1 risk manager. Each agent runs the full pipeline
(Discover → Deep Dive → Backtest) independently, then Risk Manager picks
the best stock per sector.

No new dependencies — reuses existing analysis, backtester, and data modules.
Claude calls: 4 (discovery) + 1 (risk manager) = 5 per cycle.
"""

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime

from src.personalities import AGENT_PERSONALITIES, RISK_MANAGER


@dataclass
class AgentPick:
    symbol: str
    sector: str
    agent_name: str
    agent_icon: str
    score: int = 0
    signals_bullish: int = 0
    signals_bearish: int = 0
    signals_total: int = 0
    confirmations: int = 0
    momentum_override: bool = False
    backtest_win_rate: float = 0
    backtest_trades: int = 0
    combined_score: float = 0  # score × win_rate
    reasoning: str = ""
    deep_dive_summary: str = ""


@dataclass
class MultiAgentResult:
    timestamp: str
    sectors_analyzed: list[str] = field(default_factory=list)
    agent_picks: dict = field(default_factory=dict)  # {agent_name: {sector: AgentPick}}
    sector_winners: dict = field(default_factory=dict)  # {sector: AgentPick}
    final_portfolio: list[dict] = field(default_factory=list)  # [{symbol, size, agent, reason}]
    risk_manager_reasoning: str = ""


class PersonalityAgent:
    """One trading agent with a specific personality."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.personality = AGENT_PERSONALITIES[key]
        self.name = self.personality["name"]
        self.icon = self.personality["icon"]
        self.color = self.personality["color"]

    def discover(self, sectors: list[str], macro_context: str, stock_db: dict) -> dict[str, str]:
        """Pick one stock per sector based on personality. Returns {sector: symbol}."""
        # Build available stocks per sector
        sector_stocks = {}
        for sym, (name, sector, kw) in stock_db.items():
            for s in sectors:
                if s.lower() in sector.lower():
                    sector_stocks.setdefault(s, []).append(f"{sym} ({name})")

        if not sector_stocks:
            return {}

        sector_text = "\n".join(f"{s}: {', '.join(stocks[:10])}" for s, stocks in sector_stocks.items())

        prompt = f"""{self.personality['prompt_prefix'] if 'prompt_prefix' in self.personality else f"You are a {self.name}. {self.personality['philosophy'][:200]}"}

MARKET CONTEXT:
{macro_context}

SECTORS WITH MONEY INFLOW:
{sector_text}

Pick your ONE BEST stock per sector based on your trading style.
JSON only: {{"picks": {{"Healthcare": "LLY", "Technology": "NVDA"}}}}"""

        try:
            env = dict(os.environ)
            env.pop("CLAUDECODE", None)
            proc = subprocess.run(
                ["claude", "-p", prompt, "--model", "haiku", "--allowedTools", ""],
                capture_output=True, text=True, timeout=20, env=env,
            )
            resp = proc.stdout.strip()
            j_start = resp.find("{")
            j_end = resp.rfind("}") + 1
            if j_start >= 0 and j_end > j_start:
                data = json.loads(resp[j_start:j_end])
                picks = data.get("picks", data)
                # Validate symbols exist in stock_db
                return {s: sym for s, sym in picks.items() if sym in stock_db and s in sectors}
        except Exception:
            pass

        return {}

    def deep_dive(self, symbol: str, hist_data=None) -> AgentPick:
        """Run 16-indicator analysis on a stock. No Claude call — pure computation."""
        from src.analysis import technical
        from src.analysis.opportunity import compute_opportunity
        from src.data.gateway import DataGateway

        pick = AgentPick(
            symbol=symbol, sector="", agent_name=self.key, agent_icon=self.icon,
        )

        try:
            gw = DataGateway()
            hist = hist_data if hist_data is not None else gw.get_historical(symbol, period_days=252)
            if hist is None or hist.empty:
                return pick

            tech = technical.analyze(symbol, hist)
            score = compute_opportunity(symbol, tech, is_disruption_beneficiary=True)

            # Count signals
            try:
                from src.orchestrator import analyze_stock
                report = analyze_stock(symbol, export=False)
                if report:
                    bullish_words = ("buy", "bullish", "positive", "tailwind", "accumulating")
                    bearish_words = ("sell", "bearish", "negative", "risk", "headwind")
                    for s in report.sections:
                        cl = s.content.lower()
                        if any(w in cl for w in bullish_words):
                            pick.signals_bullish += 1
                        elif any(w in cl for w in bearish_words):
                            pick.signals_bearish += 1
                        pick.signals_total += 1
            except Exception:
                pass

            pick.score = score.total_score
            pick.confirmations = score.confirmations
            pick.momentum_override = score.momentum_override

            # Summary
            rsi = f"RSI {float(tech.rsi_14):.0f}" if tech.rsi_14 else ""
            trend = tech.trend or ""
            pick.deep_dive_summary = f"{rsi}, {trend}, {pick.signals_bullish}/{pick.signals_total} bullish"

        except Exception:
            pass

        return pick

    def backtest(self, symbol: str, hist_data=None) -> tuple[float, int]:
        """Backtest with THIS agent's preferred signals. Returns (win_rate, trade_count)."""
        from src.analysis.backtester import backtest_signal, SIGNALS
        from src.data.gateway import DataGateway

        preferred = self.personality.get("backtest_signals", [])
        if not preferred:
            return 0.0, 0

        try:
            gw = DataGateway()
            hist = hist_data if hist_data is not None else gw.get_historical(symbol, period_days=365)
            if hist is None or hist.empty or len(hist) < 60:
                return 0.0, 0

            total_wins = 0
            total_trades = 0

            for sig_name in preferred:
                if sig_name not in SIGNALS:
                    continue
                try:
                    result = backtest_signal(symbol, hist, sig_name, hold_days=21)
                    if result.total_trades > 0:
                        total_wins += int(result.win_rate * result.total_trades)
                        total_trades += result.total_trades
                except Exception:
                    continue

            win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
            return round(win_rate, 1), total_trades

        except Exception:
            return 0.0, 0

    def full_pipeline(self, sectors: list[str], macro_context: str, stock_db: dict) -> dict[str, AgentPick]:
        """Run complete pipeline: discover → deep dive → backtest per sector."""
        # Step 1: Discover
        discoveries = self.discover(sectors, macro_context, stock_db)

        # Step 2+3: Deep dive + backtest each pick
        picks = {}
        for sector, symbol in discoveries.items():
            pick = self.deep_dive(symbol)
            pick.sector = sector

            bt_rate, bt_trades = self.backtest(symbol)
            pick.backtest_win_rate = bt_rate
            pick.backtest_trades = bt_trades
            pick.combined_score = round(pick.score * (bt_rate / 100), 1) if bt_rate > 0 else pick.score * 0.5

            picks[sector] = pick

        return picks


class RiskManagerAgent:
    """Evaluates all agent picks and builds final portfolio."""

    def __init__(self, config: dict | None = None) -> None:
        config = config or {}
        self.max_picks = config.get("max_picks", 3)
        self.min_score = config.get("min_score", 65)
        self.min_backtest = config.get("min_backtest", 60)
        self.max_sector_pct = config.get("max_sector_pct", 40)
        self.duplicate_action = config.get("duplicate_action", "half")

    def evaluate(self, all_agent_picks: dict[str, dict[str, AgentPick]], existing_positions: list[str] = None) -> tuple[list[dict], str]:
        """
        Evaluate all picks, select best per sector, build portfolio.
        Returns (final_picks, reasoning).
        """
        existing = set(existing_positions or [])

        # Organize by sector
        sector_candidates: dict[str, list[AgentPick]] = {}
        for agent_name, sector_picks in all_agent_picks.items():
            for sector, pick in sector_picks.items():
                sector_candidates.setdefault(sector, []).append(pick)

        # Build prompt for Claude
        sector_text = ""
        for sector, picks in sector_candidates.items():
            sector_text += f"\n{sector}:\n"
            for p in sorted(picks, key=lambda x: x.combined_score, reverse=True):
                sector_text += (
                    f"  {p.agent_icon} {p.agent_name}: {p.symbol}, "
                    f"score {p.score}, BT {p.backtest_win_rate}% ({p.backtest_trades} trades), "
                    f"confirmations {p.confirmations}/3"
                    f"{' 🚀OVERRIDE' if p.momentum_override else ''}"
                    f", {p.deep_dive_summary}\n"
                )

        prompt = f"""You are the Risk Manager. Evaluate these stock picks from 4 trading agents and build the final portfolio.

AGENT PICKS BY SECTOR:
{sector_text}

CURRENT HOLDINGS: {', '.join(existing) if existing else 'None'}

RULES:
- Pick the BEST stock per sector (highest combined_score = score × backtest_win_rate)
- Max {self.max_picks} total picks
- Min score: {self.min_score} (reject below this)
- Min backtest win rate: {self.min_backtest}% (reject unproven)
- If already holding a stock in this sector: {self.duplicate_action}
- Position size: "full" for strong picks, "half" for borderline or sector overlap

JSON only:
{{"picks": [{{"symbol": "LLY", "sector": "Healthcare", "agent": "momentum", "size": "full", "reason": "10 words max"}}],
 "reasoning": "2 sentences explaining your portfolio construction logic"}}"""

        try:
            env = dict(os.environ)
            env.pop("CLAUDECODE", None)
            proc = subprocess.run(
                ["claude", "-p", prompt, "--model", "haiku"],
                capture_output=True, text=True, timeout=25, env=env,
            )
            resp = proc.stdout.strip()
            j_start = resp.find("{")
            j_end = resp.rfind("}") + 1
            if j_start >= 0 and j_end > j_start:
                data = json.loads(resp[j_start:j_end])
                picks = data.get("picks", [])
                reasoning = data.get("reasoning", "")

                # Validate
                valid_picks = []
                for p in picks[:self.max_picks]:
                    sym = p.get("symbol", "")
                    if sym and sym not in existing:
                        valid_picks.append(p)

                return valid_picks, reasoning
        except Exception:
            pass

        # Fallback: pick highest combined_score per sector
        fallback_picks = []
        for sector, picks in sector_candidates.items():
            best = max(picks, key=lambda p: p.combined_score)
            if best.score >= self.min_score and best.backtest_win_rate >= self.min_backtest:
                fallback_picks.append({
                    "symbol": best.symbol, "sector": sector,
                    "agent": best.agent_name, "size": "full",
                    "reason": f"Highest combined score in {sector}",
                })
        return fallback_picks[:self.max_picks], "Fallback: selected highest combined scores per sector"


class MultiAgentSystem:
    """Orchestrates 4 personality agents + risk manager."""

    def __init__(self, risk_config: dict | None = None) -> None:
        self.agents = {
            key: PersonalityAgent(key) for key in AGENT_PERSONALITIES
        }
        self.risk_manager = RiskManagerAgent(risk_config)

    def run_cycle(self, sectors: list[str], macro_context: str, stock_db: dict,
                  existing_positions: list[str] = None) -> MultiAgentResult:
        """Full multi-agent cycle."""
        result = MultiAgentResult(
            timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            sectors_analyzed=sectors,
        )

        # Each agent runs full pipeline
        import time
        for key, agent in self.agents.items():
            picks = agent.full_pipeline(sectors, macro_context, stock_db)
            result.agent_picks[key] = picks
            time.sleep(0.5)  # Rate limit between agents

        # Find sector winners
        for sector in sectors:
            best_pick = None
            best_score = -1
            for agent_name, sector_picks in result.agent_picks.items():
                pick = sector_picks.get(sector)
                if pick and pick.combined_score > best_score:
                    best_score = pick.combined_score
                    best_pick = pick
            if best_pick:
                result.sector_winners[sector] = best_pick

        # Risk Manager decides final portfolio
        final_picks, reasoning = self.risk_manager.evaluate(
            result.agent_picks, existing_positions
        )
        result.final_portfolio = final_picks
        result.risk_manager_reasoning = reasoning

        return result
