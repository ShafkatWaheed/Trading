"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft, Search, RefreshCw, Database, Zap } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { TickerSearchInput } from "@/components/ui/ticker-search-input";
import { stocksApi } from "@/lib/api/endpoints";
import { VerdictBanner } from "@/components/deep-dive/verdict-banner";
import { KpiGridDeepDive } from "@/components/deep-dive/kpi-grid";
import { SignalGroups } from "@/components/deep-dive/signal-groups";
import { TradePlanRich } from "@/components/deep-dive/trade-plan-rich";
import { PriceChart } from "@/components/deep-dive/price-chart";
import { VolumeProfileChart } from "@/components/deep-dive/volume-profile";
import { EarningsTable } from "@/components/deep-dive/earnings-table";
import { RiskNarrative } from "@/components/deep-dive/risk-narrative";
import { BullNarrative } from "@/components/deep-dive/bull-narrative";
import { BubbleScoreCard } from "@/components/deep-dive/bubble-score";
import { EarningsExplainer } from "@/components/deep-dive/earnings-explainer";
import { TldrBanner } from "@/components/deep-dive/tldr-banner";
import { AnalystConsensus } from "@/components/deep-dive/analyst-consensus";
import { PeerValuationStrip } from "@/components/deep-dive/peer-valuation-strip";
import { SmartMoneyCard } from "@/components/deep-dive/smart-money";
import { NewsFeed } from "@/components/deep-dive/news-feed";
import { CatalystCalendar } from "@/components/deep-dive/catalyst-calendar";
import { RecommendationCard } from "@/components/deep-dive/recommendation-card";
import { InnovationCard } from "@/components/deep-dive/innovation-card";
import { FdaCatalystsCard } from "@/components/deep-dive/fda-catalysts-card";
import { BacklogCard } from "@/components/deep-dive/backlog-card";
import { EntityMatchDebugCard } from "@/components/deep-dive/entity-match-debug-card";
import { StickyVerdictBar } from "@/components/deep-dive/sticky-verdict-bar";
import { PositionSizing } from "@/components/deep-dive/position-sizing";
import { SectionHeader } from "@/components/deep-dive/section-header";
import { SimulationReplay } from "@/components/simulation-replay";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeepDive } from "@/lib/hooks/use-deep-dive";
import { cn, formatRelativeTime } from "@/lib/utils";

const PERIODS = ["1D", "1W", "1M", "3M", "6M", "1Y"];
const FILTERS = [
  { key: "all", label: "All Signals" },
  { key: "buy", label: "Buy Only" },
  { key: "sell", label: "Sell Only" },
  { key: "strong", label: "Strong Only" },
];

