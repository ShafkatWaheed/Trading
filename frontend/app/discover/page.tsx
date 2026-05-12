"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Compass, Layers } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { RichOpportunityCard } from "@/components/discover/rich-card";
import { ScoreExplainer } from "@/components/discover/score-explainer";
import { WatchlistManager } from "@/components/discover/watchlist-manager";
import { Skeleton } from "@/components/ui/skeleton";
import { SimulationReplay } from "@/components/simulation-replay";
import { PeriodChips } from "@/components/ui/period-chips";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import {
  DiscoverFilterBar, applyFilters, EMPTY_FILTERS, type DiscoverFilters,
} from "@/components/discover/filter-bar";
import { SortSelector, applySort, type SortKey } from "@/components/discover/sort-selector";
import { SelectionToolbar } from "@/components/discover/selection-toolbar";
import { WhatChanged } from "@/components/discover/what-changed";
import { SavedPresets, type Preset } from "@/components/discover/saved-presets";
import { RegimeToggle, regimeAdjustedScore, useMarketTone } from "@/components/discover/regime-toggle";
import { useDiscover } from "@/lib/hooks/use-discover";
import { cn, formatRelativeTime } from "@/lib/utils";

const MIN_SCORE_PRESETS = [
  { label: "All",      value: 0 },
  { label: "Fair+",    value: 40 },
  { label: "Good+",    value: 60 },
  { label: "Strong+",  value: 75 },
];

const SCOPE_OPTS = [
  { key: "watchlist" as const, label: "Watchlist" },
  { key: "all" as const,       label: "All Stocks" },
];

