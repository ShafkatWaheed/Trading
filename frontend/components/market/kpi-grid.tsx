"use client";

import type { KpiCard } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Landmark, Activity, Users, TrendingUp, Factory, DollarSign,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  bank: Landmark,
  activity: Activity,
  users: Users,
  trending: TrendingUp,
  factory: Factory,
  dollar: DollarSign,
};

function toneStyle(tone: KpiCard["tone"]) {
  switch (tone) {
    case "red":
      return {
        stripe: "bg-accent-red",
        text: "text-accent-redSoft",
        bg: "bg-accent-red/10",
        chip: "badge-red",
      };
    case "amber":
      return {
        stripe: "bg-accent-amber",
        text: "text-accent-amber",
        bg: "bg-accent-amber/10",
        chip: "badge-amber",
      };
    case "green":
      return {
        stripe: "bg-accent-greenSoft",
        text: "text-accent-greenSoft",
        bg: "bg-accent-green/10",
        chip: "badge-green",
      };
    default:
      return {
        stripe: "bg-bg-borderHi",
        text: "text-text-secondary",
        bg: "bg-bg-card2",
        chip: "badge-zinc",
      };
  }
}

export function KpiGrid({ kpis, loading }: { kpis?: KpiCard[]; loading?: boolean }) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
    );
  }
  if (!kpis || kpis.length === 0) {
    return <div className="text-text-muted text-sm">No macro data available.</div>;
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {kpis.map((k) => {
        const tone = toneStyle(k.tone);
        const Icon = (k.icon && ICONS[k.icon]) || Activity;
        return (
          <div
            key={k.name}
            className="group card relative p-5 flex flex-col gap-3 hover:border-bg-borderHi transition-colors overflow-hidden"
          >
            {/* Left tone stripe */}
            <div className={cn("absolute left-0 top-3 bottom-3 w-[3px] rounded-full opacity-90", tone.stripe)} />

            <div className="flex items-start justify-between gap-2 pl-1">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className={cn("w-8 h-8 rounded-lg grid place-items-center ring-1 ring-inset ring-white/5", tone.bg)}>
                  <Icon size={14} className={tone.text} strokeWidth={2.4} />
                </div>
                <div className="min-w-0">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
                    {k.name}
                  </div>
                  <div className="text-[22px] font-semibold tabular-nums tracking-tight mt-0.5">
                    {k.value}
                  </div>
                </div>
              </div>
              {k.status && (
                <span className={cn("badge mt-0.5 shrink-0", tone.chip)}>
                  {k.status}
                </span>
              )}
            </div>

            {k.why && (
              <p className="text-[12px] text-text-secondary leading-relaxed pl-1">
                {k.why}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
