"use client";

import { useState, useEffect } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { BarChart3, Loader2, Plus, X, Search, Layers, Bot, PieChart } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { SignalAccuracyCard } from "@/components/prove-it/signal-card";
import { SignalChart } from "@/components/prove-it/signal-chart";
import { PortfolioEquityChart } from "@/components/prove-it/portfolio-equity-chart";
import { AiDecisionRow } from "@/components/prove-it/ai-decision-row";
import { AiStrategyReference } from "@/components/prove-it/ai-strategy-reference";
import { Skeleton } from "@/components/ui/skeleton";
import { SimulationReplay } from "@/components/simulation-replay";
import { TickerSearchInput } from "@/components/ui/ticker-search-input";
import { StockAnchor } from "@/components/prove-it/stock-anchor";
import { AiProgressEstimator } from "@/components/prove-it/ai-progress-estimator";
import { AiMultiStockTable } from "@/components/prove-it/ai-multi-stock-table";
import { backtestApi, watchlistApi } from "@/lib/api/endpoints";
import { cn, formatCurrency, formatPercent } from "@/lib/utils";

const PERIODS = ["1D", "1W", "1M", "3M", "6M", "1Y"];
const SORTS = [
  { key: "ev", label: "Expected Value" },
  { key: "win", label: "Win Rate" },
  { key: "ret", label: "Avg Return" },
  { key: "trades", label: "Trade Count" },
];
const TABS = [
  "Signal Accuracy",
  "Signal Explorer",
  "Multi-Stock Compare",
  "Portfolio Simulation",
  "AI Analyst",
] as const;
type Tab = (typeof TABS)[number];

function gradeColor(grade?: string | null) {
  if (!grade) return "text-text-muted";
  if (grade === "A+" || grade === "A") return "text-accent-greenSoft";
  if (grade === "B+" || grade === "B") return "text-accent-blue";
  if (grade === "C") return "text-accent-amber";
  return "text-accent-redSoft";
}

