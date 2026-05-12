"use client";

import type { SectorFlow } from "@/lib/api/types";
import { TrendingUp, TrendingDown, ChevronsUp, ChevronsDown, Minus } from "lucide-react";
import { cn, formatPercent } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

function accelBadge(accel?: string | null) {
  if (accel === "accelerating") return { Icon: ChevronsUp,   color: "text-accent-greenSoft", label: "accelerating" };
  if (accel === "decelerating") return { Icon: ChevronsDown, color: "text-accent-redSoft",   label: "decelerating" };
  if (accel === "steady")       return { Icon: Minus,        color: "text-text-muted",       label: "steady" };
  return null;
}

export function SectorFlows({ sectors, loading }: { sectors?: SectorFlow[]; loading?: boolean }) {
  if (loading) {
    return <Skeleton className="h-[420px] w-full" />;
  }
  if (!sectors || sectors.length === 0) {
    return <div className="text-text-muted text-sm">No sector data available.</div>;
  }

  const sorted = [...sectors].sort((a, b) => b.change_pct - a.change_pct);
  const max = Math.max(...sorted.map((s) => Math.abs(s.change_pct)), 1);

  return (
    <div className="card p-6">
      <div className="space-y-3">
        {sorted.map((s) => {
          const positive = s.change_pct >= 0;
          const widthPct = (Math.abs(s.change_pct) / max) * 50;
          return (
            <div key={s.sector} className="flex items-center gap-4 text-sm group">
              <div className="w-44 truncate text-[13px] text-text-secondary flex items-center gap-2 shrink-0">
                {positive ? (
                  <TrendingUp size={11} className="text-accent-greenSoft shrink-0" strokeWidth={2.4} />
                ) : (
                  <TrendingDown size={11} className="text-accent-redSoft shrink-0" strokeWidth={2.4} />
                )}
                <span className="font-medium">{s.sector}</span>
              </div>
              <div className="flex-1 relative h-7 flex items-center bg-bg-base/30 rounded">
                <div className="absolute inset-y-0 left-1/2 w-px bg-bg-borderHi" />
                <div
                  className={cn(
                    "absolute h-5 rounded-sm transition-all duration-500 ease-out-expo",
                    "ring-1 ring-inset ring-white/5",
                    positive
                      ? "left-1/2 bg-gradient-to-r from-accent-green/30 to-accent-green/60 border-r border-accent-greenSoft"
                      : "right-1/2 bg-gradient-to-l from-accent-red/30 to-accent-red/60 border-l border-accent-redSoft",
                  )}
                  style={{ width: `${widthPct}%` }}
                />
              </div>
              <div
                className={cn(
                  "w-16 text-right tabular-nums text-[13px] font-semibold shrink-0",
                  positive ? "text-accent-greenSoft" : "text-accent-redSoft",
                )}
              >
                {formatPercent(s.change_pct)}
              </div>
              {(() => {
                const badge = accelBadge(s.accel);
                if (!badge) return <div className="w-32 shrink-0" />;
                const Icon = badge.Icon;
                return (
                  <div
                    className="w-32 shrink-0 flex items-center gap-1 text-[10px]"
                    title={
                      s.change_pct_prior != null
                        ? `Prior period: ${s.change_pct_prior >= 0 ? "+" : ""}${s.change_pct_prior.toFixed(2)}% · Delta ${(s.delta_pp ?? 0) >= 0 ? "+" : ""}${(s.delta_pp ?? 0).toFixed(2)} pp`
                        : ""
                    }
                  >
                    <Icon size={11} className={badge.color} strokeWidth={2.4} />
                    <span className={cn("uppercase tracking-wider font-semibold", badge.color)}>
                      {badge.label}
                    </span>
                    {s.delta_pp != null && (
                      <span className="text-text-muted tabular-nums">
                        ({s.delta_pp >= 0 ? "+" : ""}{s.delta_pp.toFixed(1)}pp)
                      </span>
                    )}
                  </div>
                );
              })()}
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-text-muted mt-4 pt-3 border-t border-bg-border">
        Right column compares this period vs the prior same-length window.
        Accelerating = current period is &gt;1pp stronger than prior.
        Decelerating = current period is &gt;1pp weaker than prior.
      </p>
    </div>
  );
}
