"use client";

import Link from "next/link";
import { useState } from "react";
import { Compass, Filter, Layers } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { RichOpportunityCard } from "@/components/discover/rich-card";
import { ScoreExplainer } from "@/components/discover/score-explainer";
import { WatchlistManager } from "@/components/discover/watchlist-manager";
import { Skeleton } from "@/components/ui/skeleton";
import { SimulationReplay } from "@/components/simulation-replay";
import { SectionHeading } from "@/components/ui/card";
import { PeriodChips } from "@/components/ui/period-chips";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
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

  const { data, isLoading } = useDiscover({
    min_score: minScore,
    limit: 30,
    period,
    only_watchlist: scope === "watchlist",
  });

  const ops = data?.opportunities || [];

  return (
    <div>
      <PageHeader
        icon={Compass}
        title="Discover"
        subtitle="Rank and screen stocks worth trading. Click any card to deep-dive."
        accent="text-accent-amber"
        iconBg="bg-accent-amber/10"
      />

      <div className="space-y-6">
        <SimulationReplay step="discover" accent="amber" />

        <WatchlistManager />

        <ScoreExplainer />

        {/* Filter bar */}
        <div className="card p-4 flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="flex items-center gap-2">
            <Filter size={13} className="text-text-muted" strokeWidth={2.4} />
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
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-96" />
            ))}
          </div>
        ) : ops.length === 0 ? (
          <EmptyState
            icon={Compass}
            title="No opportunities match this filter"
            description={
              scope === "watchlist"
                ? "Try lowering the score, switching to All Stocks, or adding tickers to your watchlist."
                : "Try a lower score threshold, or wait for the scheduler to refresh scores."
            }
            tone="amber"
          />
        ) : (
          <>
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="text-[11px] uppercase tracking-wider text-text-muted font-semibold">
                {ops.length} stock{ops.length === 1 ? "" : "s"} ranked over {period}
              </div>
              {ops.length > 1 && (
                <Link href={`/deep-dive/${ops[0].symbol}`}>
                  <Button tone="violet" variant="solid" size="sm" leftIcon={<Layers size={12} />}>
                    Deep Dive Top Pick · {ops[0].symbol}
                  </Button>
                </Link>
              )}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {ops.map((op, rank) => (
                <RichOpportunityCard key={op.symbol} op={op} rank={rank} />
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
