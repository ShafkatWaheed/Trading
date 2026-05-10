// Mirrors api/schemas.py — kept tiny + flat for the dashboard.

export type Tone = "green" | "amber" | "red" | "neutral";

export type KpiCard = {
  name: string;
  value: string;
  status?: string | null;
  tone: Tone;
  why?: string | null;
  icon?: string | null;
};

export type SectorFlow = {
  sector: string;
  change_pct: number;
  flow: "inflow" | "outflow";
};

export type SectorSummary = {
  net: number;
  inflow: number;
  outflow: number;
  gaining: number;
  losing: number;
  total: number;
};

export type YieldCurveSummary = {
  two_year: number;
  ten_year: number;
  spread: number;
  inverted: boolean;
  label: "Inverted" | "Flattening" | "Normal";
};

export type TradingImplication = {
  tone: "green" | "amber" | "red";
  text: string;
};

export type MarketPulse = {
  regime: string;
  regime_explanation: string;
  kpis: KpiCard[];
  yield_curve?: YieldCurveSummary | null;
  sectors: SectorFlow[];
  sector_summary: SectorSummary;
  implications: TradingImplication[];
  period: string;
  available_periods: string[];
  last_updated: string;
};

export type CalendarEvent = {
  date: string;
  name: string;
  icon: string;
  category: string;
  impact: "high" | "medium" | "low";
  days_away: number;
  warning?: string;
};

export type CalendarPayload = {
  events: CalendarEvent[];
  last_updated: string;
};

export type GeopoliticalEvent = {
  type: string;
  icon: string;
  title: string;
  snippet: string;
  url?: string;
  severity: "high" | "moderate";
  negative_sectors: string[];
  positive_sectors: string[];
  explanation: string;
};

export type GeopoliticalPayload = {
  events: GeopoliticalEvent[];
  last_updated: string;
};

export type DisruptionTheme = {
  name: string;
  icon: string;
  intensity: "HIGH" | "MEDIUM" | "EMERGING";
  tickers_benefit: string[];
  sectors_benefit: string[];
  tickers_risk: string[];
  sectors_risk: string[];
  headline: string;
};

export type DisruptionPayload = {
  themes: DisruptionTheme[];
  source: "claude" | "fallback";
  last_updated: string;
};

export type Week52Range = { high: number; low: number; position_pct: number };

export type SubScores = {
  volume: number;
  price: number;
  flow: number;
  risk_reward: number;
};

export type Confirmations = {
  trend_pullback: boolean;
  relative_strength: boolean;
  volume_confirmed: boolean;
  momentum_override: boolean;
};

export type SecondaryStrategy = {
  name: string;
  icon: string;
  description: string;
};

export type SparkPoint = { date: string; close: number };

export type OpportunityCard = {
  symbol: string;
  name?: string | null;
  sector?: string | null;
  sector_label?: string | null;
  market_cap?: string | null;
  next_earnings?: string | null;
  price?: number | null;
  change_pct?: number | null;
  week52?: Week52Range | null;
  score: number;
  label: string;
  strategy: string;
  strategy_icon: string;
  strategy_description: string;
  secondary_strategies: SecondaryStrategy[];
  risk_reward_ratio?: number | null;
  sub_scores: SubScores;
  confirmations: Confirmations;
  confirmation_count: number;
  spark?: SparkPoint[] | null;
};

export type DiscoverPayload = {
  opportunities: OpportunityCard[];
  period: string;
  lookback_days: number;
  available_periods: string[];
  popular_top5: string[];
  last_updated: string;
};

export type WatchlistEntry = { symbol: string };

export type SignalRow = {
  name: string;
  category: string;
  icon: string;
  color: string;
  direction: "bullish" | "bearish" | "neutral";
  strength: number;
  explanation: string;
  why?: string | null;
};

export type SignalCounts = {
  bullish: number;
  bearish: number;
  neutral: number;
  total: number;
};

