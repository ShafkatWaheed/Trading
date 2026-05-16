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
  change_pct_prior?: number | null;
  delta_pp?: number | null;
  accel?: "accelerating" | "decelerating" | "steady" | null;
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
  next_event?: CalendarEvent | null;
  next_high_impact?: CalendarEvent | null;
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
  sources?: number[];
};

export type DisruptionArticle = {
  idx: number;
  title: string;
  url: string;
  source: string;
};

export type DisruptionPayload = {
  themes: DisruptionTheme[];
  source: "claude" | "fallback";
  articles?: DisruptionArticle[];
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

export type AiAnalystMultiResponse = {
  period: string;
  mode: "single" | "multi" | string;
  cycles: number;
  rows: AiAnalystResponse[];
  error?: string | null;
  last_updated?: string | null;
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
  invalidates_if?: string;
  risk_rating?: number | null;
  risk_label?: string | null;
  error?: string | null;
  raw?: string | null;
  from_cache?: boolean;
};

export type BubbleScore = {
  symbol: string;
  score: number;
  label: string;
  components: {
    growth_gap: number;
    valuation: number;
    momentum: number;
  };
  metrics: {
    price_change_1y_pct?: number | null;
    price_change_3m_pct?: number | null;
    revenue_growth_pct?: number | null;
    earnings_growth_pct?: number | null;
    growth_gap_pct?: number | null;
    vibes_share_pct?: number | null;
    fundamental_growth_pct?: number | null;
    pe_ratio?: number | null;
    ps_ratio?: number | null;
    pb_ratio?: number | null;
    pfcf_ratio?: number | null;
  };
  verdict: string;
  reasons?: string[];
  last_updated: string;
  from_cache?: boolean;
};

export type BullNarrative = {
  symbol: string;
  growth_drivers?: string;
  competitive_moat?: string;
  multiple_expansion?: string;
  catalysts?: string;
  best_case?: string;
  invalidates_if?: string;
  error?: string | null;
  raw?: string | null;
  from_cache?: boolean;
};

export type AnalystConsensus = {
  symbol: string;
  rating?: string | null;
  rating_mean?: number | null;
  analyst_count?: number | null;
  current_price?: number | null;
  target_mean?: number | null;
  target_high?: number | null;
  target_low?: number | null;
  upside_pct?: number | null;
  ratings_breakdown: {
    strong_buy: number; buy: number; hold: number; sell: number; strong_sell: number;
  };
  error?: string | null;
  last_updated: string;
  from_cache?: boolean;
};

export type PeerValuationRow = {
  symbol: string;
  is_self: boolean;
  pe_ratio?: number | null;
  ps_ratio?: number | null;
  pfcf_ratio?: number | null;
  price_change_1y_pct?: number | null;
};

export type PeerValuation = {
  symbol: string;
  rows: PeerValuationRow[];
  medians: {
    pe_ratio?: number | null;
    ps_ratio?: number | null;
    pfcf_ratio?: number | null;
    price_change_1y_pct?: number | null;
  };
  last_updated: string;
  from_cache?: boolean;
};

export type NewsFeedItem = {
  title: string;
  snippet?: string;
  url?: string;
  source?: string;
  sentiment: "bullish" | "bearish" | "neutral" | string;
  sentiment_score: number;
  published?: string | null;
};

export type NewsFeed = {
  symbol: string;
  items: NewsFeedItem[];
  bull_count: number;
  bear_count: number;
  neutral_count: number;
  net_sentiment: "bullish" | "bearish" | "mixed" | "no coverage" | string;
  net_score: number;
  last_updated: string;
  from_cache?: boolean;
};

export type CatalystEvent = {
  date: string;
  days_out: number;
  title: string;
  kind: "earnings" | "dividend" | "macro" | "split" | string;
  weight: "low" | "med" | "high" | "very_high" | string;
  detail?: string | null;
  symbol_specific: boolean;
};

export type Recommendation = {
  symbol: string;
  action: "STRONG_BUY" | "BUY" | "BUY_ON_DIP" | "HOLD" | "TRIM" | "SELL" | "STRONG_SELL" | string;
  action_label: string;
  tone: "strong_bullish" | "bullish" | "cautious_bullish" | "neutral" | "cautious_bearish" | "bearish" | "strong_bearish" | string;
  headline: string;
  reasoning: string;
  wait_until_price?: number | null;
  wait_reason?: string | null;
  reevaluate?: string | null;
  components: {
    verdict?: string | null;
    risk_rating?: number | null;
    bubble_score?: number | null;
    bubble_label?: string | null;
    analyst_rating?: string | null;
    analyst_upside?: number | null;
    analyst_target?: number | null;
    insider?: string | null;
    congress?: string | null;
    price?: number | null;
  };
  last_updated: string;
  from_cache?: boolean;
};

export type SignalEvidenceItem = {
  signal_key?: string | null;
  win_rate?: number | null;
  avg_return_pct?: number | null;
  total_trades?: number | null;
  max_gain_pct?: number | null;
  max_loss_pct?: number | null;
  hold_days?: number | null;
  grade?: string | null;
  error?: string | null;
};

export type SignalEvidence = {
  symbol: string;
  hold_days: number;
  signals_tested: number;
  signals_total: number;
  evidence: Record<string, SignalEvidenceItem>;
  last_updated: string;
  from_cache?: boolean;
};

export type MarketStatus = {
  status: "open" | "pre_market" | "after_hours" | "closed" | string;
  label: string;
  minutes_to_open?: number | null;
  minutes_to_close?: number | null;
};

export type IndexSnapshot = {
  key: string;
  ticker: string;
  display: string;
  price?: number | null;
  change?: number | null;
  change_pct?: number | null;
  spark?: number[];
  change_30d_pct?: number | null;
};

export type BreadthMetrics = {
  spy_vs_rsp_1m_pp?: number | null;
  iwm_vs_spy_1m_pp?: number | null;
  vix_level?: number | null;
  vix_regime?: string | null;
  spy_pct_above_50d?: number | null;
  spy_pct_above_200d?: number | null;
  headline: string;
};

export type MoverRow = {
  symbol: string;
  price: number;
  change_pct: number;
  change: number;
};

export type MarketDashboard = {
  status: MarketStatus;
  indices: IndexSnapshot[];
  breadth: BreadthMetrics;
  movers: {
    gainers_1d: MoverRow[];
    losers_1d: MoverRow[];
    gainers_5d: MoverRow[];
    losers_5d: MoverRow[];
    error?: string | null;
  };
  last_updated: string;
  from_cache?: boolean;
};

export type MarketTakeaway = {
  regime: string;
  stance: string;
  tone: "bullish" | "cautious_bullish" | "cautious" | "neutral" | "defensive" | string;
  headline: string;
  bullets: string[];
  last_updated: string;
  from_cache?: boolean;
};

export type MarketNewsItem = {
  title: string;
  snippet?: string;
  url?: string;
  source?: string;
  sentiment: string;
  sentiment_score: number;
  published?: string | null;
};

export type MarketNews = {
  items: MarketNewsItem[];
  bull_count: number;
  bear_count: number;
  neutral_count: number;
  net_sentiment: string;
  net_score: number;
  provider?: string | null;
  source_warning?: string | null;
  last_updated: string;
  from_cache?: boolean;
};

export type BenchmarkSparkPoint = {
  date: string;
  close: number;
  idx: number;
};

export type Benchmarks = {
  symbol: string;
  period: string;
  sector?: string | null;
  sector_etf?: string | null;
  spy_spark: BenchmarkSparkPoint[];
  sector_spark: BenchmarkSparkPoint[];
  last_updated: string;
  from_cache?: boolean;
};

export type CatalystCalendar = {
  symbol: string;
  horizon_days: number;
  events: CatalystEvent[];
  earnings_count: number;
  macro_count: number;
  dividend_count: number;
  last_updated: string;
  from_cache?: boolean;
};

export type SmartMoney = {
  symbol: string;
  institutional: {
    top_holders: Array<{
      name?: string | null;
      type?: string | null;
      value_usd?: number | null;
      pct_outstanding?: number | null;
      pct_portfolio?: number | null;
      as_of?: string | null;
    }>;
    total_known_holders: number;
    error?: string | null;
  };
  insider: {
    total_trades: number;
    total_buys: number;
    total_sells: number;
    unique_insiders: number;
    cluster_buy: boolean;
    buy_value_usd?: number | null;
    sell_value_usd?: number | null;
    net_value_usd?: number | null;
    signal: string;
    recent_trades: Array<{
      filer: string;
      title?: string | null;
      transaction?: string | null;
      shares?: number | null;
      price?: number | null;
      value_usd?: number | null;
      transaction_date?: string | null;
      filing_date?: string | null;
    }>;
    error?: string | null;
  };
  congress: {
    total_trades: number;
    total_buys: number;
    total_sells: number;
    unique_politicians: number;
    net_sentiment: string;
    top_buyers: string[];
    top_sellers: string[];
    recent_trades: Array<{
      politician: string;
      party?: string | null;
      chamber?: string | null;
      state?: string | null;
      transaction?: string | null;
      amount_range?: string | null;
      amount_low_usd?: number | null;
      amount_high_usd?: number | null;
      trade_date?: string | null;
      filed_date?: string | null;
      days_to_file?: number | null;
      committees: string[];
    }>;
    party_breakdown: Record<string, Record<string, number>>;
    error?: string | null;
  };
  summary: string;
  last_updated: string;
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

// ── Refresh pipeline ─────────────────────────────────────────────

export type RefreshKindMeta = {
  kind: string;
  description: string;
};

export type RefreshJob = {
  id: number;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  progress: number;             // 0..1
  processed: number;
  total: number;
  message?: string | null;
  error?: string | null;
  result_json?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

export type RefreshQualitySnapshot = {
  universe: { total: number; by_tier: Record<string, number> };
  industries: {
    stock_industry_rows: number;
    tagged_symbols: number;
    distinct_industries: number;
  };
  peers: { by_source: Record<string, number> };
  relations: { by_type: Record<string, number> };
  commodity_exposures: { by_source: Record<string, number> };
  institutional: {
    holdings_total: number;
    by_source: Record<string, number>;
  };
  freshness: { by_status: Record<string, number> };
  latest_jobs: Record<string, { status: string; finished_at?: string | null }>;
};


// ── Deep Dive Bundle (Phase 4) ────────────────────────────────

export type DeepDiveBundle = {
  deep_dive: DeepDive;
  bubble_score: BubbleScore | null;
  peer_valuation: PeerValuation | null;
  analyst_consensus: AnalystConsensus | null;
  benchmarks: Benchmarks | null;
  period: string;
  last_updated: string;
  errors: Record<string, string>;
};


// ── AI Track Record (Phase 2) ─────────────────────────────────

export type TrackRecordSource = "recommendation" | "ai_analyst" | "bubble_score";

export type TrackRecordOverall = {
  total: number;
  correct: number;
  accuracy_pct: number;
  avg_return_pct: number;
  avg_win_return_pct: number;
  avg_loss_return_pct: number;
};

export type TrackRecordBySource = {
  source: TrackRecordSource;
  total: number;
  correct: number;
  accuracy_pct: number;
  avg_return_pct: number;
};

export type TrackRecord = {
  filter: {
    source: TrackRecordSource | null;
    symbol: string | null;
    days: number | null;
  };
  overall: TrackRecordOverall;
  by_source: TrackRecordBySource[];
  pending_count: number;
  last_updated: string;
};

export type DecisionStatus = "pending" | "correct" | "incorrect";

export type DecisionLogItem = {
  id: number;
  created_at: string;
  symbol: string;
  source: TrackRecordSource;
  decision: string;
  score: number | null;
  price_at_call: number;
  prediction_window_days: number;
  context: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  status: DecisionStatus;
  evaluated_at: string | null;
  price_now: number | null;
  return_pct: number | null;
};

export type DecisionsRecent = {
  filter: { source: TrackRecordSource | null; symbol: string | null; limit: number };
  items: DecisionLogItem[];
  last_updated: string;
};

export type TopWinLossRow = {
  id: number;
  created_at: string;
  symbol: string;
  source: TrackRecordSource;
  decision: string;
  price_at_call: number;
  return_pct: number;
  was_correct: number;
};

export type TopWinsLosses = {
  wins: TopWinLossRow[];
  losses: TopWinLossRow[];
  last_updated: string;
};

export type EvaluatorRun = {
  ran_at: string;
  candidates: number;
  evaluated: number;
  correct: number;
  incorrect: number;
  skipped_pending: number;
  skipped_no_price: number;
};

// ── Context Search (Tier 1: LLM query expander → graph) ───────────

export type ContextSearchCommodity = {
  code: string;
  direction: "up" | "down";
  intensity: number;
};

export type ContextSearchIndustry = {
  code: string;
  polarity: number;
};

export type ContextSearchExpansion = {
  keywords: string[];
  commodities: ContextSearchCommodity[];
  industries: ContextSearchIndustry[];
  themes: string[];
  substitutes_hint: string[];
  interpretation: string;
};

export type ContextSearchStock = {
  symbol: string;
  name?: string | null;
  tier?: string | null;
  sector?: string | null;
  industry_code?: string | null;
  composite_score: number;
  polarity: number;
  legs: ("keywords" | "commodities" | "graph_relevance")[];
  reasoning: string[];
};

export type ContextSearchIndustryRow = {
  industry_code: string;
  polarity: number;
  strength: number;
  contributing_keywords: string[];
  stocks: string[];
};

export type ContextSearchResponse = {
  query: string;
  expansion: ContextSearchExpansion;
  stocks: ContextSearchStock[];
  by_industry: ContextSearchIndustryRow[];
  matched_keywords: string[];
  matched_symbols: string[];
};