export default function DeepDiveTickerPage() {
  const params = useParams<{ ticker: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const ticker = decodeURIComponent(params.ticker || "").toUpperCase();

  const [period, setPeriod] = useState("3M");
  const [signalFilter, setSignalFilter] = useState("all");
  const [accountSize, setAccountSize] = useState(10000);
  const [riskPct, setRiskPct] = useState(2);
  const [forceRefreshing, setForceRefreshing] = useState(false);

  const queryOpts = {
    period, signal_filter: signalFilter,
    account_size: accountSize, risk_pct: riskPct,
  };
  const { data, isLoading, error, refetch, isFetching } = useDeepDive(ticker, queryOpts);

  const handleForceRefresh = async () => {
    setForceRefreshing(true);
    try {
      const fresh = await stocksApi.deepDive(ticker, { ...queryOpts, force: true });
      qc.setQueryData(["deepDive", ticker, queryOpts], fresh);
    } finally {
      setForceRefreshing(false);
    }
  };

  return (
    <div>
      <PageHeader
        icon={Search}
        title={`Deep Dive · ${ticker}`}
        subtitle="Full analysis with trade plan, signal breakdown, and timing notes."
        accent="text-accent-violet"
        iconBg="bg-accent-violet/10"
      />

      <div className="mb-4 flex items-center gap-3 flex-wrap">
        <Link
          href="/deep-dive"
          className="text-sm text-text-secondary hover:text-text-primary inline-flex items-center gap-1.5 shrink-0"
        >
          <ArrowLeft size={14} /> Back
        </Link>
        <div className="flex-1 min-w-[200px] max-w-md">
          <TickerSearchInput
            onPick={(sym) => router.push(`/deep-dive/${encodeURIComponent(sym)}`)}
            placeholder={`Switch ticker (currently ${ticker})`}
            tone="violet"
            compact
          />
        </div>
        {data && (
          <div className="flex items-center gap-1.5 text-[11px] text-text-muted shrink-0">
            {data.from_cache ? (
              <>
                <Database size={11} />
                <span>Cached {data.cached_at ? formatRelativeTime(data.cached_at) : ""}</span>
              </>
            ) : (
              <>
                <Zap size={11} className="text-accent-greenSoft" />
                <span className="text-accent-greenSoft">Live</span>
              </>
            )}
          </div>
        )}

        <button
          onClick={handleForceRefresh}
          disabled={isFetching || forceRefreshing}
          className="text-xs text-text-secondary hover:text-text-primary inline-flex items-center gap-1.5 px-2 py-1 rounded transition-colors shrink-0 disabled:opacity-50"
          title="Bypass cache and re-fetch"
        >
          <RefreshCw size={12} className={(isFetching || forceRefreshing) ? "animate-spin" : ""} />
          {forceRefreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {/* Filters */}
      <div className="card p-4 mb-6 flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-wider text-text-muted">Timeframe</span>
          <div className="flex gap-1">
            {PERIODS.map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={cn(
                  "px-2.5 py-1 rounded-md text-xs font-mono font-medium transition-colors border",
                  period === p
                    ? "bg-accent-violet/10 text-accent-violet border-accent-violet/40"
                    : "bg-bg-base text-text-secondary border-bg-border hover:text-text-primary"
                )}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-wider text-text-muted">Filter</span>
          <div className="flex gap-1">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setSignalFilter(f.key)}
                className={cn(
                  "px-2.5 py-1 rounded-md text-xs font-medium transition-colors border",
                  signalFilter === f.key
                    ? "bg-accent-blue/10 text-accent-blue border-accent-blue/40"
                    : "bg-bg-base text-text-secondary border-bg-border hover:text-text-primary"
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2 ml-auto">
          <span className="text-xs uppercase tracking-wider text-text-muted">Account</span>
          <input
            type="number"
            min={100}
            value={accountSize}
            onChange={(e) => setAccountSize(Math.max(100, Number(e.target.value) || 10000))}
            className="w-24 bg-bg-base border border-bg-border rounded-md px-2 py-1 text-xs tabular-nums focus:outline-none focus:border-accent-violet/60"
          />
          <span className="text-xs text-text-muted">·</span>
          <span className="text-xs uppercase tracking-wider text-text-muted">Risk %</span>
          <input
            type="number"
            min={0.1}
            max={10}
            step={0.5}
            value={riskPct}
            onChange={(e) => setRiskPct(Math.max(0.1, Math.min(10, Number(e.target.value) || 2)))}
            className="w-16 bg-bg-base border border-bg-border rounded-md px-2 py-1 text-xs tabular-nums focus:outline-none focus:border-accent-violet/60"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-32" />
          <Skeleton className="h-24" />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Skeleton className="h-64" />
            <Skeleton className="h-64" />
          </div>
        </div>
      ) : error ? (
        <div className="card p-6 border-l-4 border-accent-red/40">
          <p className="text-accent-redSoft font-medium">Analysis failed.</p>
          <p className="text-text-muted text-sm mt-1">{(error as Error).message}</p>
          <p className="text-xs text-text-muted mt-3">
            Try again — many failures are upstream rate-limit hiccups that resolve quickly.
          </p>
        </div>
      ) : data ? (
        <div className="space-y-6">
          {/* Sticky condensed bar — slides in once user scrolls past hero */}
          <StickyVerdictBar data={data} />

          <SimulationReplay step="deep_dive" accent="violet" />

          {/* ── 01 · SNAPSHOT ──────────────────────────────────────────── */}
          <SectionHeader index={1} label="Snapshot" subtitle="who is this stock · 5-second read" id="snapshot" />

          <VerdictBanner
            symbol={data.symbol}
            name={data.name}
            sector={data.sector}
            verdict={data.verdict}
            confidence={data.confidence}
            riskRating={data.risk_rating}
          />

          <KpiGridDeepDive data={data} />

          <TldrBanner symbol={data.symbol} />

          {/* ── 02 · ACTION ────────────────────────────────────────────── */}
          <SectionHeader index={2} label="Action" subtitle="recommended next move · chart · summary" id="action" />

          <RecommendationCard symbol={data.symbol} />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2">
              {data.period_change && (
                <PriceChart
                  data={data.period_change}
                  symbol={data.symbol}
                  tradePlan={data.trade_plan}
                />
              )}
            </div>
            <div>
              {data.volume_profile && <VolumeProfileChart data={data.volume_profile} />}
            </div>
          </div>

          {data.summary && (
            <div className="card-subtle p-6">
              <h3 className="text-base font-semibold mb-2">Summary</h3>
              <p className="text-text-secondary text-sm leading-relaxed whitespace-pre-line">
                {data.summary}
              </p>
            </div>
          )}

          {/* ── 03 · WHAT'S HAPPENING ──────────────────────────────────── */}
          <SectionHeader index={3} label="What's happening" subtitle="news + upcoming catalysts" id="news" />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <NewsFeed symbol={data.symbol} />
            <CatalystCalendar symbol={data.symbol} />
          </div>

          {/* ── 04 · WHAT PROS ARE DOING ───────────────────────────────── */}
          <SectionHeader index={4} label="What pros are doing" subtitle="smart money + Wall Street consensus" id="pros" />

          <SmartMoneyCard symbol={data.symbol} />
          <AnalystConsensus symbol={data.symbol} />

          {/* ── 05 · IS THE PRICE RIGHT ────────────────────────────────── */}
          <SectionHeader index={5} label="Is the price right" subtitle="bubble score · vibes premium · peers" id="valuation" />

          <BubbleScoreCard symbol={data.symbol} />
          <PeerValuationStrip symbol={data.symbol} />
          <InnovationCard ticker={data.symbol} />
          <FdaCatalystsCard ticker={data.symbol} />
          <BacklogCard ticker={data.symbol} />

          {/* ── 06 · BULL vs BEAR ──────────────────────────────────────── */}
          <SectionHeader index={6} label="Bull vs Bear" subtitle="symmetric thesis · invalidation conditions" id="thesis" />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <BullNarrative symbol={data.symbol} />
            <RiskNarrative symbol={data.symbol} />
          </div>

          {/* ── 07 · HOW TO EXECUTE ────────────────────────────────────── */}
          <SectionHeader index={7} label="How to execute" subtitle="trade plan · sizing · signals" id="setup" />

          {data.trade_plan && <TradePlanRich plan={data.trade_plan} />}
          {data.trade_plan && <PositionSizing plan={data.trade_plan} />}

          <div className="card-subtle p-4 flex items-center gap-4 flex-wrap text-xs">
            <span className="text-text-muted uppercase tracking-wider">Signal Tally</span>
            <span className="text-accent-greenSoft font-semibold">
              ↑ {data.signal_counts.bullish} bullish
            </span>
            <span className="text-accent-redSoft font-semibold">
              ↓ {data.signal_counts.bearish} bearish
            </span>
            <span className="text-text-muted">{data.signal_counts.neutral} neutral</span>
            <span className="ml-auto text-text-muted">
              {data.signal_counts.total} signal{data.signal_counts.total === 1 ? "" : "s"} after filter
            </span>
          </div>

          <SignalGroups groups={data.signal_groups} symbol={data.symbol} />

          {/* ── 08 · REFERENCE ─────────────────────────────────────────── */}
          <SectionHeader index={8} label="Reference" subtitle="earnings history · transcript explainer" id="reference" />

          {data.earnings.length > 0 && <EarningsTable rows={data.earnings} />}
          <EarningsExplainer symbol={data.symbol} />

          <EntityMatchDebugCard ticker={data.symbol} />

          <p className="text-xs text-text-muted text-right pt-2">
            Analyzed {formatRelativeTime(data.last_updated)}
          </p>
        </div>
      ) : null}
    </div>
  );
}
