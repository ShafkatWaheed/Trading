"use client";

import type { SignalResultRow } from "@/lib/api/types";
import { cn, formatPercent } from "@/lib/utils";

function gradeTone(grade: string) {
  if (grade === "A+" || grade === "A") return { bg: "bg-accent-green/15", text: "text-accent-greenSoft", border: "border-accent-green/40" };
  if (grade === "B+" || grade === "B") return { bg: "bg-accent-blue/15", text: "text-accent-blue", border: "border-accent-blue/40" };
  if (grade === "C") return { bg: "bg-accent-amber/15", text: "text-accent-amber", border: "border-accent-amber/40" };
  return { bg: "bg-accent-red/15", text: "text-accent-redSoft", border: "border-accent-red/40" };
}

function winRateColor(wr: number) {
  if (wr >= 0.65) return "text-accent-greenSoft";
  if (wr < 0.45) return "text-accent-redSoft";
  return "text-accent-amber";
}

export function SignalAccuracyCard({ row, rank }: { row: SignalResultRow; rank: number }) {
  const grade = gradeTone(row.grade || "C");
  const dots = (row.trades || []).slice(0, 18).map((t, i) => (
    <span
      key={i}
      className={cn(
        "text-[10px] leading-none",
        t.outcome === "win" ? "text-accent-greenSoft" : "text-accent-redSoft",
      )}
      title={`${t.outcome.toUpperCase()}: ${t.pnl_percent >= 0 ? "+" : ""}${t.pnl_percent.toFixed(1)}% in ${t.hold_days}d`}
    >
      {t.outcome === "win" ? "●" : "○"}
    </span>
  ));

  const label = row.signal_name.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());

  return (
    <div className="card p-4 hover:border-bg-borderHi transition-colors">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-text-dim text-[11px] font-bold tabular-nums">#{rank + 1}</span>
            <span className="font-semibold text-sm tracking-tight">{label}</span>
            <span className="badge-zinc text-[10px]">
              {row.direction === "buy" ? "↑ Buy" : "↓ Sell"}
            </span>
          </div>
          {row.description && (
            <p className="text-[11px] text-text-muted mt-1 line-clamp-1">{row.description}</p>
          )}
        </div>
        <span className={cn("badge font-bold text-[13px] px-2.5 py-1 shrink-0", grade.bg, grade.text, grade.border)}>
          {row.grade}
        </span>
      </div>

      {dots.length > 0 && (
        <div className="flex flex-wrap gap-0.5 mb-3 leading-none p-2 rounded bg-bg-base/40 border border-bg-divider">
          {dots}
        </div>
      )}

      <div className="grid grid-cols-5 gap-1.5">
        <Stat label="Win" value={`${(row.win_rate * 100).toFixed(0)}%`} tone={winRateColor(row.win_rate)} />
        <Stat
          label="Avg"
          value={formatPercent(row.avg_return)}
          tone={row.avg_return >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft"}
        />
        <Stat label="N" value={String(row.total_trades)} tone="text-text-primary" />
        <Stat label="Best" value={formatPercent(row.max_gain)} tone="text-accent-greenSoft" />
        <Stat label="Worst" value={formatPercent(row.max_loss)} tone="text-accent-redSoft" />
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="bg-bg-base/50 border border-bg-divider rounded-md p-2 text-center">
      <div className="text-[9px] uppercase tracking-wider text-text-muted font-semibold">{label}</div>
      <div className={cn("text-sm font-semibold tabular-nums tracking-tight mt-0.5", tone)}>
        {value}
      </div>
    </div>
  );
}