export type PeriodChange = {
  period: string;
  lookback_days: number;
  start_price: number;
  end_price: number;
  change_pct: number;
  spark: SparkPoint[];
};

export type TradePlan = {
  price: number;
  entry: number;
  stop_loss: number;
  target1: number;
  target2: number;
  support?: number | null;
  resistance?: number | null;
  stop_pct: number;
  target1_pct: number;
  target2_pct: number;
  risk_per_share: number;
  risk_reward: number;
  account_size: number;
  risk_pct: number;
  shares: number;
  position_value: number;
  profit_t1: number;
  profit_t2: number;
  loss_at_stop: number;
  alignment_pct: number;
  alignment_dominant: "bullish" | "bearish";
  alignment_bull: number;
  alignment_bear: number;
  alignment_neutral: number;
  alignment_total: number;
  timing_good: string[];
  timing_warn: string[];
  risks: string[];
};

export type EarningsRow = {
  date?: string | null;
  eps_estimate?: number | null;
  eps_actual?: number | null;
  surprise_pct?: number | null;
};

export type VolumeProfileRow = { price: number; volume: number };

export type VolumeProfile = {
  rows: VolumeProfileRow[];
  poc: number | null;
  last_price: number;
  period_days: number;
  bin_size: number;
};

export type CompareRow = {
  symbol: string;
  name?: string | null;
  sector?: string | null;
  verdict?: string | null;
  confidence?: string | null;
  risk_rating?: number | null;
  sentiment_score?: number | null;
  price?: number | null;
  change_pct?: number | null;
  spark: SparkPoint[];
  bullish_signals: number;
  bearish_signals: number;
  total_signals: number;
  pe_ratio?: number | null;
  dividend_yield?: number | null;
  from_cache?: boolean;
  error?: string | null;
};

export type ComparePayload = {
  rows: CompareRow[];
  period: string;
  available_periods: string[];
  last_updated: string;
};

export type DeepDive = {
  symbol: string;
  name?: string | null;
  sector?: string | null;
  industry?: string | null;
  verdict: string;
  confidence: string;
  risk_rating: number;
  risk_label: string;
  price?: number | null;
  period_change?: PeriodChange | null;
  summary?: string | null;
  sentiment_score?: number | null;
  signals: SignalRow[];
  signal_groups: Record<string, SignalRow[]>;
  signal_counts: SignalCounts;
  trade_plan?: TradePlan | null;
  earnings: EarningsRow[];
  volume_profile?: VolumeProfile | null;
  available_periods: string[];
  period: string;
  signal_filter: string;
  last_updated: string;
  cached_at?: string | null;
  from_cache?: boolean;
};

export type AgentStatus = {
  enabled: boolean;
  last_run?: string | null;
  portfolio_value: number;
  open_positions: number;
  rebalance_frequency: string;
  next_run?: string | null;
  overdue?: boolean;
};

export type AgentDecision = {
  timestamp: string;
  symbol: string;
  action: string;
  quantity?: number | null;
  reason?: string | null;
};

export type AgentConfig = {
  starting_capital: number;
  current_cash: number;
  risk_per_trade: number;
  max_positions: number;
  max_buys_per_cycle: number;
  min_opportunity_score: number;
  stop_loss_pct: number;
  rebalance_frequency: string;
  status: string;
  last_run?: string | null;
};

export type AgentPersonality = {
  key: string;
  name: string;
  icon: string;
  color: string;
  tagline: string;
  philosophy: string;
  strengths: string[];
  weaknesses: string[];
  prioritizes: string[];
  avoids: string[];
  backtest_signals: string[];
  risk_tolerance: string;
  ideal_market: string;
  historical_edge: string;
  kind: "opinion" | "data";
};

export type RiskManagerInfo = {
  name: string;
  icon: string;
  color: string;
  tagline: string;
  philosophy: string;
  checks: string[];
};

