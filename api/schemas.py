"""Pydantic request/response schemas for the API."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


# ── Market ────────────────────────────────────────────────────────


class KpiCard(BaseModel):
    name: str
    value: str
    status: str | None = None
    tone: str = "neutral"   # "green" | "amber" | "red" | "neutral"
    why: str | None = None
    icon: str | None = None


class SectorFlow(BaseModel):
    sector: str
    change_pct: float
    flow: str  # "inflow" | "outflow"
    change_pct_prior: float | None = None
    delta_pp: float | None = None
    accel: str | None = None  # "accelerating" | "decelerating" | "steady" | None


class SectorSummary(BaseModel):
    net: float
    inflow: float
    outflow: float
    gaining: int
    losing: int
    total: int


class YieldCurveSummary(BaseModel):
    two_year: float
    ten_year: float
    spread: float
    inverted: bool
    label: str   # "Inverted" | "Flattening" | "Normal"


class TradingImplication(BaseModel):
    tone: str    # "green" | "amber" | "red"
    text: str


class MarketPulseResponse(BaseModel):
    regime: str
    regime_explanation: str
    kpis: list[KpiCard]
    yield_curve: YieldCurveSummary | None = None
    sectors: list[SectorFlow]
    sector_summary: SectorSummary
    implications: list[TradingImplication]
    period: str
    available_periods: list[str]
    last_updated: str


# ── Economic Calendar ─────────────────────────────────────────────


class CalendarEvent(BaseModel):
    date: str
    name: str
    icon: str
    category: str
    impact: str    # "high" | "medium" | "low"
    days_away: int
    warning: str = ""


class CalendarResponse(BaseModel):
    events: list[CalendarEvent]
    next_event: CalendarEvent | None = None
    next_high_impact: CalendarEvent | None = None
    last_updated: str


# ── Geopolitical Events ───────────────────────────────────────────


class GeopoliticalEvent(BaseModel):
    type: str
    icon: str
    title: str
    snippet: str
    url: str = ""
    severity: str  # "high" | "moderate"
    negative_sectors: list[str] = []
    positive_sectors: list[str] = []
    explanation: str = ""


class GeopoliticalResponse(BaseModel):
    events: list[GeopoliticalEvent]
    last_updated: str


# ── Disruption Themes ─────────────────────────────────────────────


class DisruptionTheme(BaseModel):
    name: str
    icon: str
    intensity: str   # "HIGH" | "MEDIUM" | "EMERGING"
    tickers_benefit: list[str] = []
    sectors_benefit: list[str] = []
    tickers_risk: list[str] = []
    sectors_risk: list[str] = []
    headline: str = ""


class DisruptionResponse(BaseModel):
    themes: list[DisruptionTheme]
    source: str    # "claude" | "fallback"
    last_updated: str


# ── Discover ──────────────────────────────────────────────────────


class Week52Range(BaseModel):
    high: float
    low: float
    position_pct: float   # 0-100 where current price sits in the range


class SubScores(BaseModel):
    volume: float
    price: float
    flow: float
    risk_reward: float


class Confirmations(BaseModel):
    trend_pullback: bool = False
    relative_strength: bool = False
    volume_confirmed: bool = False
    momentum_override: bool = False


class SecondaryStrategy(BaseModel):
    name: str
    icon: str
    description: str = ""


class SparkPoint(BaseModel):
    date: str
    close: float


class OpportunityCard(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    sector_label: str | None = None
    market_cap: str | None = None
    next_earnings: str | None = None
    price: float | None = None
    change_pct: float | None = None
    week52: Week52Range | None = None
    score: float
    label: str
    strategy: str
    strategy_icon: str
    strategy_description: str = ""
    secondary_strategies: list[SecondaryStrategy] = []
    risk_reward_ratio: float | None = None
    sub_scores: SubScores
    confirmations: Confirmations
    confirmation_count: int = 0
    spark: list[SparkPoint] | None = None


class DiscoverResponse(BaseModel):
    opportunities: list[OpportunityCard]
    period: str
    lookback_days: int
    available_periods: list[str]
    popular_top5: list[str]
    last_updated: str


# ── Deep Dive ─────────────────────────────────────────────────────


class SignalRow(BaseModel):
    name: str
    category: str
    icon: str
    color: str
    direction: str  # "bullish" | "bearish" | "neutral"
    strength: float  # 0..1
    explanation: str
    why: str | None = None


class SignalCounts(BaseModel):
    bullish: int = 0
    bearish: int = 0
    neutral: int = 0
    total: int = 0


class PeriodChange(BaseModel):
    period: str
    lookback_days: int
    start_price: float
    end_price: float
    change_pct: float
    spark: list[SparkPoint] = []


class TradePlan(BaseModel):
    price: float
    entry: float
    stop_loss: float
    target1: float
    target2: float
    support: float | None = None
    resistance: float | None = None
    stop_pct: float
    target1_pct: float
    target2_pct: float
    risk_per_share: float
    risk_reward: float
    account_size: float
    risk_pct: float
    shares: int
    position_value: float
    profit_t1: float
    profit_t2: float
    loss_at_stop: float
    alignment_pct: int
    alignment_dominant: str  # "bullish" | "bearish"
    alignment_bull: int
    alignment_bear: int
    alignment_neutral: int
    alignment_total: int
    timing_good: list[str] = []
    timing_warn: list[str] = []
    risks: list[str] = []


class EarningsRow(BaseModel):
    date: str | None = None
    eps_estimate: float | None = None
    eps_actual: float | None = None
    surprise_pct: float | None = None


class VolumeProfileRow(BaseModel):
    price: float
    volume: float


class VolumeProfile(BaseModel):
    rows: list[VolumeProfileRow]
    poc: float | None = None
    last_price: float
    period_days: int
    bin_size: float


class CompareRow(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    verdict: str | None = None
    confidence: str | None = None
    risk_rating: int | None = None
    sentiment_score: float | None = None
    price: float | None = None
    change_pct: float | None = None
    spark: list[SparkPoint] = []
    bullish_signals: int = 0
    bearish_signals: int = 0
    total_signals: int = 0
    pe_ratio: float | None = None
    dividend_yield: float | None = None
    from_cache: bool = False
    error: str | None = None


class CompareResponse(BaseModel):
    rows: list[CompareRow]
    period: str
    available_periods: list[str]
    last_updated: str


class DeepDiveResponse(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    verdict: str
    confidence: str
    risk_rating: int
    risk_label: str
    price: float | None = None
    period_change: PeriodChange | None = None
    summary: str | None = None
    sentiment_score: float | None = None
    signals: list[SignalRow]
    signal_groups: dict[str, list[SignalRow]] = {}
    signal_counts: SignalCounts
    trade_plan: TradePlan | None = None
    earnings: list[EarningsRow] = []
    volume_profile: VolumeProfile | None = None
    available_periods: list[str]
    period: str
    signal_filter: str
    last_updated: str
    cached_at: str | None = None
    from_cache: bool = False


# ── Backtest ──────────────────────────────────────────────────────


class BacktestRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10)
    signal: str
    hold_days: int = Field(default=20, ge=1, le=200)


class BacktestTrade(BaseModel):
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    return_pct: float


class BacktestResponse(BaseModel):
    symbol: str
    signal: str
    win_rate: float
    avg_return: float
    total_trades: int
    trades: list[BacktestTrade]


class SignalCatalogItem(BaseModel):
    name: str
    label: str
    description: str
    direction: str    # "buy" | "sell"
    category: str


class SignalCatalogResponse(BaseModel):
    signals: list[SignalCatalogItem]
    categories: list[str]
    category_signals: dict[str, list[str]]


class FullBacktestTrade(BaseModel):
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    pnl_percent: float
    hold_days: int
    outcome: str   # "win" | "loss"


class SignalResultRow(BaseModel):
    signal_name: str
    description: str
    category: str
    direction: str
    win_rate: float
    avg_return: float
    total_trades: int
    max_gain: float
    max_loss: float
    grade: str
    trades: list[FullBacktestTrade] = []


class AllSignalsResponse(BaseModel):
    symbol: str
    period: str
    hold_days: int
    category: str
    results: list[SignalResultRow]
    available_periods: list[str] = []
    available_categories: list[str] = []
    error: str | None = None
    last_updated: str


class Candle(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class SingleBacktestResponse(BaseModel):
    symbol: str
    signal: str
    signal_label: str
    signal_description: str
    period: str
    hold_days: int
    result: SignalResultRow | None = None
    candles: list[Candle] = []
    error: str | None = None
    last_updated: str | None = None


class MultiStockRow(BaseModel):
    symbol: str
    signal_name: str | None = None
    description: str | None = None
    category: str | None = None
    direction: str | None = None
    win_rate: float | None = None
    avg_return: float | None = None
    total_trades: int | None = None
    max_gain: float | None = None
    max_loss: float | None = None
    grade: str | None = None
    error: str | None = None


class MultiStockResponse(BaseModel):
    signal: str
    signal_label: str
    signal_description: str
    period: str
    hold_days: int
    rows: list[MultiStockRow]
    last_updated: str


# ── Portfolio Simulation ──────────────────────────────────────────


class PortfolioSimRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=12)
    strategy: str
    initial_capital: float = Field(default=100_000, ge=1_000, le=10_000_000)
    position_size_pct: float = Field(default=0.20, ge=0.01, le=1.0)


class PortfolioEquityPoint(BaseModel):
    date: str
    total_value: float
    cash: float
    invested: float
    daily_return: float
    cumulative_return: float
    benchmark_return: float


class PortfolioTradeRow(BaseModel):
    symbol: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    pnl_percent: float
    hold_days: int
    outcome: str


class PortfolioBestTrade(BaseModel):
    symbol: str
    pnl_percent: float
    entry_date: str
    exit_date: str


class PortfolioSimResponse(BaseModel):
    strategy: str | None = None
    symbols: list[str] = []
    initial_capital: float = 0
    final_value: float = 0
    total_return: float = 0
    annualized_return: float = 0
    sharpe_ratio: float = 0
    max_drawdown: float = 0
    win_rate: float = 0
    total_trades: int = 0
    alpha: float = 0
    best_trade: PortfolioBestTrade | None = None
    worst_trade: PortfolioBestTrade | None = None
    equity_curve: list[PortfolioEquityPoint] = []
    trades: list[PortfolioTradeRow] = []
    error: str | None = None
    last_updated: str | None = None


# ── AI Analyst ────────────────────────────────────────────────────


class AiAnalystRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10)
    period: str = Field("1M", pattern="^(1D|1W|1M|3M|6M|1Y)$")
    cycles: int = Field(default=12, ge=3, le=24)
    mode: str = Field(default="single", pattern="^(single|multi)$")


class AgentVote(BaseModel):
    agent: str
    vote: str    # "BUY" | "SELL" | "HOLD"
    reason: str = ""
    raw: str = ""


class AiTradePlanSnapshot(BaseModel):
    entry: float
    stop: float
    target1: float
    target2: float
    risk_per_share: float
    rr: float
    stop_pct: float


class AiDecision(BaseModel):
    date: str
    price: float
    decision: str    # "BUY" | "SELL" | "HOLD"
    action: str      # "OPEN" | "CLOSE" | "HOLD"
    raw_response: str = ""
    rsi: float | None = None
    pnl_percent: float | None = None
    regime: str | None = None
    sentiment: str | None = None
    trade_plan: AiTradePlanSnapshot | None = None
    prompt: str = ""
    agent_votes: list[AgentVote] = []


class AiAnalystResponse(BaseModel):
    symbol: str
    period: str
    mode: str = "single"
    agents_used: list[str] = []
    hold_days: int = 0
    cycles_run: int = 0
    decisions: list[AiDecision] = []
    trades: list[PortfolioTradeRow] = []
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0
    avg_return: float = 0
    total_trades: int = 0
    error: str | None = None
    last_updated: str | None = None


# ── AI Analyst — multi-stock ──────────────────────────────────────


class AiAnalystMultiRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=8)
    period: str = Field("1M", pattern="^(1D|1W|1M|3M|6M|1Y)$")
    cycles: int = Field(default=8, ge=3, le=24)
    mode: str = Field(default="single", pattern="^(single|multi)$")


class AiAnalystMultiResponse(BaseModel):
    period: str
    mode: str
    cycles: int
    rows: list[AiAnalystResponse] = []
    error: str | None = None
    last_updated: str | None = None


# ── Agent ─────────────────────────────────────────────────────────


class AgentStatus(BaseModel):
    enabled: bool
    last_run: str | None = None
    portfolio_value: float
    open_positions: int
    rebalance_frequency: str
    next_run: str | None = None
    overdue: bool = False


class AgentDecision(BaseModel):
    timestamp: str
    symbol: str
    action: str
    quantity: float | None = None
    reason: str | None = None


class AgentConfig(BaseModel):
    starting_capital: float
    current_cash: float
    risk_per_trade: float
    max_positions: int
    max_buys_per_cycle: int
    min_opportunity_score: int
    stop_loss_pct: float
    rebalance_frequency: str
    status: str
    last_run: str | None = None


class AgentConfigUpdate(BaseModel):
    starting_capital: float | None = None
    risk_per_trade: float | None = None
    max_positions: int | None = None
    max_buys_per_cycle: int | None = None
    min_opportunity_score: int | None = None
    stop_loss_pct: float | None = None
    rebalance_frequency: str | None = None


class AgentResetRequest(BaseModel):
    starting_capital: float = Field(100_000, ge=1_000)
    risk_per_trade: float = Field(0.02, ge=0.001, le=0.20)
    max_positions: int = Field(8, ge=1, le=20)
    max_buys_per_cycle: int = Field(3, ge=1, le=10)
    min_opportunity_score: int = Field(60, ge=0, le=100)
    stop_loss_pct: float = Field(12.0, ge=1.0, le=50.0)


class AgentPersonality(BaseModel):
    key: str
    name: str
    icon: str
    color: str
    tagline: str
    philosophy: str
    strengths: list[str] = []
    weaknesses: list[str] = []
    prioritizes: list[str] = []
    avoids: list[str] = []
    backtest_signals: list[str] = []
    risk_tolerance: str = ""
    ideal_market: str = ""
    historical_edge: str = ""
    kind: str   # "opinion" | "data"


class RiskManagerInfo(BaseModel):
    name: str
    icon: str
    color: str
    tagline: str
    philosophy: str
    checks: list[str] = []


class AgentPersonalitiesResponse(BaseModel):
    agents: list[AgentPersonality]
    risk_manager: RiskManagerInfo


class AgentPosition(BaseModel):
    symbol: str
    direction: str = "long"
    shares: float
    entry_price: float
    entry_date: str | None = None
    stop_loss: float | None = None
    target: float | None = None
    current_price: float
    pnl: float
    pnl_pct: float
    ai_reasoning: str = ""


class AgentEquityPoint(BaseModel):
    date: str
    total_value: float
    cash: float
    invested: float
    cumulative_return: float
    benchmark_value: float | None = None


class AgentEquityMetrics(BaseModel):
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    alpha: float


class AgentEquityResponse(BaseModel):
    points: list[AgentEquityPoint]
    metrics: AgentEquityMetrics


class AgentCycleResult(BaseModel):
    ok: bool
    trades_executed: int = 0
    portfolio_value: float = 0
    summary: str = ""
    error: str | None = None


class MultiAgentPick(BaseModel):
    sector: str | None = None
    symbol: str
    agent: str | None = None
    score: float
    reasoning: str = ""


class SectorWinner(BaseModel):
    symbol: str
    agent: str
    score: float


class MultiAgentResult(BaseModel):
    ok: bool
    timestamp: str | None = None
    macro_context: str = ""
    sectors_analyzed: list[str] = []
    agent_picks: dict[str, list[MultiAgentPick]] = {}
    sector_winners: dict[str, SectorWinner] = {}
    final_portfolio: list[MultiAgentPick] = []
    risk_manager_reasoning: str = ""
    error: str | None = None


class MultiAgentRunRequest(BaseModel):
    rm_picks: int = Field(5, ge=1, le=12)
    min_score: int = Field(60, ge=0, le=100)


# ── Chain of Thought + Lifecycle ──────────────────────────────────


class CotStep(BaseModel):
    step: str = ""
    symbol: str = ""
    decision: str = ""
    reasoning: str = ""
    created_at: str = ""


class CotRun(BaseModel):
    run_date: str
    steps: list[CotStep] = []


class CotResponse(BaseModel):
    runs: list[CotRun] = []


class AgentLifecycle(BaseModel):
    ok: bool
    status: str


# ── Portfolio AI Agent (live pick) ────────────────────────────────


class PortfolioAgentRequest(BaseModel):
    top_n: int = Field(default=15, ge=5, le=30)
    min_agents: int = Field(default=3, ge=2, le=7)


class CandidateScreen(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    price: float | None = None
    rsi: float | None = None
    change_5d: float | None = None
    change_20d: float | None = None
    vol_ratio: float | None = None
    opportunity_score: int = 0
    opportunity_label: str = "—"
    strategy: str = "Neutral"
    bull_signals: int = 0
    bear_signals: int = 0
    alignment_pct: int = 0
    dominant: str = "neutral"


class StockPick(BaseModel):
    symbol: str
    reason: str = ""


class AgentVotePicks(BaseModel):
    agent: str
    picks: list[StockPick] = []
    raw: str = ""


class ConsensusVote(BaseModel):
    agent: str
    reason: str = ""


class ConsensusPick(BaseModel):
    symbol: str
    agent_count: int
    votes: list[ConsensusVote] = []


class PortfolioAgentConfig(BaseModel):
    top_n: int
    min_agents_for_consensus: int
    max_picks_per_agent: int
    agents: list[str] = []


class PortfolioAgentResponse(BaseModel):
    timestamp: str
    universe_size: int
    error: str | None = None
    candidates_screened: list[CandidateScreen] = []
    agent_votes: list[AgentVotePicks] = []
    consensus_picks: list[ConsensusPick] = []
    final_portfolio: list[ConsensusPick] = []
    config: PortfolioAgentConfig | None = None


class PortfolioExecuteRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list, max_length=15)
    reasons: dict[str, str] = Field(default_factory=dict)


class ExecutedTrade(BaseModel):
    symbol: str
    action: str
    shares: int = 0
    price: float = 0.0


class SkippedTrade(BaseModel):
    symbol: str
    reason: str


class PortfolioExecuteResponse(BaseModel):
    timestamp: str
    run_date: str
    executed: list[ExecutedTrade] = []
    skipped: list[SkippedTrade] = []
    cash_remaining: float
    open_positions: int
    max_positions: int


# ── Walk-forward simulation ────────────────────────────────────────


class WalkForwardSimRequest(BaseModel):
    start_date: str
    end_date: str
    cycle_days: int = Field(default=14, ge=5, le=60)
    initial_capital: float = Field(default=100_000.0, ge=1000)
    max_positions: int = Field(default=5, ge=1, le=10)
    min_agents: int = Field(default=3, ge=2, le=7)
    top_n: int = Field(default=12, ge=5, le=30)
    position_size_pct: float = Field(default=0.10, gt=0.0, le=0.5)


class SimEquityPoint(BaseModel):
    date: str
    equity: float


class SimVoter(BaseModel):
    agent: str
    reason: str = ""


class SimTrade(BaseModel):
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    pnl_pct: float
    consensus_count: int
    voters: list[SimVoter] = []


class SimOpenedPick(BaseModel):
    symbol: str
    shares: int
    entry_price: float
    entry_date: str
    consensus_count: int


class SimCycleAgentVote(BaseModel):
    agent: str
    picks: list[StockPick] = []
    raw: str = ""


class SimCycleLog(BaseModel):
    cycle_index: int
    date: str
    skipped: str | None = None
    candidates_screened: list[CandidateScreen] = []
    agent_votes: list[SimCycleAgentVote] = []
    consensus_picks: list[ConsensusPick] = []
    opened: list[SimOpenedPick] = []


class PortfolioSimSummary(BaseModel):
    initial_capital: float
    final_equity: float
    total_return_pct: float
    total_trades: int
    winners: int
    win_rate: float
    avg_pnl_pct: float
    cycles_run: int


class PortfolioSimConfig(BaseModel):
    start_date: str
    end_date: str
    cycle_days: int
    initial_capital: float
    max_positions: int
    min_agents: int
    top_n: int
    position_size_pct: float
    agents: list[str] = []


class WalkForwardSimResponse(BaseModel):
    error: str | None = None
    config: PortfolioSimConfig | None = None
    summary: PortfolioSimSummary | None = None
    equity_curve: list[SimEquityPoint] = []
    trades: list[SimTrade] = []
    cycles: list[SimCycleLog] = []


# ── Stock search ──────────────────────────────────────────────────


class StockSearchResult(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None


# ── Generic ───────────────────────────────────────────────────────


class JobStartResponse(BaseModel):
    job_id: str
    status: str = "started"


# ── Alerts ────────────────────────────────────────────────────────


class AlertItem(BaseModel):
    id: int | None = None
    symbol: str = ""
    alert_type: str = ""
    message: str = ""
    old_value: str | None = None
    new_value: str | None = None
    severity: str = "info"   # "critical" | "warning" | "info"
    created_at: str = ""


class AlertSummary(BaseModel):
    total: int = 0
    critical: int = 0
    warning: int = 0
    last_24h: int = 0


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "trading-api"
    version: str = "0.1.0"


# ── Data Sources / Rate Limits ────────────────────────────────────


class DataSourceStatus(BaseModel):
    source: str             # display name, e.g. "Alpha Vantage"
    key: str                # api_log source key, e.g. "alphavantage"
    used: int               # calls observed in the window
    capacity: int | None    # published limit; null means untracked
    window_seconds: int
    status: str             # "ok" | "warning" | "limited" | "untracked"


class DataSourcesResponse(BaseModel):
    sources: list[DataSourceStatus]
    any_limited: bool       # convenience flag for the UI banner


# ── Universe (knowledge-graph prototype) ─────────────────────────


class IndustryTag(BaseModel):
    code: str
    sector: str | None = None
    weight: float = 1.0
    is_primary: bool = True


class UniverseStock(BaseModel):
    symbol: str
    name: str | None = None
    tier: str               # 'A' | 'B' | 'C' | 'D'
    exchange: str | None = None
    country: str | None = None
    market_cap: float | None = None
    avg_dollar_volume: float | None = None
    in_sp500: bool = False
    in_russell1000: bool = False
    in_russell2000: bool = False
    in_tsx60: bool = False
    in_qqq: bool = False
    industries: list[IndustryTag] = []


class TierCounts(BaseModel):
    A: int = 0
    B: int = 0
    C: int = 0
    D: int = 0
    total: int = 0


class UniverseResponse(BaseModel):
    stocks: list[UniverseStock]
    counts: TierCounts
    filters_applied: dict[str, str | None] = {}


# ── News Impact (knowledge-graph prototype Phase 2) ──────────────


class NewsImpactRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


class NewsImpactStock(BaseModel):
    symbol: str
    name: str | None = None
    tier: str
    sector: str | None = None
    industry_code: str | None = None
    polarity: float       # -1..1
    strength: float       # 0..1
    composite_score: float
    contributing_keywords: list[str] = []
    contributing_industries: list[str] = []
    direct_target: bool = False


class NewsImpactIndustry(BaseModel):
    industry_code: str
    polarity: float
    strength: float
    contributing_keywords: list[str] = []
    contributing_domains: list[str] = []


class NewsImpactResponse(BaseModel):
    stocks: list[NewsImpactStock]
    industries: list[NewsImpactIndustry]
    matched_keywords: list[str] = []
    matched_countries: list[str] = []
    matched_symbols: list[str] = []
    negated_keywords: list[str] = []


# ── Graph: peers (Phase 3) ──────────────────────────────────────


class PeerEdge(BaseModel):
    symbol: str                                 # the peer's ticker
    name: str | None = None
    tier: str | None = None                     # tier of the peer stock
    sector: str | None = None
    industry_code: str | None = None
    similarity: float                           # 0..1
    overlap_dimensions: list[str] = []          # ["cloud", "ai", ...] (Tier A only typically)
    source: str                                 # 'hand' | 'claude_batch' | 'claude_validated'
    confidence: str                             # 'high' | 'medium' | 'low'
    evidence: str | None = None                 # short rationale


class PeerListResponse(BaseModel):
    symbol: str                                 # the stock the peers were queried for
    name: str | None = None
    tier: str | None = None
    peers: list[PeerEdge] = []
    total: int


# ── Graph: neighborhood (Phase 4) ───────────────────────────────


class NeighborEdge(BaseModel):
    symbol: str
    name: str | None = None
    tier: str | None = None
    sector: str | None = None
    edge_type: str          # 'supplier' | 'customer' | 'peer' | 'substitute' | 'complement'
    strength: float
    polarity: float
    confidence: str
    source: str
    evidence: str | None = None


class NeighborhoodResponse(BaseModel):
    symbol: str
    name: str | None = None
    tier: str | None = None
    sector: str | None = None
    suppliers:   list[NeighborEdge] = []     # upstream — what this stock depends on
    customers:   list[NeighborEdge] = []     # downstream — who buys from this stock
    peers:       list[NeighborEdge] = []
    substitutes: list[NeighborEdge] = []     # zero-sum substitutes (polarity -1)
    complements: list[NeighborEdge] = []     # co-purchased / paired demand


# ── Phase 7A: ownership ─────────────────────────────────────────


class HolderRow(BaseModel):
    cik: str
    institution_name: str | None = None
    institution_type: str | None = None
    value_usd: float | None = None
    pct_portfolio: float | None = None
    pct_outstanding: float | None = None
    as_of: str
    source: str | None = None


class TopHoldersResponse(BaseModel):
    symbol: str
    holders: list[HolderRow] = []
    total: int


class HoldingRow(BaseModel):
    symbol: str
    stock_name: str | None = None
    tier: str | None = None
    value_usd: float | None = None
    pct_portfolio: float | None = None
    pct_outstanding: float | None = None
    rank_in_portfolio: int | None = None
    as_of: str


class InstitutionHoldingsResponse(BaseModel):
    cik: str
    name: str | None = None
    type: str | None = None
    total_aum: float | None = None
    holdings: list[HoldingRow] = []
    total: int


# ── Phase 7B: edge freshness ────────────────────────────────────


class FreshnessQueueRow(BaseModel):
    symbol: str
    status: str                            # 'fresh' | 'aging' | 'needs_review' | 'stale'
    trigger_reason: str | None = None
    flagged_at: str | None = None
    last_extracted_at: str | None = None


class FreshnessQueueResponse(BaseModel):
    queue: list[FreshnessQueueRow]
    counts_by_status: dict[str, int] = {}


# ── Risk narrative + earnings explainer ───────────────────────────


class RiskNarrativeResponse(BaseModel):
    symbol: str
    industry_threats: str = ""
    competitive_risks: str = ""
    balance_sheet: str = ""
    macro_exposure: str = ""
    worst_case: str = ""
    invalidates_if: str = ""
    risk_rating: int | None = None
    risk_label: str | None = None
    error: str | None = None
    raw: str | None = None
    from_cache: bool = False


class EarningsExplainRequest(BaseModel):
    symbol: str = Field("", max_length=10)
    text: str = Field(..., min_length=1, max_length=15000)


class EarningsExplainResponse(BaseModel):
    symbol: str
    summary: str = ""
    beats: list[str] = []
    misses: list[str] = []
    guidance: str = ""
    case_change: str = "unchanged"
    case_change_reason: str = ""
    input_chars: int | None = None
    error: str | None = None
    raw: str | None = None


class BubbleScoreComponents(BaseModel):
    growth_gap: float
    valuation: float
    momentum: float


class BubbleScoreMetrics(BaseModel):
    price_change_1y_pct: float | None = None
    price_change_3m_pct: float | None = None
    revenue_growth_pct: float | None = None
    earnings_growth_pct: float | None = None
    growth_gap_pct: float | None = None
    vibes_share_pct: float | None = None
    fundamental_growth_pct: float | None = None
    pe_ratio: float | None = None
    ps_ratio: float | None = None
    pb_ratio: float | None = None
    pfcf_ratio: float | None = None


class BubbleScoreResponse(BaseModel):
    symbol: str
    score: float
    label: str
    components: BubbleScoreComponents
    metrics: BubbleScoreMetrics
    verdict: str
    reasons: list[str] = []
    last_updated: str
    from_cache: bool = False


class BullNarrativeResponse(BaseModel):
    symbol: str
    growth_drivers: str = ""
    competitive_moat: str = ""
    multiple_expansion: str = ""
    catalysts: str = ""
    best_case: str = ""
    invalidates_if: str = ""
    error: str | None = None
    raw: str | None = None
    from_cache: bool = False


class AnalystRatingsBreakdown(BaseModel):
    strong_buy: int = 0
    buy: int = 0
    hold: int = 0
    sell: int = 0
    strong_sell: int = 0


class AnalystConsensusResponse(BaseModel):
    symbol: str
    rating: str | None = None
    rating_mean: float | None = None
    analyst_count: int | None = None
    current_price: float | None = None
    target_mean: float | None = None
    target_high: float | None = None
    target_low: float | None = None
    upside_pct: float | None = None
    ratings_breakdown: AnalystRatingsBreakdown = AnalystRatingsBreakdown()
    error: str | None = None
    last_updated: str
    from_cache: bool = False


class PeerValuationRow(BaseModel):
    symbol: str
    is_self: bool = False
    pe_ratio: float | None = None
    ps_ratio: float | None = None
    pfcf_ratio: float | None = None
    price_change_1y_pct: float | None = None


class PeerValuationMedians(BaseModel):
    pe_ratio: float | None = None
    ps_ratio: float | None = None
    pfcf_ratio: float | None = None
    price_change_1y_pct: float | None = None


class PeerValuationResponse(BaseModel):
    symbol: str
    rows: list[PeerValuationRow]
    medians: PeerValuationMedians
    last_updated: str
    from_cache: bool = False


# ── Smart-money flow ──────────────────────────────────────────────


class TopHolderRow(BaseModel):
    name: str | None = None
    type: str | None = None
    value_usd: float | None = None
    pct_outstanding: float | None = None
    pct_portfolio: float | None = None
    as_of: str | None = None


class InsiderTradeRow(BaseModel):
    filer: str
    title: str | None = None
    transaction: str | None = None
    shares: int | None = None
    price: float | None = None
    value_usd: float | None = None
    transaction_date: str | None = None
    filing_date: str | None = None


class CongressTradeRow(BaseModel):
    politician: str
    party: str | None = None
    chamber: str | None = None
    state: str | None = None
    transaction: str | None = None
    amount_range: str | None = None
    amount_low_usd: float | None = None
    amount_high_usd: float | None = None
    trade_date: str | None = None
    filed_date: str | None = None
    days_to_file: int | None = None
    committees: list[str] = []


class InstitutionalSection(BaseModel):
    top_holders: list[TopHolderRow] = []
    total_known_holders: int = 0
    error: str | None = None


class InsiderSection(BaseModel):
    total_trades: int = 0
    total_buys: int = 0
    total_sells: int = 0
    unique_insiders: int = 0
    cluster_buy: bool = False
    buy_value_usd: float | None = None
    sell_value_usd: float | None = None
    net_value_usd: float | None = None
    signal: str = ""
    recent_trades: list[InsiderTradeRow] = []
    error: str | None = None


class CongressSection(BaseModel):
    total_trades: int = 0
    total_buys: int = 0
    total_sells: int = 0
    unique_politicians: int = 0
    net_sentiment: str = "neutral"
    top_buyers: list[str] = []
    top_sellers: list[str] = []
    recent_trades: list[CongressTradeRow] = []
    party_breakdown: dict[str, dict[str, int]] = {}
    error: str | None = None


class SmartMoneyResponse(BaseModel):
    symbol: str
    institutional: InstitutionalSection
    insider: InsiderSection
    congress: CongressSection
    summary: str
    last_updated: str
    from_cache: bool = False


# ── News feed + catalyst calendar ─────────────────────────────────


class NewsFeedItem(BaseModel):
    title: str
    snippet: str = ""
    url: str = ""
    source: str = ""
    sentiment: str = "neutral"
    sentiment_score: float = 0.0
    published: str | None = None


class NewsFeedResponse(BaseModel):
    symbol: str
    items: list[NewsFeedItem] = []
    bull_count: int = 0
    bear_count: int = 0
    neutral_count: int = 0
    net_sentiment: str = "no coverage"
    net_score: float = 0.0
    last_updated: str
    from_cache: bool = False


class CatalystEvent(BaseModel):
    date: str
    days_out: int
    title: str
    kind: str        # "earnings" | "dividend" | "macro" | "split"
    weight: str      # "low" | "med" | "high" | "very_high"
    detail: str | None = None
    symbol_specific: bool = True


class CatalystCalendarResponse(BaseModel):
    symbol: str
    horizon_days: int
    events: list[CatalystEvent] = []
    earnings_count: int = 0
    macro_count: int = 0
    dividend_count: int = 0
    last_updated: str
    from_cache: bool = False


class BenchmarkSparkPoint(BaseModel):
    date: str
    close: float
    idx: float


class BenchmarksResponse(BaseModel):
    symbol: str
    period: str
    sector: str | None = None
    sector_etf: str | None = None
    spy_spark: list[BenchmarkSparkPoint] = []
    sector_spark: list[BenchmarkSparkPoint] = []
    last_updated: str
    from_cache: bool = False


# ── Risk-adjusted recommendation ──────────────────────────────────


class RecommendationComponents(BaseModel):
    verdict: str | None = None
    risk_rating: int | None = None
    bubble_score: float | None = None
    bubble_label: str | None = None
    analyst_rating: str | None = None
    analyst_upside: float | None = None
    analyst_target: float | None = None
    insider: str | None = None
    congress: str | None = None
    price: float | None = None


class RecommendationResponse(BaseModel):
    symbol: str
    action: str          # STRONG_BUY | BUY | BUY_ON_DIP | HOLD | TRIM | SELL | STRONG_SELL
    action_label: str
    tone: str            # strong_bullish | bullish | cautious_bullish | neutral | cautious_bearish | bearish | strong_bearish
    headline: str
    reasoning: str
    wait_until_price: float | None = None
    wait_reason: str | None = None
    reevaluate: str | None = None
    components: RecommendationComponents
    last_updated: str
    from_cache: bool = False


# ── Per-signal empirical evidence ─────────────────────────────────


class SignalEvidenceItem(BaseModel):
    signal_key: str | None = None
    win_rate: float | None = None
    avg_return_pct: float | None = None
    total_trades: int | None = None
    max_gain_pct: float | None = None
    max_loss_pct: float | None = None
    hold_days: int | None = None
    grade: str | None = None
    error: str | None = None


class SignalEvidenceResponse(BaseModel):
    symbol: str
    hold_days: int
    signals_tested: int = 0
    signals_total: int = 0
    evidence: dict[str, SignalEvidenceItem] = {}
    last_updated: str
    from_cache: bool = False


# ── Market dashboard / takeaway / news ────────────────────────────


class MarketStatus(BaseModel):
    status: str          # open | pre_market | after_hours | closed
    label: str
    minutes_to_open: int | None = None
    minutes_to_close: int | None = None


class IndexSnapshot(BaseModel):
    key: str
    ticker: str
    display: str
    price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    spark: list[float] = []           # last 30 daily closes
    change_30d_pct: float | None = None


class BreadthMetrics(BaseModel):
    spy_vs_rsp_1m_pp: float | None = None
    iwm_vs_spy_1m_pp: float | None = None
    vix_level: float | None = None
    vix_regime: str | None = None
    spy_pct_above_50d: float | None = None
    spy_pct_above_200d: float | None = None
    headline: str = ""


class MoverRow(BaseModel):
    symbol: str
    price: float
    change_pct: float
    change: float


class TopMovers(BaseModel):
    gainers_1d: list[MoverRow] = []
    losers_1d: list[MoverRow] = []
    gainers_5d: list[MoverRow] = []
    losers_5d: list[MoverRow] = []
    error: str | None = None


class MarketDashboardResponse(BaseModel):
    status: MarketStatus
    indices: list[IndexSnapshot] = []
    breadth: BreadthMetrics
    movers: TopMovers
    last_updated: str
    from_cache: bool = False


class MarketTakeawayResponse(BaseModel):
    regime: str
    stance: str
    tone: str
    headline: str
    bullets: list[str] = []
    last_updated: str
    from_cache: bool = False


class MarketNewsItem(BaseModel):
    title: str
    snippet: str = ""
    url: str = ""
    source: str = ""
    sentiment: str = "neutral"
    sentiment_score: float = 0.0
    published: str | None = None


class MarketNewsResponse(BaseModel):
    items: list[MarketNewsItem] = []
    bull_count: int = 0
    bear_count: int = 0
    neutral_count: int = 0
    net_sentiment: str = "no coverage"
    net_score: float = 0.0
    provider: str | None = None
    source_warning: str | None = None
    last_updated: str
    from_cache: bool = False
