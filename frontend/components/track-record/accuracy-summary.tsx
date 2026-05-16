"use client";

import { useQuery } from "@tanstack/react-query";
import { Target, TrendingUp, TrendingDown, Hourglass, Loader2 } from "lucide-react";
import { trackRecordApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { RefreshButton } from "@/components/ui/refresh-button";
import { cn } from "@/lib/utils";

type Props = { days: number };

function pctTone(p: number): string {
  if (p >= 60) return "text-accent-greenSoft";
  if (p >= 50) return "text-accent-amber";
  return "text-accent-redSoft";
}

function returnTone(r: number): string {
  if (r >= 0.5) return "text-accent-greenSoft";
  if (r <= -0.5) return "text-accent-redSoft";
  return "text-text-secondary";
}

export function AccuracySummary({ days }: Props) {
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["track-record-summary", days],
    queryFn: () => trackRecordApi.summary({ days }),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
    );
  }
  if (!data) return null;
  const o = data.overall;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Target size={14} className="text-accent-blue" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
          Overall accuracy
        </h3>
        <span className="text-[11px] text-text-muted">
          last {days}d · {o.total} graded · {data.pending_count} pending
        </span>
        <RefreshButton onClick={() => refetch()} isFetching={isFetching} title="Refresh" />
        {isFetching && <Loader2 size={11} className="animate-spin text-text-muted" />}
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi
          label="Accuracy"
          value={o.total ? `${o.accuracy_pct.toFixed(1)}%` : "—"}
          sub={o.total ? `${o.correct} of ${o.total} correct` : "no graded decisions yet"}
          tone={o.total ? pctTone(o.accuracy_pct) : "text-text-muted"}
          icon={Target}
        />
        <Kpi
          label="Avg return"
          value={o.total ? `${o.avg_return_pct >= 0 ? "+" : ""}${o.avg_return_pct.toFixed(2)}%` : "—"}
          sub="per decision, all outcomes"
          tone={o.total ? returnTone(o.avg_return_pct) : "text-text-muted"}
          icon={TrendingUp}
        />
        <Kpi
          label="Avg win"
          value={o.total ? `+${o.avg_win_return_pct.toFixed(2)}%` : "—"}
          sub="when AI was right"
          tone="text-accent-greenSoft"
          icon={TrendingUp}
        />
        <Kpi
          label="Avg miss"
          value={o.total ? `${o.avg_loss_return_pct >= 0 ? "+" : ""}${o.avg_loss_return_pct.toFixed(2)}%` : "—"}
          sub="when AI was wrong"
          tone="text-accent-redSoft"
          icon={TrendingDown}
        />
      </div>

      {data.pending_count > 0 && (
        <div className="flex items-start gap-2 text-[11px] text-text-muted bg-bg-card2/60 border border-bg-border rounded-md p-2.5">
          <Hourglass size={12} className="text-accent-amber mt-0.5 shrink-0" />
          <span>
            <strong className="text-text-secondary">{data.pending_count} pending</strong> — these decisions
            haven't matured yet (prediction window still open). They'll be graded automatically
            by the daily evaluator once the window passes.
          </span>
        </div>
      )}
    </div>
  );
}

function Kpi({
  label, value, sub, tone, icon: Icon,
}: {
  label: string; value: string; sub: string; tone: string; icon: typeof Target;
}) {
  return (
    <div className="card-subtle p-4">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-text-muted">
        <Icon size={11} />
        <span>{label}</span>
      </div>
      <div className={cn("text-2xl font-bold tabular-nums mt-1.5", tone)}>{value}</div>
      <div className="text-[11px] text-text-muted mt-1 leading-snug">{sub}</div>
    </div>
  );
}
