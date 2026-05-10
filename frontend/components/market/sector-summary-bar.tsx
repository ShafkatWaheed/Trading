"use client";

import type { SectorSummary } from "@/lib/api/types";
import { TrendingUp, TrendingDown, Activity } from "lucide-react";
import { cn, formatPercent } from "@/lib/utils";

export function SectorSummaryBar({ summary, period }: { summary: SectorSummary; period: string }) {
  const netPositive = summary.net >= 0;
  const netLabel = netPositive ? "Net Inflow" : "Net Outflow";

  return (
    <div className="card p-5 mb-4">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="text-[11px] text-text-muted uppercase tracking-wider font-semibold">
          Sector Flows · {period} · {summary.total} sectors
        </div>
        <span className={cn(
          "badge text-[11px]",
          netPositive ? "badge-green" : "badge-red",
        )}>
          {netLabel}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <SummaryStat
          icon={<Activity size={11} />}
          label="Net"
          value={formatPercent(summary.net)}
          tone={netPositive ? "green" : "red"}
        />
        <SummaryStat
          icon={<TrendingUp size={11} />}
          label={`Inflows · ${summary.gaining}`}
          value={`+${summary.inflow.toFixed(1)}%`}
          tone="green"
        />
        <SummaryStat
          icon={<TrendingDown size={11} />}
          label={`Outflows · ${summary.losing}`}
          value={`${summary.outflow.toFixed(1)}%`}
          tone="red"
        />
      </div>
    </div>
  );
}

function SummaryStat({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone: "green" | "red";
}) {
  const text = tone === "green" ? "text-accent-greenSoft" : "text-accent-redSoft";
  return (
    <div className="bg-bg-base/50 border border-bg-divider rounded-lg p-3 text-center">
      <div className="flex items-center gap-1 justify-center text-[10px] uppercase tracking-wider text-text-muted">
        {icon}
        {label}
      </div>
      <div className={cn("text-2xl font-semibold tabular-nums tracking-tight mt-1", text)}>
        {value}
      </div>
    </div>
  );
}
