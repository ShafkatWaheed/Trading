"use client";

import type { VolumeProfile } from "@/lib/api/types";
import { BarChart2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function VolumeProfileChart({ data }: { data: VolumeProfile }) {
  const rows = [...data.rows].sort((a, b) => b.price - a.price); // high → low (top → bottom)
  if (rows.length === 0) return null;

  const maxVol = Math.max(...rows.map((r) => r.volume), 1);

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2">
          <BarChart2 size={14} className="text-accent-amber" />
          <h3 className="text-sm font-semibold">
            Volume Profile · {data.period_days}d
          </h3>
        </div>
        {data.poc != null && (
          <span className="text-xs text-text-muted">
            POC <span className="text-accent-amber font-semibold tabular-nums">${data.poc.toFixed(2)}</span>
          </span>
        )}
      </div>

      <div className="space-y-1">
        {rows.map((r) => {
          const pct = (r.volume / maxVol) * 100;
          const isPoc = data.poc != null && Math.abs(r.price - data.poc) < data.bin_size / 2;
          const isCurrent = Math.abs(r.price - data.last_price) < data.bin_size / 2;
          return (
            <div key={r.price} className="flex items-center gap-2 text-[11px]">
              <span className={cn(
                "w-14 text-right tabular-nums shrink-0",
                isCurrent ? "text-accent-greenSoft font-semibold" : "text-text-muted"
              )}>
                ${r.price.toFixed(0)}
              </span>
              <div className="flex-1 h-3 bg-bg-base border border-bg-border rounded overflow-hidden">
                <div
                  className={cn(
                    "h-full transition-all",
                    isPoc ? "bg-accent-amber/70"
                      : isCurrent ? "bg-accent-greenSoft/60"
                      : "bg-accent-blue/30"
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>
              {isCurrent && (
                <span className="text-accent-greenSoft text-[10px] tabular-nums">← now</span>
              )}
              {isPoc && !isCurrent && (
                <span className="text-accent-amber text-[10px] tabular-nums">← POC</span>
              )}
            </div>
          );
        })}
      </div>

      <p className="text-[11px] text-text-muted mt-3">
        Bars show how much volume traded at each price level. POC = price with most volume = strongest support/resistance.
      </p>
    </div>
  );
}
