"use client";

import { useQuery } from "@tanstack/react-query";
import { Target, ArrowUp, ArrowDown, Minus, Hourglass, Loader2 } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

const TONE_MAP: Record<string, { color: string; bg: string; border: string; Icon: typeof ArrowUp }> = {
  strong_bullish:    { color: "text-accent-greenSoft", bg: "bg-accent-green/10",  border: "border-accent-green/50",   Icon: ArrowUp },
  bullish:           { color: "text-accent-greenSoft", bg: "bg-accent-green/5",   border: "border-accent-green/40",   Icon: ArrowUp },
  cautious_bullish:  { color: "text-accent-amber",     bg: "bg-accent-amber/5",   border: "border-accent-amber/40",   Icon: Hourglass },
  neutral:           { color: "text-text-secondary",   bg: "bg-bg-card2",         border: "border-bg-borderHi",       Icon: Minus },
  cautious_bearish:  { color: "text-accent-amber",     bg: "bg-accent-amber/5",   border: "border-accent-amber/40",   Icon: ArrowDown },
  bearish:           { color: "text-accent-redSoft",   bg: "bg-accent-red/5",     border: "border-accent-red/40",     Icon: ArrowDown },
  strong_bearish:    { color: "text-accent-redSoft",   bg: "bg-accent-red/10",    border: "border-accent-red/50",     Icon: ArrowDown },
};

export function RecommendationCard({ symbol }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["recommendation", symbol],
    queryFn: () => stocksApi.recommendation(symbol),
    staleTime: 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) {
    return (
      <section className="card p-5">
        <div className="flex items-center gap-2 mb-3">
          <Target size={16} className="text-accent-blue" />
          <h3 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Action</h3>
          <Loader2 size={12} className="animate-spin text-text-muted ml-auto" />
        </div>
        <Skeleton className="h-20 w-full" />
      </section>
    );
  }

  if (!data) return null;
  const tone = TONE_MAP[data.tone] || TONE_MAP.neutral;
  const Icon = tone.Icon;
  const c = data.components;

  return (
    <section className={cn("card p-5 border-l-4", tone.border)}>
      <div className="flex items-center gap-2 mb-3">
        <Target size={14} className="text-accent-blue" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
          Risk-Adjusted Recommendation
        </h3>
        <span className="text-[10px] text-text-muted ml-auto">
          synthesized from verdict · valuation · analysts · smart money
        </span>
      </div>

      <div className="flex items-start gap-4 mb-3">
        <div className={cn("shrink-0 w-12 h-12 rounded-lg grid place-items-center", tone.bg, tone.color)}>
          <Icon size={24} strokeWidth={2.4} />
        </div>
        <div className="flex-1 min-w-0">
          <div className={cn("text-2xl font-bold leading-tight", tone.color)}>
            {data.action_label}
          </div>
          <p className="text-sm text-text-secondary mt-1 leading-snug">{data.headline}</p>
        </div>
      </div>

      {data.wait_reason && (
        <div className="bg-bg-base rounded-md p-3 border border-bg-border mb-3 flex items-start gap-2">
          <Hourglass size={14} className="text-accent-amber mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="text-sm text-text-secondary leading-relaxed">{data.wait_reason}</p>
          </div>
        </div>
      )}

      <div className="text-[11px] text-text-secondary leading-relaxed mb-2">
        <span className="text-text-muted">Why: </span>
        {data.reasoning}
      </div>

      {data.reevaluate && (
        <div className="text-[11px] text-text-muted italic">{data.reevaluate}</div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-4 pt-3 border-t border-bg-border text-[11px]">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Verdict</div>
          <div className="font-semibold text-text-primary">{c.verdict || "—"}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Bubble Score</div>
          <div className="font-semibold text-text-primary tabular-nums">
            {c.bubble_score != null ? `${c.bubble_score.toFixed(0)} · ${c.bubble_label}` : "—"}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Street</div>
          <div className="font-semibold text-text-primary">
            {c.analyst_rating ? c.analyst_rating.replace("_", " ") : "—"}
            {c.analyst_upside != null && (
              <span className={cn("ml-1 tabular-nums", c.analyst_upside >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft")}>
                ({c.analyst_upside >= 0 ? "+" : ""}{c.analyst_upside.toFixed(1)}%)
              </span>
            )}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Smart Money</div>
          <div className="font-semibold text-text-primary">
            <span className={c.insider === "buying" ? "text-accent-greenSoft" : c.insider === "selling" ? "text-accent-redSoft" : ""}>
              ins {c.insider}
            </span>
            <span className="text-text-muted mx-1">·</span>
            <span className={c.congress === "buying" ? "text-accent-greenSoft" : c.congress === "selling" ? "text-accent-redSoft" : ""}>
              pol {c.congress}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