export type AgentPersonalitiesResponse = {
  agents: AgentPersonality[];
  risk_manager: RiskManagerInfo;
};

export type AgentPosition = {
  symbol: string;
  direction: string;
  shares: number;
  entry_price: number;
  entry_date?: string | null;
  stop_loss?: number | null;
  target?: number | null;
  current_price: number;
  pnl: number;
  pnl_pct: number;
  ai_reasoning: string;
};

export type AgentEquityPoint = {
  date: string;
  total_value: number;
  cash: number;
  invested: number;
  cumulative_return: number;
  benchmark_value?: number | null;
};

export type AgentEquityMetrics = {
  total_return: number;
  annualized_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  alpha: number;
};

export type AgentEquityResponse = {
  points: AgentEquityPoint[];
  metrics: AgentEquityMetrics;
};

export type AgentCycleResult = {
  ok: boolean;
  trades_executed: number;
  portfolio_value: number;
  summary: string;
  error?: string | null;
};

export type MultiAgentPick = {
  sector?: string | null;
  symbol: string;
  agent?: string | null;
  score: number;
  reasoning: string;
};

export type SectorWinner = {
  symbol: string;
  agent: string;
  score: number;
};

export type MultiAgentResult = {
  ok: boolean;
  timestamp?: string | null;
  macro_context: string;
  sectors_analyzed: string[];
  agent_picks: Record<string, MultiAgentPick[]>;
  sector_winners: Record<string, SectorWinner>;
  final_portfolio: MultiAgentPick[];
  risk_manager_reasoning: string;
  error?: string | null;
};

export type CotStep = {
  step: string;
  symbol: string;
  decision: string;
  reasoning: string;
  created_at: string;
};

export type CotRun = {
  run_date: string;
  steps: CotStep[];
};

export type CotResponse = {
  runs: CotRun[];
};

export type AgentLifecycle = {
  ok: boolean;
  status: string;
};

// ── Portfolio AI Agent (live pick) ──────────────────────────────

export type CandidateScreen = {
  symbol: string;
  name?: string | null;
  sector?: string | null;
  price: number | null;
  rsi: number | null;
  change_5d: number | null;
  change_20d: number | null;
  vol_ratio: number | null;
  opportunity_score: number;
  opportunity_label: string;
  strategy: string;
  bull_signals: number;
  bear_signals: number;
  alignment_pct: number;
  dominant: string;
};

export type StockPick = {
  symbol: string;
  reason: string;
};

export type AgentVotePicks = {
  agent: string;
  picks: StockPick[];
  raw: string;
};

export type ConsensusVote = {
  agent: string;
  reason: string;
};

export type ConsensusPick = {
  symbol: string;
  agent_count: number;
  votes: ConsensusVote[];
};

export type PortfolioAgentConfig = {
  top_n: number;
  min_agents_for_consensus: number;
  max_picks_per_agent: number;
  agents: string[];
};

export type PortfolioAgentResponse = {
  timestamp: string;
  universe_size: number;
  error?: string | null;
  candidates_screened: CandidateScreen[];
  agent_votes: AgentVotePicks[];
  consensus_picks: ConsensusPick[];
  final_portfolio: ConsensusPick[];
  config?: PortfolioAgentConfig | null;
};

export type ExecutedTrade = {
  symbol: string;
  action: string;
  shares: number;
  price: number;
};

export type SkippedTrade = {
  symbol: string;
  reason: string;
};

export type PortfolioExecuteResponse = {
  timestamp: string;
  run_date: string;
  executed: ExecutedTrade[];
  skipped: SkippedTrade[];
  cash_remaining: number;
  open_positions: number;
  max_positions: number;
};

// ── Walk-forward simulation ────────────────────────────────────

export type SimEquityPoint = {
  date: string;
  equity: number;
};

export type SimVoter = {
  agent: string;
  reason: string;
};

