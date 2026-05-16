import { api } from "./client";
import type {
  MarketPulse,
  DiscoverPayload,
  DeepDive,
  AgentStatus,
  AgentDecision,
  AgentConfig,
  AgentPersonalitiesResponse,
  AgentPosition,
  AgentEquityResponse,
  AgentCycleResult,
  MultiAgentResult,
  CotResponse,
  AgentLifecycle,
  StockSearchResult,
  CalendarPayload,
  GeopoliticalPayload,
  DisruptionPayload,
  WatchlistEntry,
  ComparePayload,
  SignalCatalog,
  AllSignalsResponse,
  SingleBacktestResponse,
  MultiStockResponse,
  PortfolioSimResponse,
  AiAnalystResponse,
  AiAnalystMultiResponse,
  AlertItem,
  AlertSummary,
  DataSourcesResponse,
  PortfolioAgentResponse,
  PortfolioExecuteResponse,
  WalkForwardSimResponse,
  UniverseResponse,
  NewsImpactResponse,
  PeerListResponse,
  NeighborhoodResponse,
  TopHoldersResponse,
  InstitutionHoldingsResponse,
  FreshnessQueueResponse,
  RefreshKindMeta,
  RefreshJob,
  RefreshQualitySnapshot,
  ContextSearchResponse,
  RiskNarrative,
  EarningsExplanation,
  BubbleScore,
  BullNarrative,
  AnalystConsensus,
  PeerValuation,
  SmartMoney,
  NewsFeed,
  CatalystCalendar,
  Benchmarks,
  Recommendation,
  SignalEvidence,
  MarketDashboard,
  MarketTakeaway,
  MarketNews,
  TrackRecord,
  TrackRecordSource,
  DecisionsRecent,
  TopWinsLosses,
  EvaluatorRun,
  DeepDiveBundle,
  StockInformation,
  EntityMatches,
} from "./types";

export const marketApi = {
  pulse: (period: string = "1M") =>
    api.get<MarketPulse>(`/market/pulse?period=${encodeURIComponent(period)}`),
  dashboard: () => api.get<MarketDashboard>("/market/dashboard"),
  takeaway:  () => api.get<MarketTakeaway>("/market/takeaway"),
  news:      () => api.get<MarketNews>("/market/news"),
  calendar: (days = 60, limit = 12) =>
    api.get<CalendarPayload>(`/market/calendar?days=${days}&limit=${limit}`),
  geopolitical: () => api.get<GeopoliticalPayload>("/market/geopolitical"),
  disruption: () => api.get<DisruptionPayload>("/market/disruption"),
};

export const discoverApi = {
  list: (opts?: {
    min_score?: number;
    limit?: number;
    sector?: string;
    period?: string;
    only_watchlist?: boolean;
  }) => {
    const params = new URLSearchParams();
    if (opts?.min_score !== undefined) params.set("min_score", String(opts.min_score));
    if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
    if (opts?.sector) params.set("sector", opts.sector);
    if (opts?.period) params.set("period", opts.period);
    if (opts?.only_watchlist !== undefined) params.set("only_watchlist", String(opts.only_watchlist));
    const qs = params.toString();
    return api.get<DiscoverPayload>(`/discover${qs ? "?" + qs : ""}`);
  },
};

export const compareApi = {
  run: (symbols: string[], period: string = "3M") =>
    api.get<ComparePayload>(
      `/compare?symbols=${encodeURIComponent(symbols.join(","))}&period=${encodeURIComponent(period)}`
    ),
};

