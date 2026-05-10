"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Layers, ArrowLeft, Plus, Search, Play } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Sparkline } from "@/components/discover/sparkline";
import { Skeleton } from "@/components/ui/skeleton";
import { PeriodChips } from "@/components/ui/period-chips";
import { SelectedSymbolChips, WatchlistQuickAdd } from "@/components/ui/symbol-chips";
import { compareApi, watchlistApi } from "@/lib/api/endpoints";
import type { CompareRow } from "@/lib/api/types";
import { cn, formatCurrency, formatPercent } from "@/lib/utils";

function verdictTone(v?: string | null) {
  const s = (v || "").toLowerCase();
  if (s.includes("strong buy")) return "bg-accent-green/10 text-accent-greenSoft border-accent-green/40";
  if (s.includes("buy")) return "bg-accent-green/10 text-accent-greenSoft border-accent-green/30";
  if (s.includes("strong sell")) return "bg-accent-red/10 text-accent-redSoft border-accent-red/40";
  if (s.includes("sell")) return "bg-accent-red/10 text-accent-redSoft border-accent-red/30";
  return "bg-accent-amber/10 text-accent-amber border-accent-amber/30";
}

function CompareCard({ row }: { row: CompareRow }) {
  if (row.error) {
    return (
      <div className="card p-5 border-l-4 border-accent-red/40">
        <div className="font-mono font-bold text-lg">{row.symbol}</div>
        <p className="text-accent-redSoft text-xs mt-1">{row.error}</p>
      </div>
    );
  }

  const change = row.change_pct ?? 0;
  const positive = change > 0;

  return (
    <div className="card p-5 flex flex-col gap-3 min-w-0">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Link
            href={`/deep-dive/${row.symbol}`}
            className="font-mono font-bold text-lg hover:text-accent-violet transition-colors"
          >
            {row.symbol}
          </Link>
          {row.name && (
            <p className="text-text-muted text-xs truncate">{row.name}</p>
          )}
        </div>
        <span className={cn("badge text-[10px]", verdictTone(row.verdict))}>
          {row.verdict || "—"}
        </span>
      </div>

      {row.spark && row.spark.length > 1 && (
        <div className="-mx-2"><Sparkline points={row.spark} height={50} /></div>
      )}

      <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Price</div>
          <div className="font-semibold tabular-nums">
            {row.price != null ? formatCurrency(row.price, 2) : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Change</div>
          <div className={cn(
            "font-semibold tabular-nums",
            positive ? "text-accent-greenSoft" : change < 0 ? "text-accent-redSoft" : "text-text-secondary"
          )}>
            {row.change_pct != null ? formatPercent(change) : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Risk</div>
          <div className={cn(
            "font-semibold",
            (row.risk_rating ?? 3) <= 2 ? "text-accent-greenSoft"
              : (row.risk_rating ?? 3) >= 4 ? "text-accent-redSoft"
              : "text-accent-amber"
          )}>
            {row.risk_rating != null ? `${row.risk_rating}/5` : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Sentiment</div>
          <div className={cn(
            "font-semibold tabular-nums",
            (row.sentiment_score ?? 0) > 0.1 ? "text-accent-greenSoft"
              : (row.sentiment_score ?? 0) < -0.1 ? "text-accent-redSoft"
              : "text-text-secondary"
          )}>
            {row.sentiment_score != null
              ? `${row.sentiment_score > 0 ? "+" : ""}${row.sentiment_score.toFixed(2)}`
              : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">P/E</div>
          <div className="font-semibold tabular-nums">
            {row.pe_ratio != null ? row.pe_ratio.toFixed(1) : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Div Yield</div>
          <div className="font-semibold tabular-nums">
            {row.dividend_yield != null ? `${(row.dividend_yield * 100).toFixed(2)}%` : "—"}
          </div>
        </div>
      </div>

      <div className="pt-2 border-t border-bg-border">
        <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-text-muted mb-1">
          <span>Signal Tally</span>
          <span>{row.total_signals} total</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-accent-greenSoft font-semibold">↑ {row.bullish_signals} bull</span>
          <span className="text-accent-redSoft font-semibold">↓ {row.bearish_signals} bear</span>
        </div>
      </div>
    </div>
  );
}

export default function ComparePage() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [period, setPeriod] = useState("3M");
  const [submitted, setSubmitted] = useState<string[]>([]);

  const { data: watchlist = [] } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.list(),
    staleTime: 30 * 1000,
  });

  const mutation = useMutation({
    mutationFn: (vars: { syms: string[]; per: string }) => compareApi.run(vars.syms, vars.per),
  });

  const addSymbol = (s: string) => {
    const v = s.trim().toUpperCase();
    if (!v) return;
    if (symbols.includes(v)) return;
    if (symbols.length >= 6) return;
    setSymbols([...symbols, v]);
    setInput("");
  };

  const removeSymbol = (s: string) => setSymbols(symbols.filter((x) => x !== s));

  const run = () => {
    if (symbols.length === 0) return;
    setSubmitted(symbols);
    mutation.mutate({ syms: symbols, per: period });
  };

  const data = mutation.data;

  return (
    <div>
      <PageHeader
        icon={Layers}
        title="Compare Stocks"
        subtitle="Run analysis on up to 6 tickers side by side."
        accent="text-accent-violet"
        iconBg="bg-accent-violet/10"
      />

      <div className="mb-4">
        <Link
          href="/deep-dive"
          className="text-sm text-text-secondary hover:text-text-primary inline-flex items-center gap-1.5"
        >
          <ArrowLeft size={14} /> Back
        </Link>
      </div>

      <div className="card p-5 mb-6">
        <h3 className="text-sm font-semibold mb-3">Select Tickers</h3>

        {/* Add input */}
        <form
          onSubmit={(e) => { e.preventDefault(); addSymbol(input); }}
          className="flex items-center gap-2 mb-3"
        >
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value.toUpperCase())}
              placeholder="Add ticker (e.g. NVDA)"
              maxLength={10}
              disabled={symbols.length >= 6}
              className="w-full bg-bg-base border border-bg-border rounded-md pl-9 pr-3 py-2 text-sm font-mono focus:outline-none focus:border-accent-violet/60 disabled:opacity-50"
            />
          </div>
          <button
            type="submit"
            disabled={!input.trim() || symbols.length >= 6}
            className="bg-accent-violet/10 border border-accent-violet/40 hover:bg-accent-violet/20 text-accent-violet px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <Plus size={14} /> Add
          </button>
        </form>

        <div className="mb-3">
          <WatchlistQuickAdd
            watchlist={watchlist}
            selected={symbols}
            onAdd={addSymbol}
            max={6}
            tone="violet"
          />
        </div>

        <div className="mb-3">
          <SelectedSymbolChips
            symbols={symbols}
            onRemove={removeSymbol}
            tone="violet"
            label="Selected"
            max={6}
          />
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs uppercase tracking-wider text-text-muted">Period</span>
          <PeriodChips value={period} onChange={setPeriod} accent="blue" />
          <button
            onClick={run}
            disabled={symbols.length === 0 || mutation.isPending}
            className="ml-auto bg-accent-violet/10 border border-accent-violet/40 hover:bg-accent-violet/20 text-accent-violet px-4 py-2 rounded-md text-sm font-medium flex items-center gap-2 transition-colors disabled:opacity-50"
          >
            <Play size={14} />
            {mutation.isPending ? "Running…" : `Run (${symbols.length})`}
          </button>
        </div>
      </div>

      {mutation.isError && (
        <div className="card p-4 border-l-4 border-accent-red/40 mb-4">
          <p className="text-accent-redSoft text-sm">{(mutation.error as Error).message}</p>
        </div>
      )}

      {mutation.isPending && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {submitted.map((s) => <Skeleton key={s} className="h-72" />)}
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {data.rows.map((r) => <CompareCard key={r.symbol} row={r} />)}
        </div>
      )}

      {data?.rows.length === 0 && (
        <div className="card p-10 text-center text-text-muted text-sm">
          No data returned.
        </div>
      )}
    </div>
  );
}
