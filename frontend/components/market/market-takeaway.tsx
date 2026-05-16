"use client";

import { useQuery } from "@tanstack/react-query";
import { Sparkles, ArrowUp, ArrowDown, Hourglass, Shield, Minus } from "lucide-react";
import { marketApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { RefreshButton } from "@/components/ui/refresh-button";
import { cn } from "@/lib/utils";

const TONE: Record<string, { color: string; border: string; Icon: typeof ArrowUp; label: string }> = {
  bullish:          { color: "text-accent-greenSoft", border: "border-accent-green/50",  Icon: ArrowUp,    label: "Risk-On" },
  cautious_bullish: { color: "text-accent-greenSoft", border: "border-accent-green/40",  Icon: ArrowUp,    label: "Constructive" },
  cautious:         { color: "text-accent-amber",     border: "border-accent-amber/50",  Icon: Hourglass,  label: "Cautious" },
  neutral:          { color: "text-text-secondary",   border: "border-bg-borderHi",      Icon: Minus,      label: "Neutral" },
  defensive:        { color: "text-accent-redSoft",   border: "border-accent-red/50",    Icon: Shield,     label: "Defensive" },
};

export function MarketTakeaway() {
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["market-takeaway"],
    queryFn: () => marketApi.takeaway(),
    staleTime: 10 * 60 * 1000,
    refetchInterval: 15 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <section className="card p-6">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles size={16} className="text-accent-blue" />
          <h3 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Today's takeaway</h3>
        </div>
        <Skeleton className="h-24 w-full" />
      </section>
    );
  }
  if (!data) return null;

  const tone = TONE[data.tone] || TONE.neutral;
  const Icon = tone.Icon;

  return (
    <section className={cn("card p-5 border-l-4", tone.border)}>
      <div className="flex items-center gap-2 mb-3">
        <Sparkles size={14} className="text-accent-blue" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
          Today's market takeaway
        </h3>
        <span className="text-[10px] text-text-muted ml-auto">synthesized from regime · breadth · volatility</span>
        <RefreshButton onClick={() => refetch()} isFetching={isFetching} title="Refresh takeaway" />
      </div>

      <div className="flex items-start gap-4 mb-3">
        <div className={cn("shrink-0 w-12 h-12 rounded-lg grid place-items-center", "bg-bg-base ring-1 ring-inset ring-bg-borderHi", tone.color)}>
          <Icon size={22} strokeWidth={2.4} />
        </div>
        <div className="flex-1 min-w-0">
          <div className={cn("text-2xl font-bold leading-tight", tone.color)}>
            {tone.label}
          </div>
          <p className="text-sm text-text-secondary mt-1 leading-snug">{data.headline}</p>
          <p className="text-sm text-text-primary mt-1.5 font-medium">{data.stance}.</p>
        </div>
      </div>

      {data.bullets.length > 0 && (
        <ul className="space-y-1.5 mt-3 pt-3 border-t border-bg-border">
          {data.bullets.map((b, i) => (
            <li key={i} className="text-[13px] text-text-secondary leading-relaxed flex items-start gap-2">
              <span className="text-text-dim mt-0.5">•</span>
              <span>{b}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
