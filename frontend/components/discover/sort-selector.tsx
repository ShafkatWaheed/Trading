"use client";

import { ArrowUpDown, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { OpportunityCard } from "@/lib/api/types";

export type SortKey =
  | "score" | "change_pct" | "volume" | "rr" | "momentum" | "flow";

export const SORT_OPTIONS: { key: SortKey; label: string; hint: string }[] = [
  { key: "score",      label: "Composite Score",   hint: "Default — overall ranking" },
  { key: "change_pct", label: "Period % Gain",     hint: "Biggest movers over selected period" },
  { key: "volume",     label: "Volume Spike",      hint: "Highest volume vs 20-day average" },
  { key: "rr",         label: "Risk-Reward",       hint: "Best upside vs downside distance" },
  { key: "momentum",   label: "Price Momentum",    hint: "Strongest RSI / MACD / trend" },
  { key: "flow",       label: "Smart-Money Flow",  hint: "Options + insider buying signal" },
];

export function applySort(ops: OpportunityCard[], sort: SortKey): OpportunityCard[] {
  const arr = [...ops];
  const get = (op: OpportunityCard): number => {
    switch (sort) {
      case "change_pct": return op.change_pct ?? -Infinity;
      case "volume":     return op.sub_scores?.volume ?? 0;
      case "rr":         return op.risk_reward_ratio ?? 0;
      case "momentum":   return op.sub_scores?.price ?? 0;
      case "flow":       return op.sub_scores?.flow ?? 0;
      case "score":
      default:           return op.score ?? 0;
    }
  };
  arr.sort((a, b) => get(b) - get(a));
  return arr;
}

export function SortSelector({ value, onChange }: { value: SortKey; onChange: (v: SortKey) => void }) {
  const current = SORT_OPTIONS.find((o) => o.key === value) ?? SORT_OPTIONS[0];
  return (
    <div className="relative inline-block">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as SortKey)}
        className={cn(
          "appearance-none bg-bg-base border border-bg-border rounded-md",
          "pl-8 pr-7 py-1.5 text-[12px] font-medium",
          "focus:outline-none focus:border-accent-amber/60 hover:border-bg-borderHi",
          "cursor-pointer"
        )}
        title={current.hint}
      >
        {SORT_OPTIONS.map((o) => (
          <option key={o.key} value={o.key}>{o.label}</option>
        ))}
      </select>
      <ArrowUpDown size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
      <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
    </div>
  );
}