export const backtestApi = {
  signals: () => api.get<SignalCatalog>("/backtest/signals"),
  all: (symbol: string, period: string, category: string) =>
    api.get<AllSignalsResponse>(
      `/backtest/all?symbol=${encodeURIComponent(symbol)}&period=${encodeURIComponent(period)}&category=${encodeURIComponent(category)}`
    ),
  single: (symbol: string, signal: string, period: string) =>
    api.get<SingleBacktestResponse>(
      `/backtest/single?symbol=${encodeURIComponent(symbol)}&signal=${encodeURIComponent(signal)}&period=${encodeURIComponent(period)}`
    ),
  multiStock: (symbols: string[], signal: string, period: string) =>
    api.post<MultiStockResponse>("/backtest/multi-stock", { symbols, signal, period }),
  portfolio: (
    symbols: string[],
    strategy: string,
    initial_capital = 100_000,
    position_size_pct = 0.20,
  ) =>
    api.post<PortfolioSimResponse>("/backtest/portfolio", {
      symbols, strategy, initial_capital, position_size_pct,
    }),
  // Bypass the Next.js dev proxy for this long-running call. The dev rewrite
  // drops connections after ~60-90s, but the backend takes several minutes for
  // multi-mode. Direct fetch to :8000 + CORS (allowed in api/main.py) works.
  // In production, replace with the deployed API origin (or move behind a
  // proxy whose timeout you control).
  aiAnalyst: async (symbol: string, period: string, cycles = 12, mode: "single" | "multi" = "single") => {
    const isBrowser = typeof window !== "undefined";
    const isLocalDev = isBrowser && /^https?:\/\/(localhost|127\.0\.0\.1):\d+/.test(window.location.origin);
    const url = isLocalDev
      ? "http://localhost:8000/backtest/ai-analyst"
      : "/api/backtest/ai-analyst";
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, period, cycles, mode }),
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(body || `HTTP ${res.status} ${res.statusText}`);
    }
    return (await res.json()) as AiAnalystResponse;
  },
  aiAnalystMulti: async (
    symbols: string[], period: string, cycles = 8, mode: "single" | "multi" = "single",
  ) => {
    // Same dev-proxy bypass as single; multi-stock can take minutes for N stocks.
    const isBrowser = typeof window !== "undefined";
    const isLocalDev = isBrowser && /^https?:\/\/(localhost|127\.0\.0\.1):\d+/.test(window.location.origin);
    const url = isLocalDev
      ? "http://localhost:8000/backtest/ai-analyst-multi"
      : "/api/backtest/ai-analyst-multi";
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols, period, cycles, mode }),
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(body || `HTTP ${res.status} ${res.statusText}`);
    }
    return (await res.json()) as AiAnalystMultiResponse;
  },
};

export const alertsApi = {
  list: (limit = 50, symbol?: string) => {
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    if (symbol) params.set("symbol", symbol);
    return api.get<AlertItem[]>(`/alerts?${params.toString()}`);
  },
  summary: () => api.get<AlertSummary>("/alerts/summary"),
  clearAll: () => api.del<{ ok: boolean; deleted: number }>("/alerts"),
};

export const watchlistApi = {
  list: () => api.get<WatchlistEntry[]>("/watchlist"),
  add: (symbol: string) => api.post<{ ok: boolean; symbol?: string; error?: string }>("/watchlist", { symbol }),
  remove: (symbol: string) =>
    api.del<{ ok: boolean }>(`/watchlist/${encodeURIComponent(symbol)}`),
  addTop5: () => api.post<{ ok: boolean; added: string[] }>("/watchlist/top5", {}),
};

