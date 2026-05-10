"""Personality-Based Multi-Agent Trading System.

8 personality agents + 1 risk manager. 4 opinion-based agents (momentum, value,
contrarian, macro) + 4 data-driven agents (disruption, insider, options, flow).
Each agent runs the full pipeline (Discover → Deep Dive → Backtest) independently,
then Risk Manager picks the best stocks per sector.

Claude calls: 8 (discovery) + 1 (risk manager) = 9 per cycle.
Data-driven agents pre-fetch their specialized data before the Claude discovery call.
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
    # Opportunity score
    score: int = 0
    signals_bullish: int = 0
    signals_bearish: int = 0
    signals_total: int = 0
    confirmations: int = 0
    momentum_override: bool = False
    # Backtest
    backtest_win_rate: float = 0
    backtest_trades: int = 0
    combined_score: float = 0  # score × win_rate
    # Report data
    verdict: str = ""
    confidence: str = ""
    risk_rating: int = 0
    sentiment_score: float = 0
    signal_details: list = field(default_factory=list)
    # Trade plan
    price: float = 0
    support: float = 0
    resistance: float = 0
    risk_reward: float = 0
    atr_stop: float = 0
    atr_stop_pct: float = 0
    # Short-term signals
    rsi_5: float | None = None
    ema8_above_ema21: bool | None = None
    momentum_3d: float | None = None
    obv_trend: str | None = None
    macd_divergence: str | None = None
    seasonality: float | None = None
    fib_382: float | None = None
    # Meta
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
                    sector_stocks.setdefault(s, []).append(sym)

        if not sector_stocks:
            return {}

        # All agents get a light shared data summary; data-driven agents get deep specialized data
        from src.data.gateway import DataGateway
        gw = DataGateway()
        extra_data = self._fetch_shared_data(sector_stocks, gw)
        data_focus = self.personality.get("data_focus")
        if data_focus:
            extra_data += "\n" + self._fetch_agent_data(data_focus, sector_stocks, gw)

        sector_text = "\n".join(f"{s}: {', '.join(stocks[:10])}" for s, stocks in sector_stocks.items())

        prompt = f"""{self.personality.get('prompt_prefix', f"You are a {self.name}. {self.personality['philosophy'][:250]}")}

MARKET CONTEXT:
{macro_context}