export default function DiscoverPage() {
  const [period, setPeriod] = useState("1M");
  const [minScore, setMinScore] = useState(0);
  const [scope, setScope] = useState<"watchlist" | "all">("watchlist");
  const [filters, setFilters] = useState<DiscoverFilters>(EMPTY_FILTERS);
  const [sort, setSort] = useState<SortKey>("score");
  const [regimeAdjusted, setRegimeAdjusted] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);

  // Note: useDiscover currently only accepts min_score / limit / sector.
  // period + scope filtering is applied client-side via the filter bar.
  const { data, isLoading } = useDiscover({
    min_score: minScore,
    limit: 30,
  });

  const rawOps = data?.opportunities || [];
  const tone = useMarketTone();

  // Apply client-side filters → optional regime re-score → sort
  const processed = useMemo(() => {
    let arr = applyFilters(rawOps, filters);
    if (regimeAdjusted) {
      arr = arr
        .map((op) => ({ ...op, score: regimeAdjustedScore(op, tone) }))
        // Re-sort by adjusted score if sorting by score; otherwise leave for sort step
        ;
    }
    arr = applySort(arr, sort);
    return arr;
  }, [rawOps, filters, sort, regimeAdjusted, tone]);

  const toggleSelect = (sym: string) => {
    setSelected((prev) =>
      prev.includes(sym)
        ? prev.filter((s) => s !== sym)
        : prev.length >= 4
          ? prev               // cap at 4
          : [...prev, sym]
    );
  };

  const loadPreset = (p: Preset) => {
    setPeriod(p.period);
    setMinScore(p.min_score);
    setScope(p.scope);
    setFilters(p.filters);
    setSort(p.sort);
    setRegimeAdjusted(p.regime_adjusted);
  };

  return (
    <div>
      <PageHeader
        icon={Compass}
        title="Discover"
        subtitle="Rank, filter, and screen stocks worth trading. Click any card to deep-dive."
        accent="text-accent-amber"
        iconBg="bg-accent-amber/10"
      />

      <div className="space-y-6">
        <SimulationReplay step="discover" accent="amber" />

        <WatchlistManager />

        <details className="card p-3">
          <summary className="text-xs text-text-muted hover:text-text-secondary cursor-pointer select-none">
            How is the score computed? (click to learn)
          </summary>
          <div className="mt-3">
            <ScoreExplainer />
          </div>
        </details>

        {/* What changed since last visit */}
        <WhatChanged ops={rawOps} />

        {/* Filter bar — sectors + setup quality toggles */}
        <DiscoverFilterBar ops={rawOps} filters={filters} onChange={setFilters} />

        {/* Top row — scope + period + min score + sort + regime + presets */}
        <div className="card p-4 flex flex-wrap items-center gap-x-5 gap-y-3">
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Scope</span>
            <SegmentedControl
              options={SCOPE_OPTS.map(o => ({ value: o.key, label: o.label }))}
              value={scope}
              onChange={setScope}
              accent="amber"
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Period</span>
            <PeriodChips value={period} onChange={setPeriod} accent="blue" size="sm" />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Min Score</span>
            <SegmentedControl
              options={MIN_SCORE_PRESETS.map(p => ({ value: p.value, label: p.label }))}
              value={minScore}
              onChange={setMinScore}
              accent="green"
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Sort</span>
            <SortSelector value={sort} onChange={setSort} />
          </div>

          <div className="ml-auto">
            <RegimeToggle enabled={regimeAdjusted} onToggle={setRegimeAdjusted} />
          </div>
        </div>

        <SavedPresets
          current={{
            period, min_score: minScore, scope, filters, sort, regime_adjusted: regimeAdjusted,
          }}
          onLoad={loadPreset}
        />

        <SelectionToolbar
          selected={selected}
          onClear={() => setSelected([])}
          onRemove={(s) => setSelected((prev) => prev.filter((x) => x !== s))}
        />

        {isLoading ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-96" />
            ))}
          </div>
        ) : processed.length === 0 ? (
          <EmptyState
            icon={Compass}
            title="No opportunities match this filter"
            description={
              filters.sectors.length > 0 || filters.volume_conf || filters.smart_money ||
              filters.trend_pullback || filters.rel_strength || filters.earnings_14d
                ? "Try clearing some filters, or switch to All Stocks."
                : scope === "watchlist"
                  ? "Try lowering the score, switching to All Stocks, or adding tickers to your watchlist."
                  : "Try a lower score threshold, or wait for the scheduler to refresh scores."
            }
            tone="amber"
          />
        ) : (
          <>
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="text-[11px] uppercase tracking-wider text-text-muted font-semibold">
                {processed.length} stock{processed.length === 1 ? "" : "s"}
                {rawOps.length !== processed.length && (
                  <span className="text-text-dim normal-case"> (filtered from {rawOps.length})</span>
                )}
                <span className="text-text-dim normal-case"> · sorted by {sort}</span>
              </div>
              {processed.length > 1 && (
                <Link href={`/deep-dive/${processed[0].symbol}`}>
                  <Button tone="violet" variant="solid" size="sm" leftIcon={<Layers size={12} />}>
                    Deep Dive Top Pick · {processed[0].symbol}
                  </Button>
                </Link>
              )}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {processed.map((op, rank) => (
                <RichOpportunityCard
                  key={op.symbol}
                  op={op}
                  rank={rank}
                  selected={selected.includes(op.symbol)}
                  onToggleSelect={toggleSelect}
                  adjustedScore={regimeAdjusted ? op.score : null}
                />
              ))}
            </div>
          </>
        )}

        {data && (
          <p className="text-[11px] text-text-muted text-right">
            Last updated {formatRelativeTime(data.last_updated)}
          </p>
        )}
      </div>
    </div>
  );
}

/** Reusable pill-group control with active accent */
function SegmentedControl<T extends string | number>({
  options,
  value,
  onChange,
  accent = "amber",
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  accent?: "amber" | "blue" | "green" | "violet" | "cyan";
}) {
  const ACCENT: Record<string, string> = {
    amber: "text-accent-amber bg-accent-amber/15 border-accent-amber/40",
    blue: "text-accent-blue bg-accent-blue/15 border-accent-blue/40",
    green: "text-accent-greenSoft bg-accent-green/15 border-accent-green/40",
    violet: "text-accent-violet bg-accent-violet/15 border-accent-violet/40",
    cyan: "text-accent-cyan bg-accent-cyan/15 border-accent-cyan/40",
  };
  return (
    <div className="inline-flex items-center gap-0.5 p-0.5 bg-bg-base border border-bg-border rounded-md">
      {options.map((o) => (
        <button
          key={String(o.value)}
          onClick={() => onChange(o.value)}
          className={cn(
            "h-7 px-2.5 rounded-[4px] text-[11px] font-semibold transition-all duration-150",
            value === o.value
              ? cn(ACCENT[accent], "border")
              : "text-text-muted hover:text-text-primary border border-transparent hover:bg-bg-card",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