export const stocksApi = {
  search: (q: string) => api.get<StockSearchResult[]>(`/stocks/search?q=${encodeURIComponent(q)}`),
  deepDive: (
    ticker: string,
    opts?: {
      period?: string;
      signal_filter?: string;
      account_size?: number;
      risk_pct?: number;
      force?: boolean;
    }
  ) => {
    const params = new URLSearchParams();
    if (opts?.period) params.set("period", opts.period);
    if (opts?.signal_filter) params.set("signal_filter", opts.signal_filter);
    if (opts?.account_size !== undefined) params.set("account_size", String(opts.account_size));
    if (opts?.risk_pct !== undefined) params.set("risk_pct", String(opts.risk_pct));
    if (opts?.force) params.set("force", "true");
    const qs = params.toString();
    return api.get<DeepDive>(`/stocks/${encodeURIComponent(ticker)}/deep-dive${qs ? "?" + qs : ""}`);
  },
  // Deep-dive bundle runs 5 services concurrently and the slowest sub-call
  // (yfinance fundamentals) can push the total past 60s when Yahoo's crumb
  // cache invalidates. The Next.js dev proxy drops anything over ~60s with
  // an empty 500, so in dev we bypass the proxy and hit FastAPI directly.
  // Production keeps the relative path so deployed reverse-proxy timeouts
  // can be tuned independently.
  deepDiveBundle: async (
    ticker: string,
    opts?: {
      period?: string;
      signal_filter?: string;
      account_size?: number;
      risk_pct?: number;
      force?: boolean;
    }
  ): Promise<DeepDiveBundle> => {
    const params = new URLSearchParams();
    if (opts?.period) params.set("period", opts.period);
    if (opts?.signal_filter) params.set("signal_filter", opts.signal_filter);
    if (opts?.account_size !== undefined) params.set("account_size", String(opts.account_size));
    if (opts?.risk_pct !== undefined) params.set("risk_pct", String(opts.risk_pct));
    if (opts?.force) params.set("force", "true");
    const qs = params.toString();
    const path = `/stocks/${encodeURIComponent(ticker)}/deep-dive-bundle${qs ? "?" + qs : ""}`;

    const isBrowser = typeof window !== "undefined";
    const isLocalDev = isBrowser && /^https?:\/\/(localhost|127\.0\.0\.1):\d+/.test(window.location.origin);
    const url = isLocalDev ? `http://localhost:8000${path}` : `/api${path}`;

    const res = await fetch(url, { headers: { "Content-Type": "application/json" } });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(body || `HTTP ${res.status} ${res.statusText}`);
    }
    return (await res.json()) as DeepDiveBundle;
  },
  riskNarrative: (ticker: string, force = false) =>
    api.get<RiskNarrative>(
      `/stocks/${encodeURIComponent(ticker)}/risk-narrative${force ? "?force=true" : ""}`
    ),
  bubbleScore: (ticker: string, force = false) =>
    api.get<BubbleScore>(
      `/stocks/${encodeURIComponent(ticker)}/bubble-score${force ? "?force=true" : ""}`
    ),
  bullNarrative: (ticker: string, force = false) =>
    api.get<BullNarrative>(
      `/stocks/${encodeURIComponent(ticker)}/bull-narrative${force ? "?force=true" : ""}`
    ),
  analystConsensus: (ticker: string, force = false) =>
    api.get<AnalystConsensus>(
      `/stocks/${encodeURIComponent(ticker)}/analyst-consensus${force ? "?force=true" : ""}`
    ),
  peerValuation: (ticker: string, force = false) =>
    api.get<PeerValuation>(
      `/stocks/${encodeURIComponent(ticker)}/peer-valuation${force ? "?force=true" : ""}`
    ),
  smartMoney: (ticker: string, force = false) =>
    api.get<SmartMoney>(
      `/stocks/${encodeURIComponent(ticker)}/smart-money${force ? "?force=true" : ""}`
    ),
  newsFeed: (ticker: string, force = false) =>
    api.get<NewsFeed>(
      `/stocks/${encodeURIComponent(ticker)}/news-feed${force ? "?force=true" : ""}`
    ),
  catalystCalendar: (ticker: string, force = false) =>
    api.get<CatalystCalendar>(
      `/stocks/${encodeURIComponent(ticker)}/catalyst-calendar${force ? "?force=true" : ""}`
    ),
  benchmarks: (ticker: string, period: string = "3M") =>
    api.get<Benchmarks>(
      `/stocks/${encodeURIComponent(ticker)}/benchmarks?period=${encodeURIComponent(period)}`
    ),
  recommendation: (ticker: string, force = false) =>
    api.get<Recommendation>(
      `/stocks/${encodeURIComponent(ticker)}/recommendation${force ? "?force=true" : ""}`
    ),
  signalEvidence: (ticker: string, force = false) =>
    api.get<SignalEvidence>(
      `/stocks/${encodeURIComponent(ticker)}/signal-evidence${force ? "?force=true" : ""}`
    ),
  innovation: (ticker: string) =>
    api.get<StockInformation>(`/stocks/${encodeURIComponent(ticker)}/innovation`),
  fdaCatalysts: (ticker: string) =>
    api.get<StockInformation>(`/stocks/${encodeURIComponent(ticker)}/fda-catalysts`),
  entityMatches: (ticker: string) =>
    api.get<EntityMatches>(`/stocks/${encodeURIComponent(ticker)}/entity-matches`),
};