SECTORS WITH MONEY INFLOW:
{sector_text}
{extra_data}
Pick your ONE BEST stock per sector based on your trading style and the data above.
JSON only: {{"picks": {{"Healthcare": "LLY", "Technology": "NVDA"}}}}"""

        try:
            env = dict(os.environ)
            env.pop("CLAUDECODE", None)
            proc = subprocess.run(
                ["claude", "-p", prompt, "--model", "haiku", "--allowedTools", ""],
                capture_output=True, text=True, timeout=30, env=env,
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

    def _fetch_shared_data(self, sector_stocks: dict[str, list[str]], gw) -> str:
        """Fetch light shared data for ALL agents — short interest, fundamentals."""
        lines = []
        all_syms = []
        for syms in sector_stocks.values():
            all_syms.extend(syms[:6])

        si_lines = []
        analyst_lines = []
        for sym in all_syms[:10]:
            # Short interest
            try:
                si = gw.get_short_interest(sym)
                if si and si.get("short_pct_float", 0) and si["short_pct_float"] > 5:
                    si_lines.append(f"{sym}: {si['short_pct_float']:.1f}% short")
            except Exception:
                pass
            # Fundamentals snapshot
            try:
                fund = gw.get_fundamentals(sym)
                if fund:
                    pe_str = f"P/E={float(fund.pe_ratio):.1f}" if fund.pe_ratio else ""
                    div_str = f"Div={float(fund.dividend_yield):.1f}%" if fund.dividend_yield else ""
                    parts = [p for p in [pe_str, div_str] if p]
                    if parts:
                        analyst_lines.append(f"{sym}: {', '.join(parts)}")
            except Exception:
                pass

        if si_lines:
            lines.append(f"\nSHORT INTEREST: {', '.join(si_lines[:8])}")
        if analyst_lines:
            lines.append(f"FUNDAMENTALS: {', '.join(analyst_lines[:8])}")

        return "\n".join(lines) if lines else ""

    def _fetch_agent_data(self, data_focus: str, sector_stocks: dict[str, list[str]], gw) -> str:
        """Fetch specialized data for data-driven agents. Returns formatted text for prompt."""
        lines = []
        all_syms = []
        for syms in sector_stocks.values():
            all_syms.extend(syms[:8])  # Cap per sector to avoid overload

        if data_focus == "disruption_chain":
            # Disruption Hunter: ask Claude to map dependency chains, then score stocks
            lines.append("\nDISRUPTION DEPENDENCY DATA:")
            lines.append("Your job: find the INFRASTRUCTURE play, not the obvious disruptor.")
            lines.append("Look for: companies supplying compute, memory, networking, power, cooling, or fab capacity")
            lines.append("to the primary disruptors. Lower P/E + tied to megatrend = ideal pick.")
            # Fetch fundamentals for P/E comparison
            for sym in all_syms[:15]:
                try:
                    fund = gw.get_fundamentals(sym)
                    if fund:
                        pe = f"P/E={float(fund.pe_ratio):.1f}" if fund.pe_ratio else "P/E=N/A"
                        mcap = f"MCap=${float(fund.market_cap)/1e9:.0f}B" if fund.market_cap else ""
                        lines.append(f"  {sym}: {pe}, {mcap}")
                except Exception:
                    continue

        elif data_focus == "smart_money":
            # Insider Shadow: fetch insider + congress + institutional data
            lines.append("\nSMART MONEY DATA (Priority: Insider > Congress > Institutional):")
            for sym in all_syms[:12]:
                sym_lines = []
                try:
                    insider = gw.get_insider_summary(sym, days=90)
                    if insider and insider.total_trades > 0:
                        cluster = " *** CLUSTER BUY ***" if insider.cluster_buy else ""
                        sym_lines.append(f"Insider: {insider.total_buys}B/{insider.total_sells}S, signal={insider.signal}{cluster}")
                except Exception:
                    pass
                try:
                    congress = gw.get_congress_summary(sym, days=180)
                    if congress and congress.total_trades > 0:
                        sym_lines.append(f"Congress: {congress.total_buys}B/{congress.total_sells}S, {congress.unique_politicians} politicians, sentiment={congress.net_sentiment}")
                except Exception:
                    pass
                try:
                    inst = gw.get_institutional_summary(sym)
                    if inst and inst.total_institutions > 0:
                        net = "accumulating" if inst.net_change_shares and inst.net_change_shares > 0 else "distributing" if inst.net_change_shares and inst.net_change_shares < 0 else "stable"
                        sym_lines.append(f"Institutional: {inst.total_institutions} holders, {inst.new_positions} new, net={net}")
                except Exception:
                    pass
                if sym_lines:
                    lines.append(f"  {sym}: {' | '.join(sym_lines)}")

            lines.append("\nCONVERGENCE BONUS: If 2+ sources (insider+congress+institutional) agree = highest conviction.")

        elif data_focus == "options_flow":
            # Options Whisperer: fetch options summaries
            lines.append("\nOPTIONS FLOW DATA (Flag: volume/OI >= 3x, PCR < 0.5 or > 1.3):")
            for sym in all_syms[:12]:
                try:
                    opts = gw.get_options_summary(sym)
                    if opts:
                        pcr = f"PCR={opts.put_call_ratio:.2f}" if opts.put_call_ratio else "PCR=N/A"
                        iv = f"IV={opts.avg_iv:.0f}%" if opts.avg_iv else ""
                        sent = opts.sentiment or "neutral"
                        call_vol = opts.total_call_volume or 0
                        put_vol = opts.total_put_volume or 0
                        unusual = ""
                        if opts.unusual_activity:
                            bullish_ua = sum(1 for u in opts.unusual_activity if getattr(u, 'sentiment', '') == 'bullish')
                            bearish_ua = sum(1 for u in opts.unusual_activity if getattr(u, 'sentiment', '') == 'bearish')
                            if bullish_ua or bearish_ua:
                                unusual = f" ** UNUSUAL: {bullish_ua} bullish / {bearish_ua} bearish **"
                        lines.append(f"  {sym}: {pcr}, {iv}, calls={call_vol:,}, puts={put_vol:,}, sentiment={sent}{unusual}")
                except Exception:
                    continue

        elif data_focus == "microstructure":
            # Flow Tracker: fetch Level 2 microstructure
            lines.append("\nORDER FLOW DATA (Look for: buy_ratio > 1.5 + near VWAP + high liquidity):")
            for sym in all_syms[:10]:
                try:
                    micro = gw.get_microstructure(sym)
                    if micro:
                        ratio = f"Buy/Sell={micro.buy_sell_ratio:.2f}" if micro.buy_sell_ratio else ""
                        vwap = f"VWAP=${micro.vwap:.2f}" if micro.vwap else ""
                        liq = f"Liquidity={micro.liquidity_score}" if micro.liquidity_score else ""
                        large = f"LargeTrades={micro.large_trade_count}" if micro.large_trade_count else ""
                        imb = f"Imbalance={micro.order_imbalance:+.2f}" if micro.order_imbalance else ""
                        parts = [p for p in [ratio, vwap, liq, large, imb] if p]
                        if parts:
                            lines.append(f"  {sym}: {', '.join(parts)}")
                except Exception:
                    continue

        return "\n".join(lines) if lines else ""

    def deep_dive(self, symbol: str, hist_data=None) -> AgentPick:
        """Run FULL analysis — 16 indicators + trade plan + all data. No Claude call."""
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

            # Full report with ALL 16 indicators
            try:
                from src.orchestrator import analyze_stock
                report = analyze_stock(symbol, export=False)
                if report:
                    bullish_words = ("buy", "bullish", "positive", "tailwind", "accumulating", "upgrade", "strong buy", "beneficiary")
                    bearish_words = ("sell", "bearish", "negative", "risk", "distributing", "headwind", "downgrade", "at risk")

                    signal_details = []
                    for s in report.sections:
                        cl = s.content.lower()
                        data_score = s.data.get("score", s.data.get("overall", None))
                        try:
                            sn = float(data_score) if data_score is not None else None
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
                            pick.signals_bullish += 1
                        elif direction == "bearish":
                            pick.signals_bearish += 1
                        pick.signals_total += 1

                        signal_details.append(f"{s.title}={direction}")

                    pick.verdict = report.verdict.value
                    pick.confidence = report.confidence
                    pick.risk_rating = report.risk_rating.value
                    pick.sentiment_score = float(report.sentiment_score)
                    pick.signal_details = signal_details
            except Exception:
                pass

            pick.score = score.total_score
            pick.confirmations = score.confirmations
            pick.momentum_override = score.momentum_override

            # Trade plan data
            price = float(tech.current_price) if tech.current_price else 0
            pick.price = price

            # Support / resistance / risk-reward
            support = float(tech.support) if tech.support else None
            resistance = float(tech.resistance) if tech.resistance else None
            if support and resistance and price > 0 and support < price and resistance > price:
                downside = price - support
                upside = resistance - price
                pick.risk_reward = round(upside / downside, 1) if downside > 0 else 0
                pick.support = support
                pick.resistance = resistance
            else:
                pick.risk_reward = 0

            # ATR-based stop
            if tech.atr_stop:
                pick.atr_stop = float(tech.atr_stop)
                pick.atr_stop_pct = tech.atr_stop_pct or 0

            # Short-term signals
            pick.rsi_5 = float(tech.rsi_5) if tech.rsi_5 else None
            pick.ema8_above_ema21 = (float(tech.ema_8) > float(tech.ema_21)) if tech.ema_8 and tech.ema_21 else None
            pick.momentum_3d = tech.momentum_3d
            pick.obv_trend = tech.obv_trend
            pick.macd_divergence = tech.macd_divergence
            pick.seasonality = tech.seasonality_avg

            # Fibonacci
            pick.fib_382 = float(tech.fib_382) if tech.fib_382 else None

            # Summary — comprehensive
            parts = []
            if tech.rsi_14:
                parts.append(f"RSI14={float(tech.rsi_14):.0f}")
            if tech.rsi_5:
                parts.append(f"RSI5={float(tech.rsi_5):.0f}")
            parts.append(tech.trend or "no trend")
            parts.append(f"{pick.signals_bullish}/{pick.signals_total} bullish")
            if pick.risk_reward:
                parts.append(f"R/R {pick.risk_reward}:1")
            if pick.atr_stop_pct:
                parts.append(f"ATR stop {pick.atr_stop_pct}%")
            if tech.obv_trend:
                parts.append(f"OBV {tech.obv_trend}")
            if score.momentum_override:
                parts.append("🚀OVERRIDE")
            pick.deep_dive_summary = ", ".join(parts)

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
        self.max_picks = config.get("max_picks", 5)
        self.min_score = config.get("min_score", 65)
        self.min_backtest = config.get("min_backtest", 60)
        self.max_sector_pct = config.get("max_sector_pct", 30)
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
                    f"  {p.agent_icon} {p.agent_name}: {p.symbol} @ ${p.price:.2f}\n"
                    f"    Score: {p.score}, Verdict: {p.verdict}, Confidence: {p.confidence}, Risk: {p.risk_rating}/5\n"
                    f"    Signals: {p.signals_bullish} bullish / {p.signals_bearish} bearish / {p.signals_total} total\n"
                    f"    Backtest: {p.backtest_win_rate}% win rate ({p.backtest_trades} trades)\n"
                    f"    Confirmations: {p.confirmations}/3{' 🚀OVERRIDE' if p.momentum_override else ''}\n"
                    f"    Trade Plan: Support ${p.support:.2f}, Resistance ${p.resistance:.2f}, R/R {p.risk_reward}:1\n" if p.support and p.resistance else ""
                    f"    ATR Stop: ${p.atr_stop:.2f} ({p.atr_stop_pct}%)\n" if p.atr_stop else ""
                    f"    Short-term: RSI5={p.rsi_5:.0f}, " if p.rsi_5 else ""
                    f"EMA8>21={'yes' if p.ema8_above_ema21 else 'no'}, " if p.ema8_above_ema21 is not None else ""
                    f"Mom3d={p.momentum_3d:+.1f}%, " if p.momentum_3d else ""
                    f"OBV={p.obv_trend}\n" if p.obv_trend else "\n"
                )

        prompt = f"""You are the Risk Manager. Evaluate stock picks from 8 trading agents and build the final portfolio.