export type SimTrade = {
  symbol: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  shares: number;
  pnl: number;
  pnl_pct: number;
  consensus_count: number;
  voters: SimVoter[];
};

export type SimOpenedPick = {
  symbol: string;
  shares: number;
  entry_price: number;
  entry_date: string;
  consensus_count: number;
};

export type SimCycleAgentVote = {
  agent: string;
  picks: StockPick[];
  raw: string;
};

export type SimCycleLog = {
  cycle_index: number;
  date: string;
  skipped?: string | null;
  candidates_screened: CandidateScreen[];
  agent_votes: SimCycleAgentVote[];
  consensus_picks: ConsensusPick[];
  opened: SimOpenedPick[];
};

export type WalkForwardSimSummary = {
  initial_capital: number;
  final_equity: number;
  total_return_pct: number;
  total_trades: number;
  winners: number;
  win_rate: number;
  avg_pnl_pct: number;
  cycles_run: number;
};

export type WalkForwardSimConfig = {
  start_date: string;
  end_date: string;
  cycle_days: number;
  initial_capital: number;
  max_positions: number;
  min_agents: number;
  top_n: number;
  position_size_pct: number;
  agents: string[];
};

export type WalkForwardSimResponse = {
  error?: string | null;
  config?: WalkForwardSimConfig | null;
  summary?: WalkForwardSimSummary | null;
  equity_curve: SimEquityPoint[];
  trades: SimTrade[];
  cycles: SimCycleLog[];
};

export type StockSearchResult = {
  symbol: string;
  name?: string | null;
  sector?: string | null;
};

// ── Alerts ────────────────────────────────────────────────────────

export type AlertItem = {
  id?: number | null;
  symbol: string;
  alert_type: string;
  message: string;
  old_value?: string | null;
  new_value?: string | null;
  severity: "critical" | "warning" | "info" | string;
  created_at: string;
};

export type AlertSummary = {
  total: number;
  critical: number;
  warning: number;
  last_24h: number;
};

// ── Backtest ─────────────────────────────────────────────────────

export type SignalCatalogItem = {
  name: string;
  label: string;
  description: string;
  direction: "buy" | "sell";
  category: string;
};

export type SignalCatalog = {
  signals: SignalCatalogItem[];
  categories: string[];
  category_signals: Record<string, string[]>;
};

export type FullBacktestTrade = {
  entry_date: string;
  entry_price: number;
  exit_date: string;
  exit_price: number;
  pnl_percent: number;
  hold_days: number;
  outcome: "win" | "loss";
};

export type SignalResultRow = {
  signal_name: string;
  description: string;
  category: string;
  direction: "buy" | "sell";
  win_rate: number;
  avg_return: number;
  total_trades: number;
  max_gain: number;
  max_loss: number;
  grade: string;
  trades: FullBacktestTrade[];
};

export type AllSignalsResponse = {
  symbol: string;
  period: string;
  hold_days: number;
  category: string;
  results: SignalResultRow[];
  available_periods: string[];
  available_categories: string[];
  error?: string | null;
  last_updated: string;
};

export type Candle = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type SingleBacktestResponse = {
  symbol: string;
  signal: string;
  signal_label: string;
  signal_description: string;
  period: string;
  hold_days: number;
  result: SignalResultRow | null;
  candles: Candle[];
  error?: string | null;
};

export type MultiStockRow = {
  symbol: string;
  signal_name?: string | null;
  description?: string | null;
  win_rate?: number | null;
  avg_return?: number | null;
  total_trades?: number | null;
  max_gain?: number | null;
  max_loss?: number | null;
  grade?: string | null;
  error?: string | null;
};

export type MultiStockResponse = {
  signal: string;
  signal_label: string;
  signal_description: string;
  period: string;
  hold_days: number;
  rows: MultiStockRow[];
};

// ── Portfolio Simulation ──────────────────────────────────────────