export default function ProveItPage() {
  const [tab, setTab] = useState<Tab>("Signal Accuracy");
  const [symbol, setSymbol] = useState("AAPL");
  const [period, setPeriod] = useState("1M");
  const [category, setCategory] = useState("All Signals");
  const [sort, setSort] = useState("ev");
  const [signal, setSignal] = useState("rsi_oversold");

  // Multi-stock state
  const [multiSymbols, setMultiSymbols] = useState<string[]>([]);
  const [multiInput, setMultiInput] = useState("");

  // Portfolio Simulation state
  const [pfSymbols, setPfSymbols] = useState<string[]>([]);
  const [pfInput, setPfInput] = useState("");
  const [pfCapital, setPfCapital] = useState(100_000);
  const [pfPosSize, setPfPosSize] = useState(20);   // %

  // AI Analyst state
  const [aiCycles, setAiCycles] = useState(8);
  // Multi-stock AI Analyst — anchor + additional symbols
  const [aiMultiEnabled, setAiMultiEnabled] = useState(false);
  const [aiExtraSymbols, setAiExtraSymbols] = useState<string[]>([]);
  const [aiExtraInput, setAiExtraInput] = useState("");
  const [aiMode, setAiMode] = useState<"single" | "multi">("single");

  const { data: catalog } = useQuery({
    queryKey: ["backtest", "signals"],
    queryFn: () => backtestApi.signals(),
    staleTime: Infinity,
  });

  const { data: watchlist = [] } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.list(),
    staleTime: 30_000,
  });

  // Tab 1: All signals
  const allMutation = useMutation({
    mutationFn: (vars: { sym: string; per: string; cat: string }) =>
      backtestApi.all(vars.sym, vars.per, vars.cat),
  });

  // Tab 2: Single signal explorer
  const singleMutation = useMutation({
    mutationFn: (vars: { sym: string; sig: string; per: string }) =>
      backtestApi.single(vars.sym, vars.sig, vars.per),
  });

  // Tab 3: Multi-stock compare
  const multiMutation = useMutation({
    mutationFn: (vars: { syms: string[]; sig: string; per: string }) =>
      backtestApi.multiStock(vars.syms, vars.sig, vars.per),
  });

  // Tab 4: Portfolio simulation
  const pfMutation = useMutation({
    mutationFn: (vars: { syms: string[]; strat: string; cap: number; size: number }) =>
      backtestApi.portfolio(vars.syms, vars.strat, vars.cap, vars.size / 100),
  });

  // Tab 5: AI analyst
  const aiMutation = useMutation({
    mutationFn: (vars: { sym: string; per: string; cycles: number; mode: "single" | "multi" }) =>
      backtestApi.aiAnalyst(vars.sym, vars.per, vars.cycles, vars.mode),
  });
  // Tab 5b: AI analyst on multiple stocks
  const aiMultiMutation = useMutation({
    mutationFn: (vars: { syms: string[]; per: string; cycles: number; mode: "single" | "multi" }) =>
      backtestApi.aiAnalystMulti(vars.syms, vars.per, vars.cycles, vars.mode),
  });

  // Default category list when catalog loads
  const categories = catalog?.categories || ["All Signals"];
  const signalOptions = catalog?.signals || [];

  // Sorting helper for All Signals
  const sortedAllResults = (() => {
    const rows = allMutation.data?.results || [];
    const cloned = [...rows];
    if (sort === "win") cloned.sort((a, b) => b.win_rate - a.win_rate);
    else if (sort === "ret") cloned.sort((a, b) => b.avg_return - a.avg_return);
    else if (sort === "trades") cloned.sort((a, b) => b.total_trades - a.total_trades);
    else cloned.sort((a, b) => b.win_rate * b.avg_return - a.win_rate * a.avg_return);
    return cloned;
  })();

  return (
    <div>
      <PageHeader
        icon={BarChart3}
        title="Prove It"
        subtitle="Backtest signals against historical data — did they actually make money?"
        accent="text-accent-cyan"
        iconBg="bg-accent-cyan/10"
      />

      <div className="mb-6">
        <SimulationReplay step="trades" accent="cyan" />
      </div>

      {/* Page-level stock anchor — every backtest below operates on this */}
      <div className="mb-6">
        <StockAnchor symbol={symbol} onChange={setSymbol} />
      </div>

      {/* Tabs */}
      <div className="flex gap-0.5 mb-6 p-1 rounded-lg bg-bg-card border border-bg-border overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "flex-1 min-w-fit px-3 py-2 rounded-md text-[13px] font-medium transition-all duration-150 whitespace-nowrap",
              tab === t
                ? "bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/40 shadow-sm"
                : "text-text-secondary hover:text-text-primary hover:bg-bg-card2 border border-transparent",
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {/* ─── Tab 1: Signal Accuracy ─── */}
      {tab === "Signal Accuracy" && (
        <div>
          <div className="card p-4 mb-6 flex flex-wrap items-center gap-x-6 gap-y-3">
            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wider text-text-muted">Hold</span>
              <div className="flex gap-1">
                {PERIODS.map((p) => (
                  <button
                    key={p}
                    onClick={() => setPeriod(p)}
                    className={cn(
                      "px-2.5 py-1 rounded-md text-xs font-mono font-medium transition-colors border",
                      period === p
                        ? "bg-accent-cyan/10 text-accent-cyan border-accent-cyan/40"
                        : "bg-bg-base text-text-secondary border-bg-border hover:text-text-primary"
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wider text-text-muted">Category</span>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-cyan/60"
              >
                {categories.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wider text-text-muted">Sort</span>
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value)}
                className="bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-cyan/60"
              >
                {SORTS.map((s) => (
                  <option key={s.key} value={s.key}>{s.label}</option>
                ))}
              </select>
            </div>

            <button
              onClick={() => allMutation.mutate({ sym: symbol, per: period, cat: category })}
              disabled={!symbol || allMutation.isPending}
              className="ml-auto bg-accent-cyan/10 border border-accent-cyan/40 hover:bg-accent-cyan/20 text-accent-cyan px-4 py-1.5 rounded-md text-sm font-medium flex items-center gap-2 transition-colors disabled:opacity-50"
            >
              {allMutation.isPending && <Loader2 size={14} className="animate-spin" />}
              {allMutation.isPending ? "Running…" : "Backtest All Signals"}
            </button>
          </div>

          {allMutation.isError && (
            <div className="card p-4 border-l-4 border-accent-red/40 mb-4">
              <p className="text-accent-redSoft text-sm">{(allMutation.error as Error).message}</p>
            </div>
          )}

          {allMutation.isPending && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-44" />)}
            </div>
          )}

          {allMutation.data && (
            <>
              {allMutation.data.error && (
                <div className="card p-4 border-l-4 border-accent-amber/40 mb-4">
                  <p className="text-accent-amber text-sm">{allMutation.data.error}</p>
                </div>
              )}

              {sortedAllResults.length > 0 && (
                <>
                  <div className="card p-4 mb-4 border-l-4 border-accent-green/40 bg-accent-green/5">
                    <div className="text-xs uppercase tracking-wider text-text-muted">Best Signal</div>
                    <div className="text-base font-bold text-accent-greenSoft mt-1">
                      {sortedAllResults[0].signal_name.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
                    </div>
                    <p className="text-xs text-text-secondary mt-1">
                      {(sortedAllResults[0].win_rate * 100).toFixed(0)}% win rate · {formatPercent(sortedAllResults[0].avg_return)} avg return · {sortedAllResults[0].total_trades} trades
                    </p>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                    {sortedAllResults.map((r, i) => (
                      <SignalAccuracyCard key={r.signal_name} row={r} rank={i} />
                    ))}
                  </div>
                </>
              )}

              {sortedAllResults.length === 0 && !allMutation.data.error && (
                <div className="card p-10 text-center text-text-muted text-sm">
                  No signal triggers in this category for the selected hold period.
                </div>
              )}
            </>
          )}

          {!allMutation.data && !allMutation.isPending && (
            <div className="card p-10 text-center text-text-muted text-sm">
              Pick a stock and click <span className="text-accent-cyan font-medium">Backtest All Signals</span> to see results.
            </div>
          )}
        </div>
      )}

      {/* ─── Tab 2: Signal Explorer ─── */}
      {tab === "Signal Explorer" && (
        <div>
          <div className="card p-4 mb-6 flex flex-wrap items-center gap-x-6 gap-y-3">
            <div className="flex items-center gap-2 flex-1 min-w-[280px]">
              <span className="text-xs uppercase tracking-wider text-text-muted">Signal</span>
              <select
                value={signal}
                onChange={(e) => setSignal(e.target.value)}
                className="flex-1 bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-cyan/60"
              >
                {signalOptions.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.label} — {s.description}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs uppercase tracking-wider text-text-muted">Hold</span>
              <div className="flex gap-1">
                {PERIODS.map((p) => (
                  <button
                    key={p}
                    onClick={() => setPeriod(p)}
                    className={cn(
                      "px-2.5 py-1 rounded-md text-xs font-mono font-medium transition-colors border",
                      period === p
                        ? "bg-accent-cyan/10 text-accent-cyan border-accent-cyan/40"
                        : "bg-bg-base text-text-secondary border-bg-border hover:text-text-primary"
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={() => singleMutation.mutate({ sym: symbol, sig: signal, per: period })}
              disabled={!symbol || !signal || singleMutation.isPending}
              className="bg-accent-cyan/10 border border-accent-cyan/40 hover:bg-accent-cyan/20 text-accent-cyan px-4 py-1.5 rounded-md text-sm font-medium flex items-center gap-2 transition-colors disabled:opacity-50"
            >
              {singleMutation.isPending && <Loader2 size={14} className="animate-spin" />}
              Run
            </button>
          </div>

          {singleMutation.isPending && <Skeleton className="h-96" />}

          {singleMutation.data && (
            <div className="space-y-4">
              {singleMutation.data.error && (
                <div className="card p-4 border-l-4 border-accent-red/40">
                  <p className="text-accent-redSoft text-sm">{singleMutation.data.error}</p>
                </div>
              )}

              {singleMutation.data.result && singleMutation.data.candles.length > 0 && (
                <>
                  <SignalChart
                    candles={singleMutation.data.candles}
                    trades={singleMutation.data.result.trades}
                    symbol={singleMutation.data.symbol}
                    signalLabel={singleMutation.data.signal_label}
                    period={singleMutation.data.period}
                  />

                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                    <div className="card p-4 text-center">
                      <div className="text-[10px] uppercase tracking-wider text-text-muted">Win Rate</div>
                      <div className={cn(
                        "text-xl font-bold tabular-nums mt-1",
                        singleMutation.data.result.win_rate >= 0.65 ? "text-accent-greenSoft"
                          : singleMutation.data.result.win_rate < 0.45 ? "text-accent-redSoft"
                          : "text-accent-amber"
                      )}>
                        {(singleMutation.data.result.win_rate * 100).toFixed(0)}%
                      </div>
                    </div>
                    <div className="card p-4 text-center">
                      <div className="text-[10px] uppercase tracking-wider text-text-muted">Avg Return</div>
                      <div className={cn(
                        "text-xl font-bold tabular-nums mt-1",
                        singleMutation.data.result.avg_return >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft"
                      )}>
                        {formatPercent(singleMutation.data.result.avg_return)}
                      </div>
                    </div>
                    <div className="card p-4 text-center">
                      <div className="text-[10px] uppercase tracking-wider text-text-muted">Trades</div>
                      <div className="text-xl font-bold tabular-nums mt-1">
                        {singleMutation.data.result.total_trades}
                      </div>
                    </div>
                    <div className="card p-4 text-center">
                      <div className="text-[10px] uppercase tracking-wider text-text-muted">Best</div>
                      <div className="text-xl font-bold tabular-nums mt-1 text-accent-greenSoft">
                        {formatPercent(singleMutation.data.result.max_gain)}
                      </div>
                    </div>
                    <div className="card p-4 text-center">
                      <div className="text-[10px] uppercase tracking-wider text-text-muted">Worst</div>
                      <div className="text-xl font-bold tabular-nums mt-1 text-accent-redSoft">
                        {formatPercent(singleMutation.data.result.max_loss)}
                      </div>
                    </div>
                  </div>

                  {singleMutation.data.result.trades.length > 0 && (
                    <div className="card p-5">
                      <h3 className="text-sm font-semibold mb-3">Trades ({singleMutation.data.result.trades.length})</h3>
                      <div className="overflow-x-auto -mx-2">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-text-muted text-left uppercase tracking-wider">
                              <th className="px-2 py-2"></th>
                              <th className="px-2 py-2">Entry</th>
                              <th className="px-2 py-2 text-right">$</th>
                              <th className="px-2 py-2">Exit</th>
                              <th className="px-2 py-2 text-right">$</th>
                              <th className="px-2 py-2 text-right">Hold</th>
                              <th className="px-2 py-2 text-right">P&amp;L</th>
                            </tr>
                          </thead>
                          <tbody>
                            {singleMutation.data.result.trades.slice(0, 50).map((t, i) => (
                              <tr key={i} className="border-t border-bg-border">
                                <td className="px-2 py-2">
                                  <span className={cn(
                                    "text-base leading-none",
                                    t.outcome === "win" ? "text-accent-greenSoft" : "text-accent-redSoft"
                                  )}>
                                    {t.outcome === "win" ? "●" : "○"}
                                  </span>
                                </td>
                                <td className="px-2 py-2 tabular-nums">{t.entry_date}</td>
                                <td className="px-2 py-2 text-right tabular-nums">${t.entry_price.toFixed(2)}</td>
                                <td className="px-2 py-2 tabular-nums">{t.exit_date}</td>
                                <td className="px-2 py-2 text-right tabular-nums">${t.exit_price.toFixed(2)}</td>
                                <td className="px-2 py-2 text-right tabular-nums">{t.hold_days}d</td>
                                <td className={cn(
                                  "px-2 py-2 text-right tabular-nums font-medium",
                                  t.pnl_percent >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft"
                                )}>
                                  {formatPercent(t.pnl_percent)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {!singleMutation.data && !singleMutation.isPending && (
            <div className="card p-10 text-center text-text-muted text-sm">
              Pick a stock + signal and click <span className="text-accent-cyan font-medium">Run</span>.
            </div>
          )}
        </div>
      )}

      {/* ─── Tab 3: Multi-Stock Compare ─── */}
      {tab === "Multi-Stock Compare" && (
        <div>
          <div className="card p-5 mb-6">
            <h3 className="text-sm font-semibold mb-3">Configure</h3>

            <div className="flex items-center gap-2 mb-3 flex-wrap">
              <span className="text-xs uppercase tracking-wider text-text-muted">Signal</span>
              <select
                value={signal}
                onChange={(e) => setSignal(e.target.value)}
                className="flex-1 bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-cyan/60"
              >
                {signalOptions.map((s) => (
                  <option key={s.name} value={s.name}>{s.label} — {s.description}</option>
                ))}
              </select>
              <span className="text-xs uppercase tracking-wider text-text-muted ml-2">Hold</span>
              <div className="flex gap-1">
                {PERIODS.map((p) => (
                  <button
                    key={p}
                    onClick={() => setPeriod(p)}
                    className={cn(
                      "px-2.5 py-1 rounded-md text-xs font-mono font-medium transition-colors border",
                      period === p
                        ? "bg-accent-cyan/10 text-accent-cyan border-accent-cyan/40"
                        : "bg-bg-base text-text-secondary border-bg-border hover:text-text-primary"
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                const v = multiInput.trim().toUpperCase();
                if (v && !multiSymbols.includes(v) && multiSymbols.length < 8) {
                  setMultiSymbols([...multiSymbols, v]);
                  setMultiInput("");
                }
              }}
              className="flex items-center gap-2 mb-3"
            >
              <div className="relative flex-1">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
                <input
                  value={multiInput}
                  onChange={(e) => setMultiInput(e.target.value.toUpperCase())}
                  placeholder="Add ticker"
                  maxLength={10}
                  disabled={multiSymbols.length >= 8}
                  className="w-full bg-bg-base border border-bg-border rounded-md pl-9 pr-3 py-2 text-sm font-mono focus:outline-none focus:border-accent-cyan/60 disabled:opacity-50"
                />
              </div>
              <button
                type="submit"
                disabled={!multiInput.trim() || multiSymbols.length >= 8}
                className="bg-accent-cyan/10 border border-accent-cyan/40 hover:bg-accent-cyan/20 text-accent-cyan px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
              >
                <Plus size={14} /> Add
              </button>
            </form>

            {watchlist.length > 0 && (
              <div className="mb-3">
                <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1.5">From watchlist</div>
                <div className="flex flex-wrap gap-1.5">
                  {watchlist.map((w) => (
                    <button
                      key={w.symbol}
                      onClick={() => {
                        if (!multiSymbols.includes(w.symbol) && multiSymbols.length < 8) {
                          setMultiSymbols([...multiSymbols, w.symbol]);
                        }
                      }}
                      disabled={multiSymbols.includes(w.symbol) || multiSymbols.length >= 8}
                      className="badge bg-bg-base border-bg-border text-text-secondary hover:border-accent-cyan/40 hover:text-accent-cyan font-mono disabled:opacity-30"
                    >
                      + {w.symbol}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="mb-3">
              <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1.5">
                Selected ({multiSymbols.length}/8)
              </div>
              {multiSymbols.length === 0 ? (
                <p className="text-xs text-text-muted">No tickers selected.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {multiSymbols.map((s) => (
                    <button
                      key={s}
                      onClick={() => setMultiSymbols(multiSymbols.filter((x) => x !== s))}
                      className="badge bg-accent-cyan/10 text-accent-cyan border-accent-cyan/40 hover:bg-accent-cyan/20 font-mono"
                    >
                      {s} <X size={11} className="ml-1 opacity-60" />
                    </button>
                  ))}
                </div>
              )}
            </div>

            <button
              onClick={() => {
                // Always include the page-level anchor stock; de-dupe in case user re-added it
                const syms = [symbol, ...multiSymbols.filter((s) => s !== symbol)];
                multiMutation.mutate({ syms, sig: signal, per: period });
              }}
              disabled={multiSymbols.filter((s) => s !== symbol).length === 0 || multiMutation.isPending}
              className="w-full bg-accent-cyan/10 border border-accent-cyan/40 hover:bg-accent-cyan/20 text-accent-cyan px-4 py-2 rounded-md text-sm font-medium flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
            >
              {multiMutation.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Layers size={14} />
              )}
              {(() => {
                const extra = multiSymbols.filter((s) => s !== symbol).length;
                const total = extra + 1; // anchor always included
                if (multiMutation.isPending) return "Running…";
                if (extra === 0) return `Add at least 1 more stock to compare with ${symbol}`;
                return `Compare ${symbol} + ${extra} other${extra === 1 ? "" : "s"} (${total} total)`;
              })()}
            </button>
          </div>

          {multiMutation.isError && (
            <div className="card p-4 border-l-4 border-accent-red/40 mb-4">
              <p className="text-accent-redSoft text-sm">{(multiMutation.error as Error).message}</p>
            </div>
          )}

          {multiMutation.data && (
            <div className="card p-5">
              <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                <div>
                  <h3 className="text-sm font-semibold">{multiMutation.data.signal_label}</h3>
                  <p className="text-xs text-text-muted">{multiMutation.data.signal_description}</p>
                </div>
                <span className="text-xs text-text-muted">
                  {multiMutation.data.period} hold
                </span>
              </div>
              <div className="overflow-x-auto -mx-2">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-text-muted text-left uppercase tracking-wider">
                      <th className="px-2 py-2">Symbol</th>
                      <th className="px-2 py-2 text-right">Win Rate</th>
                      <th className="px-2 py-2 text-right">Avg Return</th>
                      <th className="px-2 py-2 text-right">Trades</th>
                      <th className="px-2 py-2 text-right">Best</th>
                      <th className="px-2 py-2 text-right">Worst</th>
                      <th className="px-2 py-2 text-right">Grade</th>
                    </tr>
                  </thead>
                  <tbody>
                    {multiMutation.data.rows.map((r) => (
                      <tr key={r.symbol} className="border-t border-bg-border">
                        <td className="px-2 py-3 font-mono font-bold">{r.symbol}</td>
                        {r.error ? (
                          <td colSpan={6} className="px-2 py-3 text-accent-redSoft text-xs">{r.error}</td>
                        ) : (
                          <>
                            <td className={cn(
                              "px-2 py-3 text-right tabular-nums",
                              (r.win_rate ?? 0) >= 0.65 ? "text-accent-greenSoft"
                                : (r.win_rate ?? 0) < 0.45 ? "text-accent-redSoft"
                                : "text-accent-amber"
                            )}>
                              {r.win_rate != null ? `${(r.win_rate * 100).toFixed(0)}%` : "—"}
                            </td>
                            <td className={cn(
                              "px-2 py-3 text-right tabular-nums",
                              (r.avg_return ?? 0) >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft"
                            )}>
                              {r.avg_return != null ? formatPercent(r.avg_return) : "—"}
                            </td>
                            <td className="px-2 py-3 text-right tabular-nums">{r.total_trades ?? 0}</td>
                            <td className="px-2 py-3 text-right tabular-nums text-accent-greenSoft">
                              {r.max_gain != null ? formatPercent(r.max_gain) : "—"}
                            </td>
                            <td className="px-2 py-3 text-right tabular-nums text-accent-redSoft">
                              {r.max_loss != null ? formatPercent(r.max_loss) : "—"}
                            </td>
                            <td className={cn("px-2 py-3 text-right font-bold", gradeColor(r.grade))}>
                              {r.grade || "—"}
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─── Tab 4: Portfolio Simulation ─── */}
      {tab === "Portfolio Simulation" && (
        <div>
          <div className="card p-5 mb-6">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <PieChart size={14} className="text-accent-cyan" />
              Configure Portfolio
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider text-text-muted">Strategy</label>
                <select
                  value={signal}
                  onChange={(e) => setSignal(e.target.value)}
                  className="mt-1 w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-cyan/60"
                >
                  {signalOptions.map((s) => (
                    <option key={s.name} value={s.name}>{s.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider text-text-muted">Initial Capital</label>
                <input
                  type="number"
                  min={1000}
                  value={pfCapital}
                  onChange={(e) => setPfCapital(Math.max(1000, Number(e.target.value) || 100000))}
                  className="mt-1 w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs tabular-nums focus:outline-none focus:border-accent-cyan/60"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider text-text-muted">Position Size %</label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={pfPosSize}
                  onChange={(e) => setPfPosSize(Math.max(1, Math.min(100, Number(e.target.value) || 20)))}
                  className="mt-1 w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs tabular-nums focus:outline-none focus:border-accent-cyan/60"
                />
              </div>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                const v = pfInput.trim().toUpperCase();
                if (v && !pfSymbols.includes(v) && pfSymbols.length < 12) {
                  setPfSymbols([...pfSymbols, v]);
                  setPfInput("");
                }
              }}
              className="flex items-center gap-2 mb-3"
            >
              <div className="relative flex-1">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
                <input
                  value={pfInput}
                  onChange={(e) => setPfInput(e.target.value.toUpperCase())}
                  placeholder="Add ticker"
                  maxLength={10}
                  disabled={pfSymbols.length >= 12}
                  className="w-full bg-bg-base border border-bg-border rounded-md pl-9 pr-3 py-2 text-sm font-mono focus:outline-none focus:border-accent-cyan/60 disabled:opacity-50"
                />
              </div>
              <button
                type="submit"
                disabled={!pfInput.trim() || pfSymbols.length >= 12}
                className="bg-accent-cyan/10 border border-accent-cyan/40 hover:bg-accent-cyan/20 text-accent-cyan px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
              >
                <Plus size={14} /> Add
              </button>
            </form>

            {watchlist.length > 0 && (
              <div className="mb-3">
                <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1.5">From watchlist</div>
                <div className="flex flex-wrap gap-1.5">
                  {watchlist.map((w) => (
                    <button
                      key={w.symbol}
                      onClick={() => {
                        if (!pfSymbols.includes(w.symbol) && pfSymbols.length < 12) {
                          setPfSymbols([...pfSymbols, w.symbol]);
                        }
                      }}
                      disabled={pfSymbols.includes(w.symbol) || pfSymbols.length >= 12}
                      className="badge bg-bg-base border-bg-border text-text-secondary hover:border-accent-cyan/40 hover:text-accent-cyan font-mono disabled:opacity-30"
                    >
                      + {w.symbol}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="mb-3">
              <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1.5">
                Selected ({pfSymbols.length}/12)
              </div>
              {pfSymbols.length === 0 ? (
                <p className="text-xs text-text-muted">No tickers selected.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {pfSymbols.map((s) => (
                    <button
                      key={s}
                      onClick={() => setPfSymbols(pfSymbols.filter((x) => x !== s))}
                      className="badge bg-accent-cyan/10 text-accent-cyan border-accent-cyan/40 hover:bg-accent-cyan/20 font-mono"
                    >
                      {s} <X size={11} className="ml-1 opacity-60" />
                    </button>
                  ))}
                </div>
              )}
            </div>

            <button
              onClick={() => {
                const syms = [symbol, ...pfSymbols.filter((s) => s !== symbol)];
                pfMutation.mutate({ syms, strat: signal, cap: pfCapital, size: pfPosSize });
              }}
              disabled={pfMutation.isPending}
              className="w-full bg-accent-cyan/10 border border-accent-cyan/40 hover:bg-accent-cyan/20 text-accent-cyan px-4 py-2 rounded-md text-sm font-medium flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
            >
              {pfMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <PieChart size={14} />}
              {(() => {
                const extra = pfSymbols.filter((s) => s !== symbol).length;
                const total = extra + 1;
                if (pfMutation.isPending) return "Simulating…";
                return `Simulate Portfolio: ${symbol}${extra > 0 ? ` + ${extra} other${extra === 1 ? "" : "s"}` : ""} (${total} stock${total === 1 ? "" : "s"})`;
              })()}
            </button>
          </div>

          {pfMutation.data && pfMutation.data.error && (
            <div className="card p-4 border-l-4 border-accent-red/40 mb-4">
              <p className="text-accent-redSoft text-sm">{pfMutation.data.error}</p>
            </div>
          )}

          {pfMutation.data && !pfMutation.data.error && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
                <div className="card p-4 text-center">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Final Value</div>
                  <div className="text-base font-bold tabular-nums mt-1">
                    {formatCurrency(pfMutation.data.final_value)}
                  </div>
                </div>
                <div className="card p-4 text-center">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Return</div>
                  <div className={cn(
                    "text-base font-bold tabular-nums mt-1",
                    pfMutation.data.total_return >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft"
                  )}>
                    {formatPercent(pfMutation.data.total_return)}
                  </div>
                </div>
                <div className="card p-4 text-center">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Annualized</div>
                  <div className={cn(
                    "text-base font-bold tabular-nums mt-1",
                    pfMutation.data.annualized_return >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft"
                  )}>
                    {formatPercent(pfMutation.data.annualized_return)}
                  </div>
                </div>
                <div className="card p-4 text-center">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Sharpe</div>
                  <div className={cn(
                    "text-base font-bold tabular-nums mt-1",
                    pfMutation.data.sharpe_ratio >= 1 ? "text-accent-greenSoft"
                      : pfMutation.data.sharpe_ratio <= 0 ? "text-accent-redSoft"
                      : "text-accent-amber"
                  )}>
                    {pfMutation.data.sharpe_ratio.toFixed(2)}
                  </div>
                </div>
                <div className="card p-4 text-center">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Max DD</div>
                  <div className="text-base font-bold tabular-nums mt-1 text-accent-redSoft">
                    {formatPercent(pfMutation.data.max_drawdown)}
                  </div>
                </div>
                <div className="card p-4 text-center">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Win Rate</div>
                  <div className="text-base font-bold tabular-nums mt-1">
                    {(pfMutation.data.win_rate * 100).toFixed(0)}%
                  </div>
                </div>
                <div className="card p-4 text-center">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Alpha vs SPY</div>
                  <div className={cn(
                    "text-base font-bold tabular-nums mt-1",
                    pfMutation.data.alpha >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft"
                  )}>
                    {formatPercent(pfMutation.data.alpha)}
                  </div>
                </div>
              </div>

              <PortfolioEquityChart points={pfMutation.data.equity_curve} />

              {pfMutation.data.trades.length > 0 && (
                <div className="card p-5">
                  <h3 className="text-sm font-semibold mb-3">
                    Trades ({pfMutation.data.total_trades})
                  </h3>
                  <div className="overflow-x-auto -mx-2">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-text-muted text-left uppercase tracking-wider">
                          <th className="px-2 py-2"></th>
                          <th className="px-2 py-2">Symbol</th>
                          <th className="px-2 py-2">Entry</th>
                          <th className="px-2 py-2 text-right">$</th>
                          <th className="px-2 py-2">Exit</th>
                          <th className="px-2 py-2 text-right">$</th>
                          <th className="px-2 py-2 text-right">Hold</th>
                          <th className="px-2 py-2 text-right">P&amp;L</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pfMutation.data.trades.slice(0, 50).map((t, i) => (
                          <tr key={i} className="border-t border-bg-border">
                            <td className="px-2 py-2">
                              <span className={cn(
                                "text-base leading-none",
                                t.outcome === "win" ? "text-accent-greenSoft" : "text-accent-redSoft"
                              )}>
                                {t.outcome === "win" ? "●" : "○"}
                              </span>
                            </td>
                            <td className="px-2 py-2 font-mono">{t.symbol}</td>
                            <td className="px-2 py-2 tabular-nums">{t.entry_date}</td>
                            <td className="px-2 py-2 text-right tabular-nums">${t.entry_price.toFixed(2)}</td>
                            <td className="px-2 py-2 tabular-nums">{t.exit_date}</td>
                            <td className="px-2 py-2 text-right tabular-nums">${t.exit_price.toFixed(2)}</td>
                            <td className="px-2 py-2 text-right tabular-nums">{t.hold_days}d</td>
                            <td className={cn(
                              "px-2 py-2 text-right tabular-nums font-medium",
                              t.pnl_percent >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft"
                            )}>
                              {formatPercent(t.pnl_percent)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ─── Tab 5: AI Analyst ─── */}
      {tab === "AI Analyst" && (
        <div>
          <div className="card p-5 mb-6">
            <div className="flex items-center gap-2 mb-4">
              <Bot size={14} className="text-accent-pink" />
              <h3 className="text-sm font-semibold tracking-tight">AI Analyst Backtest</h3>
              <span className="ml-auto text-[10px] text-text-muted">
                Walk-forward · Claude sees the same data a human would
              </span>
            </div>

            {/* Mode toggle */}
            <div className="mb-4">
              <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold mb-1.5">Mode</div>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => setAiMode("single")}
                  className={cn(
                    "card p-3 text-left transition-all",
                    aiMode === "single"
                      ? "border-accent-pink/60 bg-accent-pink/5 card-glow-amber"
                      : "hover:border-bg-borderHi"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <Bot size={14} className={aiMode === "single" ? "text-accent-pink" : "text-text-muted"} />
                    <span className={cn("text-sm font-bold", aiMode === "single" ? "text-accent-pink" : "")}>
                      Single Agent
                    </span>
                  </div>
                  <p className="text-[11px] text-text-muted mt-1 leading-snug">
                    One Claude call per cycle. Fast baseline. ~{aiCycles * 3}s total.
                  </p>
                </button>
                <button
                  onClick={() => setAiMode("multi")}
                  className={cn(
                    "card p-3 text-left transition-all",
                    aiMode === "multi"
                      ? "border-accent-violet/60 bg-accent-violet/5 card-glow-violet"
                      : "hover:border-bg-borderHi"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm">🤝</span>
                    <span className={cn("text-sm font-bold", aiMode === "multi" ? "text-accent-violet" : "")}>
                      Multi-Agent · 7 personalities vote
                    </span>
                  </div>
                  <p className="text-[11px] text-text-muted mt-1 leading-snug">
                    🚀 Momentum · 📊 Value · 🔄 Contrarian · 🌍 Macro · 🔗 Disruption · 🕵️ Insider · 💧 Flow — majority wins. ~{Math.round(aiCycles * 14)}s.
                  </p>
                </button>
              </div>
            </div>

            <div className="mb-4">
              <AiStrategyReference />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Cycle Length</label>
                <select
                  value={period}
                  onChange={(e) => setPeriod(e.target.value)}
                  className="mt-1 w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-pink/60"
                >
                  {PERIODS.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Cycles</label>
                <input
                  type="number"
                  min={3}
                  max={24}
                  value={aiCycles}
                  onChange={(e) => setAiCycles(Math.max(3, Math.min(24, Number(e.target.value) || 8)))}
                  className="mt-1 w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs tabular-nums focus:outline-none focus:border-accent-pink/60"
                />
              </div>
            </div>

            {/* Multi-stock toggle + add-symbol UI */}
            <div className="mb-3 bg-bg-base rounded-md border border-bg-border p-3">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={aiMultiEnabled}
                  onChange={(e) => setAiMultiEnabled(e.target.checked)}
                  className="w-3.5 h-3.5 accent-accent-pink"
                />
                <span className="text-[12px] font-medium text-text-primary">
                  Run on multiple stocks
                </span>
                <span className="text-[10px] text-text-muted">
                  ({symbol} is always the anchor; add up to 7 more)
                </span>
              </label>

              {aiMultiEnabled && (
                <>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const v = aiExtraInput.trim().toUpperCase();
                      if (v && v !== symbol && !aiExtraSymbols.includes(v) && aiExtraSymbols.length < 7) {
                        setAiExtraSymbols([...aiExtraSymbols, v]);
                        setAiExtraInput("");
                      }
                    }}
                    className="flex items-center gap-2 mt-3"
                  >
                    <input
                      value={aiExtraInput}
                      onChange={(e) => setAiExtraInput(e.target.value.toUpperCase())}
                      placeholder="Add ticker (e.g. NVDA)"
                      maxLength={10}
                      disabled={aiExtraSymbols.length >= 7}
                      className="flex-1 bg-bg-card border border-bg-border rounded-md px-3 py-1.5 text-xs font-mono focus:outline-none focus:border-accent-pink/60 disabled:opacity-50"
                    />
                    <button
                      type="submit"
                      disabled={!aiExtraInput.trim() || aiExtraSymbols.length >= 7}
                      className="bg-accent-pink/10 border border-accent-pink/40 hover:bg-accent-pink/20 text-accent-pink px-3 py-1.5 rounded-md text-xs font-medium flex items-center gap-1 transition-colors disabled:opacity-50"
                    >
                      <Plus size={11} /> Add
                    </button>
                  </form>

                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <span className="badge bg-accent-pink/15 text-accent-pink border-accent-pink/50 font-mono">
                      {symbol} <span className="ml-1 text-[9px] uppercase tracking-wider opacity-80">anchor</span>
                    </span>
                    {aiExtraSymbols.map((s) => (
                      <button
                        key={s}
                        onClick={() => setAiExtraSymbols(aiExtraSymbols.filter((x) => x !== s))}
                        className="badge bg-accent-pink/10 text-accent-pink border-accent-pink/40 hover:bg-accent-pink/20 font-mono"
                      >
                        {s} <X size={11} className="ml-1 opacity-60" />
                      </button>
                    ))}
                    <span className="text-[10px] text-text-muted ml-1">
                      {1 + aiExtraSymbols.length}/8
                    </span>
                  </div>
                </>
              )}
            </div>

            <button
              onClick={() => {
                if (aiMultiEnabled) {
                  const syms = [symbol, ...aiExtraSymbols.filter((s) => s !== symbol)];
                  aiMultiMutation.mutate({ syms, per: period, cycles: aiCycles, mode: aiMode });
                } else {
                  aiMutation.mutate({ sym: symbol, per: period, cycles: aiCycles, mode: aiMode });
                }
              }}
              disabled={!symbol || aiMutation.isPending || aiMultiMutation.isPending}
              className={cn(
                "w-full px-4 py-2.5 rounded-md text-sm font-semibold flex items-center justify-center gap-2 transition-all disabled:opacity-50 border",
                aiMode === "multi"
                  ? "bg-accent-violet/10 border-accent-violet/40 hover:bg-accent-violet/20 text-accent-violet"
                  : "bg-accent-pink/10 border-accent-pink/40 hover:bg-accent-pink/20 text-accent-pink",
              )}
            >
              {(aiMutation.isPending || aiMultiMutation.isPending)
                ? <Loader2 size={14} className="animate-spin" />
                : <Bot size={14} />}
              {(() => {
                if (aiMultiMutation.isPending) {
                  const n = 1 + aiExtraSymbols.length;
                  return `Running on ${n} stocks${aiMode === "multi" ? " × 7 agents" : ""}…`;
                }
                if (aiMutation.isPending) {
                  return `Running ${aiCycles} cycles${aiMode === "multi" ? " × 7 agents" : ""}…`;
                }
                if (aiMultiEnabled) {
                  const n = 1 + aiExtraSymbols.length;
                  return `Run ${aiMode === "multi" ? "Multi-Agent" : "Single-Agent"} on ${n} stocks`;
                }
                return `Run ${aiMode === "multi" ? "Multi-Agent" : "Single-Agent"} Backtest`;
              })()}
            </button>
            <p className="text-[10px] text-text-muted mt-2">
              {aiMode === "multi"
                ? `${aiCycles} cycles × 7 personality agents = ${aiCycles * 7} Claude calls (7 personalities fire in parallel per cycle). Every agent sees the same rich context — Market Pulse, Discover-equivalent score, Deep Dive signals, fundamentals, news, real historical insider trades, FINRA short volume — and replies with DECISION + REASON.`
                : `One Claude call per cycle with full context (Market Pulse macro, Discover score, Deep Dive signals, fundamentals, news, trade plan).`}
            </p>

            {/* Upfront expectation-setting before user clicks Run */}
            {aiMode === "multi" && !aiMutation.isPending && !aiMutation.data && (
              <div className="mt-3 p-3 rounded-md bg-accent-amber/5 border border-accent-amber/30 text-[11px] text-text-secondary leading-relaxed">
                <div className="font-semibold text-accent-amber mb-1">
                  Heads up — multi-agent runs are slow.
                </div>
                <p>
                  Expect roughly <span className="font-semibold text-text-primary">~{aiCycles} × 60 = {aiCycles * 60}s</span>
                  {" "}({Math.round(aiCycles * 60 / 60)}m {aiCycles * 60 % 60}s) for {aiCycles} cycles. The 7 personality agents
                  fire concurrently but each Claude subprocess takes ~10-15s and they slow each other down under contention.
                </p>
                <p className="mt-1">
                  The result caches for 6h on (<span className="font-mono">{symbol}</span>, {period}, {aiCycles}, multi) so a
                  rerun returns instantly. For exploratory runs, start with{" "}
                  <span className="font-semibold text-text-primary">cycles = 4</span> or use single-agent mode.
                </p>
              </div>
            )}

            <AiProgressEstimator
              active={aiMutation.isPending}
              cycles={aiCycles}
              mode={aiMode}
            />
          </div>

          {aiMutation.data?.error && (
            <div className="card p-4 border-l-4 border-accent-red/40 mb-4">
              <p className="text-accent-redSoft text-sm">{aiMutation.data.error}</p>
            </div>
          )}

          {aiMutation.isError && (
            <div className="card p-4 border-l-4 border-accent-red/40 mb-4">
              <p className="text-accent-redSoft text-sm font-medium">AI backtest request failed.</p>
              <p className="text-text-muted text-xs mt-1">
                {(aiMutation.error as Error)?.message || "Unknown error"}
              </p>
              <p className="text-text-muted text-[11px] mt-2 leading-relaxed">
                Multi-agent runs can take 2-4 minutes (7 personality agents × {aiCycles} cycles).
                If the connection dropped, the work may still be completing server-side — try clicking{" "}
                <span className="font-semibold">Run</span> again with the same settings; the cached result
                should appear quickly. If it keeps failing, drop cycles to 4-5 or switch to single-agent.
              </p>
            </div>
          )}

          {aiMultiMutation.isError && (
            <div className="card p-4 border-l-4 border-accent-red/40 mb-4">
              <p className="text-accent-redSoft text-sm font-medium">Multi-stock AI backtest request failed.</p>
              <p className="text-text-muted text-xs mt-1">
                {(aiMultiMutation.error as Error)?.message || "Unknown error"}
              </p>
              <p className="text-text-muted text-[11px] mt-2 leading-relaxed">
                Each stock runs sequentially. With {1 + aiExtraSymbols.length} stocks × {aiCycles} cycles{aiMode === "multi" ? " × 7 agents" : ""} this can take a while. Each stock's result caches independently for 6h — try Run again on the same list to pull cached rows.
              </p>
            </div>
          )}

          {aiMultiMutation.data?.error && (
            <div className="card p-4 border-l-4 border-accent-red/40 mb-4">
              <p className="text-accent-redSoft text-sm">{aiMultiMutation.data.error}</p>
            </div>
          )}

          {aiMultiEnabled && aiMultiMutation.data && !aiMultiMutation.data.error && (aiMultiMutation.data.rows?.length ?? 0) > 0 && (
            <AiMultiStockTable
              rows={aiMultiMutation.data.rows}
              mode={(aiMultiMutation.data.mode as "single" | "multi") || "single"}
            />
          )}

          {aiMutation.data && !aiMutation.data.error && !aiMultiEnabled && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="card p-4 text-center">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Cycles</div>
                  <div className="text-xl font-bold tabular-nums mt-1">{aiMutation.data.cycles_run}</div>
                </div>
                <div className="card p-4 text-center">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Trades</div>
                  <div className="text-xl font-bold tabular-nums mt-1">{aiMutation.data.total_trades}</div>
                </div>
                <div className="card p-4 text-center">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Win Rate</div>
                  <div className={cn(
                    "text-xl font-bold tabular-nums mt-1",
                    aiMutation.data.win_rate >= 0.65 ? "text-accent-greenSoft"
                      : aiMutation.data.win_rate < 0.45 ? "text-accent-redSoft"
                      : "text-accent-amber"
                  )}>
                    {(aiMutation.data.win_rate * 100).toFixed(0)}%
                  </div>
                </div>
                <div className="card p-4 text-center">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Avg Return</div>
                  <div className={cn(
                    "text-xl font-bold tabular-nums mt-1",
                    aiMutation.data.avg_return >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft"
                  )}>
                    {formatPercent(aiMutation.data.avg_return)}
                  </div>
                </div>
              </div>

              <div className="card p-5">
                <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                  <h3 className="text-sm font-semibold tracking-tight">Decision Log</h3>
                  <span className="text-[10px] uppercase tracking-wider text-text-muted">
                    Click <span className="text-accent-pink font-semibold">Prompt</span> on any row to see what Claude saw
                  </span>
                </div>
                <div className="space-y-1.5">
                  {aiMutation.data.decisions.map((d, i) => (
                    <AiDecisionRow key={i} d={d} idx={i} />
                  ))}
                </div>
              </div>
            </div>
          )}

          {!aiMutation.data && !aiMutation.isPending && (
            <div className="card p-10 text-center text-text-muted text-sm">
              Click <span className="text-accent-pink font-medium">Run AI Backtest</span> to walk forward through cycles.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