AGENTS:
- Opinion-based: Momentum, Value, Contrarian, Macro (analyze charts + fundamentals)
- Data-driven: Disruption Hunter, Insider Shadow, Options Whisperer, Flow Tracker (read real data feeds)
When opinion AND data agents agree on the same stock = HIGHEST CONVICTION.

AGENT PICKS BY SECTOR:
{sector_text}

CURRENT HOLDINGS: {', '.join(existing) if existing else 'None'}

RULES:
- Pick up to {self.max_picks} total (best per sector, can pick multiple from same sector if both strong)
- CONVERGENCE BONUS: if 3+ agents pick the same stock, that's a strong signal — prefer it
- Min score: {self.min_score} (reject below this)
- Min backtest win rate: {self.min_backtest}% (reject unproven)
- Max sector concentration: {self.max_sector_pct}%
- If already holding a stock in this sector: {self.duplicate_action}
- Position size: "full" for high-conviction (3+ agents agree), "half" for single-agent picks

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
    """Orchestrates 8 personality agents + risk manager."""

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

        # All 8 agents run in parallel — each is an independent subprocess
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _run_agent(key_agent):
            key, agent = key_agent
            return key, agent.full_pipeline(sectors, macro_context, stock_db)

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_run_agent, item): item[0] for item in self.agents.items()}
            for future in as_completed(futures):
                try:
                    key, picks = future.result()
                    result.agent_picks[key] = picks
                except Exception:
                    pass

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