export const earningsApi = {
  explain: (symbol: string, text: string) =>
    api.post<EarningsExplanation>("/earnings/explain", { symbol, text }),
};

export const simulationApi = {
  runs: () => api.get<{ runs: string[] }>("/simulation/runs"),
  cycles: (runId: string) =>
    api.get<{ cycles: string[] }>(`/simulation/cycles?run_id=${encodeURIComponent(runId)}`),
  step: (runId: string, cycleDate: string, step: string) =>
    api.get<{ data: Record<string, unknown> }>(
      `/simulation/step?run_id=${encodeURIComponent(runId)}&cycle_date=${encodeURIComponent(cycleDate)}&step=${encodeURIComponent(step)}`
    ).catch(() => ({ data: {} as Record<string, unknown> })),
  portfolioAgent: (body: {
    start_date: string;
    end_date: string;
    cycle_days?: number;
    initial_capital?: number;
    max_positions?: number;
    min_agents?: number;
    top_n?: number;
    position_size_pct?: number;
  }) =>
    api.post<WalkForwardSimResponse>("/simulation/portfolio-agent", {
      cycle_days: 14,
      initial_capital: 100000,
      max_positions: 5,
      min_agents: 3,
      top_n: 12,
      position_size_pct: 0.10,
      ...body,
    }),
};

export const agentApi = {
  status: () => api.get<AgentStatus>("/agent/status"),
  decisions: (limit = 30) => api.get<AgentDecision[]>(`/agent/decisions?limit=${limit}`),
  config: () => api.get<AgentConfig>("/agent/config"),
  updateConfig: (patch: Partial<AgentConfig>) =>
    api.patch<AgentConfig>("/agent/config", patch),
  reset: (body: {
    starting_capital: number;
    risk_per_trade: number;
    max_positions: number;
    max_buys_per_cycle: number;
    min_opportunity_score: number;
    stop_loss_pct: number;
  }) => api.post<AgentConfig>("/agent/reset", body),
  personalities: () => api.get<AgentPersonalitiesResponse>("/agent/personalities"),
  positions: () => api.get<AgentPosition[]>("/agent/positions"),
  equity: () => api.get<AgentEquityResponse>("/agent/equity"),
  runSingle: () => api.post<AgentCycleResult>("/agent/run/single", {}),
  runMulti: (body: { rm_picks: number; min_score: number }) =>
    api.post<MultiAgentResult>("/agent/run/multi", body),
  chainOfThought: (limitRuns = 5) =>
    api.get<CotResponse>(`/agent/chain-of-thought?limit_runs=${limitRuns}`),
  stop: () => api.post<AgentLifecycle>("/agent/stop", {}),
  resume: () => api.post<AgentLifecycle>("/agent/resume", {}),
  portfolioPick: (body: { top_n?: number; min_agents?: number } = {}) =>
    api.post<PortfolioAgentResponse>("/agent/portfolio-pick", {
      top_n: body.top_n ?? 15,
      min_agents: body.min_agents ?? 3,
    }),
  portfolioExecute: (symbols: string[], reasons: Record<string, string> = {}) =>
    api.post<PortfolioExecuteResponse>("/agent/portfolio-pick/execute", {
      symbols, reasons,
    }),
};

export const dataSourcesApi = {
  rateLimits: () => api.get<DataSourcesResponse>("/data-sources/rate-limits"),
};

export const universeApi = {
  list: (opts?: {
    tier?: string;          // comma-separated, e.g. "A,B"
    industry?: string;
    sector?: string;
    limit?: number;
    offset?: number;
  }) => {
    const params = new URLSearchParams();
    if (opts?.tier) params.set("tier", opts.tier);
    if (opts?.industry) params.set("industry", opts.industry);
    if (opts?.sector) params.set("sector", opts.sector);
    if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
    if (opts?.offset !== undefined) params.set("offset", String(opts.offset));
    const qs = params.toString();
    return api.get<UniverseResponse>(`/universe${qs ? "?" + qs : ""}`);
  },
};

