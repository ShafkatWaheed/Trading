"use client";

import { useQuery } from "@tanstack/react-query";
import { Layers } from "lucide-react";
import { trackRecordApi } from "@/lib/api/endpoints";
import type { TrackRecordSource } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { RefreshButton } from "@/components/ui/refresh-button";
import { cn } from "@/lib/utils";

type Props = { days: number };

const LABELS: Record<TrackRecordSource, { label: string; blurb: string; color: string }> = {
  recommendation: {
    label: "Recommendation",
    blurb: "Risk-adjusted BUY / SELL / HOLD action",
    color: "bg-accent-blue",
  },
  ai_analyst: {
    label: "AI Analyst",
    blurb: "Walk-forward cycle decisions from Claude",
    color: "bg-accent-violet",
  },
  bubble_score: {
    label: "Bubble Score",
    blurb: "Valuation vs. fundamentals",
    color: "bg-accent-amber",
  },
};

function pctTone(p: number): string {
  if (p >= 60) return "text-accent-greenSoft";
  if (p >= 50) return "text-accent-amber";
  return "text-accent-redSoft";
}

export function FeatureComparison({ days }: Props) {
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["track-record-summary", days],
    queryFn: () => trackRecordApi.summary({ days }),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <section className="card-subtle p-5">
        <Skeleton className="h-40" />
      </section>
    );
  }
  if (!data) return null;

  // Always render all three known sources, falling back to zero rows for ones with no data.
  const knownSources: TrackRecordSource[] = ["recommendation", "ai_analyst", "bubble_score"];
  const bySource = new Map(data.by_source.map((s) => [s.source, s] as const));
  const rows = knownSources.map((s) => {
    const r = bySource.get(s);
    return r ?? { source: s, total: 0, correct: 0, accuracy_pct: 0, avg_return_pct: 0 };
  });

  return (
    <section className="card-subtle p-5">
      <div className="flex items-center gap-2 mb-4">
        <Layers size={14} className="text-accent-blue" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
          By feature
        </h3>
        <span className="text-[11px] text-text-muted ml-auto">comparing accuracy across AI verdict sources</span>
        <RefreshButton onClick={() => refetch()} isFetching={isFetching} title="Refresh" />
      </div>

      <div className="space-y-3">
        {rows.map((r) => {
          const meta = LABELS[r.source];
          const width = r.total ? Math.max(2, Math.min(100, r.accuracy_pct)) : 0;
          return (
            <div key={r.source}>
              <div className="flex items-baseline justify-between gap-3 mb-1">
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-text-primary">{meta.label}</div>
                  <div className="text-[10px] text-text-muted leading-snug">{meta.blurb}</div>
                </div>
                <div className="text-right tabular-nums">
                  <div className={cn("text-lg font-bold", r.total ? pctTone(r.accuracy_pct) : "text-text-muted")}>
                    {r.total ? `${r.accuracy_pct.toFixed(1)}%` : "—"}
                  </div>
                  <div className="text-[10px] text-text-muted">
                    {r.total ? `${r.correct}/${r.total} · ${r.avg_return_pct >= 0 ? "+" : ""}${r.avg_return_pct.toFixed(1)}% avg` : "no data yet"}
                  </div>
                </div>
              </div>
              <div className="h-2 bg-bg-card2 rounded-full overflow-hidden">
                <div
                  className={cn("h-full transition-all", meta.color)}
                  style={{ width: `${width}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-[11px] text-text-muted mt-4 leading-relaxed">
        Accuracy thresholds: <strong>Recommendation</strong> ≥+2% for BUY, ≤-2% for SELL, ±2% for HOLD ·{" "}
        <strong>AI Analyst</strong> ±1% bands · <strong>Bubble Score</strong> ≥70 expects ≤0%, &lt;30 expects ≥0%.
      </p>
    </section>
  );
}