export type PortfolioEquityPoint = {
  date: string;
  total_value: number;
  cash: number;
  invested: number;
  daily_return: number;
  cumulative_return: number;
  benchmark_return: number;
};

export type PortfolioTradeRow = {
  symbol: string;
  entry_date: string;
  entry_price: number;
  exit_date: string;
  exit_price: number;
  pnl_percent: number;
  hold_days: number;
  outcome: "win" | "loss";
};

export type PortfolioBestTrade = {
  symbol: string;
  pnl_percent: number;
  entry_date: string;
  exit_date: string;
};

export type PortfolioSimResponse = {
  strategy?: string | null;
  symbols: string[];
  initial_capital: number;
  final_value: number;
  total_return: number;
  annualized_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  total_trades: number;
  alpha: number;
  best_trade?: PortfolioBestTrade | null;
  worst_trade?: PortfolioBestTrade | null;
  equity_curve: PortfolioEquityPoint[];
  trades: PortfolioTradeRow[];
  error?: string | null;
};

// ── AI Analyst ────────────────────────────────────────────────────

export type AiTradePlanSnapshot = {
  entry: number;
  stop: number;
  target1: number;
  target2: number;
  risk_per_share: number;
  rr: number;
  stop_pct: number;
};

export type AgentVote = {
  agent: string;
  vote: "BUY" | "SELL" | "HOLD";
  reason?: string;
  raw?: string;
};

export type AiDecision = {
  date: string;
  price: number;
  decision: "BUY" | "SELL" | "HOLD";
  action: "OPEN" | "CLOSE" | "HOLD";
  raw_response?: string;
  rsi?: number | null;
  pnl_percent?: number | null;
  regime?: string | null;
  sentiment?: string | null;
  trade_plan?: AiTradePlanSnapshot | null;
  prompt?: string;
  agent_votes?: AgentVote[];
};

export type AiAnalystResponse = {
  symbol: string;
  period: string;
  mode?: "single" | "multi";
  agents_used?: string[];
  hold_days: number;
  cycles_run: number;
  decisions: AiDecision[];
  trades: PortfolioTradeRow[];
  win_count: number;
  loss_count: number;
  win_rate: number;
  avg_return: number;
  total_trades: number;
  error?: string | null;
};


// ── Data Sources / Rate Limits ────────────────────────────────────

export type DataSourceStatusKind = "ok" | "warning" | "limited" | "untracked";

export type DataSourceStatus = {
  source: string;
  key: string;
  used: number;
  capacity: number | null;
  window_seconds: number;
  status: DataSourceStatusKind;
};

export type DataSourcesResponse = {
  sources: DataSourceStatus[];
  any_limited: boolean;
};


// ── Universe (knowledge-graph prototype) ─────────────────────────

export type Tier = "A" | "B" | "C" | "D";

export type IndustryTag = {
  code: string;
  sector: string | null;
  weight: number;
  is_primary: boolean;
};

export type UniverseStock = {
  symbol: string;
  name: string | null;
  tier: Tier;
  exchange: string | null;
  country: string | null;
  market_cap: number | null;
  avg_dollar_volume: number | null;
  in_sp500: boolean;
  in_russell1000: boolean;
  in_russell2000: boolean;
  in_tsx60: boolean;
  in_qqq: boolean;
  industries: IndustryTag[];
};

export type TierCounts = {
  A: number;
  B: number;
  C: number;
  D: number;
  total: number;
};

export type UniverseResponse = {
  stocks: UniverseStock[];
  counts: TierCounts;
  filters_applied: { tier: string | null; industry: string | null; sector: string | null };
};


// ── News Impact (Phase 2 + Phase 4 graph expansion) ────────────────

export type NewsImpactStock = {
  symbol: string;
  name: string | null;
  tier: Tier;
  sector: string | null;
  industry_code: string | null;
  polarity: number;          // -1..1 — sign indicates bullish/bearish
  strength: number;          // 0..1
  composite_score: number;
  contributing_keywords: string[];
  contributing_industries: string[];   // entries starting "via:X" indicate graph expansion
  direct_target: boolean;
};