export const newsImpactApi = {
  analyze: (text: string) =>
    api.post<NewsImpactResponse>("/news-impact", { text }),
};

export const contextSearchApi = {
  // Context Search goes through the LLM-mediated expander which can take
  // 5-15 seconds end-to-end. Bypass the Next.js dev proxy in dev so we
  // don't hit the proxy's 60s ceiling on slow Claude responses.
  search: async (text: string, limit = 40): Promise<ContextSearchResponse> => {
    const isBrowser = typeof window !== "undefined";
    const isLocalDev = isBrowser && /^https?:\/\/(localhost|127\.0\.0\.1):\d+/.test(window.location.origin);
    const url = isLocalDev ? "http://localhost:8000/context-search" : "/api/context-search";
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, limit }),
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(body || `HTTP ${res.status} ${res.statusText}`);
    }
    return (await res.json()) as ContextSearchResponse;
  },
};

export const graphApi = {
  peers: (symbol: string, max_results = 20) =>
    api.get<PeerListResponse>(
      `/graph/stock/${encodeURIComponent(symbol)}/peers?max_results=${max_results}`
    ),
  neighborhood: (symbol: string) =>
    api.get<NeighborhoodResponse>(
      `/graph/stock/${encodeURIComponent(symbol)}/neighborhood`
    ),
  topHolders: (symbol: string, max_results = 20) =>
    api.get<TopHoldersResponse>(
      `/graph/stock/${encodeURIComponent(symbol)}/holders?max_results=${max_results}`
    ),
  institutionHoldings: (cik: string, max_results = 50) =>
    api.get<InstitutionHoldingsResponse>(
      `/graph/institution/${encodeURIComponent(cik)}/holdings?max_results=${max_results}`
    ),
};

export const freshnessApi = {
  queue: () => api.get<FreshnessQueueResponse>("/freshness/queue"),
  acknowledge: (symbol: string, action: "re_extract" | "skip_30d" | "pin_current") =>
    api.post<{ symbol: string; ok: boolean; new_status?: string; error?: string }>(
      "/freshness/acknowledge",
      { symbol, action }
    ),
};

export const refreshApi = {
  kinds: () => api.get<{ kinds: RefreshKindMeta[] }>("/refresh/kinds"),
  start: (kind: string) => api.post<RefreshJob>(`/refresh/${encodeURIComponent(kind)}`, {}),
  job: (id: number) => api.get<RefreshJob>(`/refresh/jobs/${id}`),
  jobs: (kind?: string, limit = 20) => {
    const params = new URLSearchParams();
    if (kind) params.set("kind", kind);
    params.set("limit", String(limit));
    return api.get<{ jobs: RefreshJob[] }>(`/refresh/jobs?${params.toString()}`);
  },
  latest: () => api.get<Record<string, RefreshJob>>("/refresh/latest"),
  quality: () => api.get<RefreshQualitySnapshot>("/refresh/quality"),
};

export const trackRecordApi = {
  summary: (opts?: { source?: TrackRecordSource; symbol?: string; days?: number }) => {
    const params = new URLSearchParams();
    if (opts?.source) params.set("source", opts.source);
    if (opts?.symbol) params.set("symbol", opts.symbol);
    if (opts?.days !== undefined) params.set("days", String(opts.days));
    const qs = params.toString();
    return api.get<TrackRecord>(`/ai/track-record${qs ? "?" + qs : ""}`);
  },
  decisions: (opts?: { source?: TrackRecordSource; symbol?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.source) params.set("source", opts.source);
    if (opts?.symbol) params.set("symbol", opts.symbol);
    params.set("limit", String(opts?.limit ?? 50));
    return api.get<DecisionsRecent>(`/ai/decisions/recent?${params.toString()}`);
  },
  top: (opts?: { limit?: number; days?: number }) => {
    const params = new URLSearchParams();
    params.set("limit", String(opts?.limit ?? 10));
    if (opts?.days !== undefined) params.set("days", String(opts.days));
    return api.get<TopWinsLosses>(`/ai/decisions/top?${params.toString()}`);
  },
  evaluateNow: () => api.post<EvaluatorRun>("/ai/decisions/evaluate-now", {}),
};
