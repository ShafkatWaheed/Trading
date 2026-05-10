"use client";

import type { YieldCurveSummary } from "@/lib/api/types";
import { TrendingUp, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

export function YieldCurveCard({ data }: { data?: YieldCurveSummary | null }) {
  if (!data) return null;

  const tone = data.inverted
    ? { text: "text-accent-redSoft", bg: "bg-accent-red/10", chip: "badge-red", icon: AlertTriangle, glow: "card-glow-amber" }
    : data.label === "Flattening"
    ? { text: "text-accent-amber", bg: "bg-accent-amber/10", chip: "badge-amber", icon: TrendingUp, glow: "card-glow-amber" }
    : { text: "text-accent-greenSoft", bg: "bg-accent-green/10", chip: "badge-green", icon: TrendingUp, glow: "card-glow-green" };

  const Icon = tone.icon;

  return (
    <div className={cn("card p-5", tone.glow)}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <div className={cn("w-7 h-7 rounded-lg grid place-items-center ring-1 ring-inset ring-white/5", tone.bg)}>
            <Icon size={14} className={tone.text} strokeWidth={2.4} />
          </div>
          <h3 className="text-sm font-semibold tracking-tight">Yield Curve</h3>
        </div>
        <span className={cn("badge", tone.chip)}>{data.label}</span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <YieldCell label="2Y" value={`${data.two_year.toFixed(2)}%`} />
        <YieldCell label="10Y" value={`${data.ten_year.toFixed(2)}%`} />
        <YieldCell
          label="Spread"
          value={`${data.spread >= 0 ? "+" : ""}${data.spread.toFixed(2)}%`}
          tone={tone.text}
          highlight
        />
      </div>
    </div>
  );
}

function YieldCell({ label, value, tone, highlight }: { label: string; value: string; tone?: string; highlight?: boolean }) {
  return (
    <div className={cn(
      "rounded-lg p-3 text-center",
      highlight ? "bg-bg-card2 border border-bg-borderHi" : "bg-bg-base/50 border border-bg-divider",
    )}>
      <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">{label}</div>
      <div className={cn("text-lg font-semibold tabular-nums tracking-tight mt-1", tone ?? "text-text-primary")}>
        {value}
      </div>
    </div>
  );
}