export type NewsImpactIndustry = {
  industry_code: string;
  polarity: number;
  strength: number;
  contributing_keywords: string[];
  contributing_domains: string[];
};

export type NewsImpactResponse = {
  stocks: NewsImpactStock[];
  industries: NewsImpactIndustry[];
  matched_keywords: string[];
  matched_countries: string[];
  matched_symbols: string[];
  negated_keywords: string[];
};


// ── Graph: peers (Phase 3) ────────────────────────────────────────

export type PeerEdge = {
  symbol: string;
  name: string | null;
  tier: Tier | null;
  sector: string | null;
  industry_code: string | null;
  similarity: number;
  overlap_dimensions: string[];
  source: string;          // 'hand' | 'claude_batch' | 'claude_validated'
  confidence: string;      // 'high' | 'medium' | 'low'
  evidence: string | null;
};

export type PeerListResponse = {
  symbol: string;
  name: string | null;
  tier: Tier | null;
  peers: PeerEdge[];
  total: number;
};


// ── Graph: neighborhood (Phase 4) ─────────────────────────────────

export type NeighborEdge = {
  symbol: string;
  name: string | null;
  tier: Tier | null;
  sector: string | null;
  edge_type: "supplier" | "customer" | "peer" | "substitute" | "complement";
  strength: number;
  polarity: number;         // -1..1
  confidence: string;
  source: string;
  evidence: string | null;
};

export type NeighborhoodResponse = {
  symbol: string;
  name: string | null;
  tier: Tier | null;
  sector: string | null;
  suppliers: NeighborEdge[];
  customers: NeighborEdge[];
  peers: NeighborEdge[];
  substitutes: NeighborEdge[];
  complements: NeighborEdge[];
};


// ── Phase 7A: Ownership ──────────────────────────────────────────

export type HolderRow = {
  cik: string;
  institution_name: string | null;
  institution_type: string | null;
  value_usd: number | null;
  pct_portfolio: number | null;
  pct_outstanding: number | null;
  as_of: string;
  source: string | null;
};

export type TopHoldersResponse = {
  symbol: string;
  holders: HolderRow[];
  total: number;
};

export type HoldingRow = {
  symbol: string;
  stock_name: string | null;
  tier: Tier | null;
  value_usd: number | null;
  pct_portfolio: number | null;
  pct_outstanding: number | null;
  rank_in_portfolio: number | null;
  as_of: string;
};

export type InstitutionHoldingsResponse = {
  cik: string;
  name: string | null;
  type: string | null;
  total_aum: number | null;
  holdings: HoldingRow[];
  total: number;
};


// ── Phase 7B: Edge freshness ────────────────────────────────────

export type FreshnessQueueRow = {
  symbol: string;
  status: "fresh" | "aging" | "needs_review" | "stale";
  trigger_reason: string | null;
  flagged_at: string | null;
  last_extracted_at: string | null;
};

export type FreshnessQueueResponse = {
  queue: FreshnessQueueRow[];
  counts_by_status: Record<string, number>;
};

export type RiskNarrative = {
  symbol: string;
  industry_threats?: string;
  competitive_risks?: string;
  balance_sheet?: string;
  macro_exposure?: string;
  worst_case?: string;
  risk_rating?: number | null;
  risk_label?: string | null;
  error?: string | null;
  raw?: string | null;
  from_cache?: boolean;
};

export type EarningsExplanation = {
  symbol: string;
  summary?: string;
  beats?: string[];
  misses?: string[];
  guidance?: string;
  case_change?: "strengthens" | "weakens" | "unchanged" | string;
  case_change_reason?: string;
  input_chars?: number | null;
  error?: string | null;
  raw?: string | null;
};
