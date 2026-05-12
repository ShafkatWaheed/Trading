"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Gauge, Target } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import type { DeepDive } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type Props = {
  data: DeepDive;
  /** Show after the user has scrolled this many pixels (default 320). */
  showAfterPx?: number;
};

const TONE_COLOR: Record<string, string> = {
  strong_bullish:    "text-accent-greenSoft",
  bullish:           "text-accent-greenSoft",
  cautious_bullish:  "text-accent-amber",
  neutral:           "text-text-secondary",
  cautious_bearish:  "text-accent-amber",
  bearish:           "text-accent-redSoft",
  strong_bearish:    "text-accent-redSoft",
};

function bubbleColor(score: number) {
  if (score < 25)  return "text-accent-greenSoft";
  if (score < 50)  return "text-accent-blue";
  if (score < 70)  return "text-accent-amber";
  if (score < 85)  return "text-accent-amberSoft";
  return "text-accent-redSoft";
}

export function StickyVerdictBar({ data, showAfterPx = 320 }: Props) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > showAfterPx);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [showAfterPx]);

  // These two are already loaded by other cards on the page; React Query
  // de-dupes the requests so this is essentially free.
  const bubble = useQuery({
    queryKey: ["bubble-score", data.symbol],
    queryFn: () => stocksApi.bubbleScore(data.symbol),
    staleTime: 6 * 60 * 60 * 1000,
    enabled: Boolean(data.symbol),
  });
  const reco = useQuery({
    queryKey: ["recommendation", data.symbol],
    queryFn: () => stocksApi.recommendation(data.symbol),
    staleTime: 60 * 60 * 1000,
    enabled: Boolean(data.symbol),
  });

  const score = bubble.data?.score ?? null;
  const change = data.period_change?.change_pct ?? null;
  const changeColor = (change ?? 0) >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft";
  const verdictTone = data.verdict?.toLowerCase().includes("buy")
    ? "text-accent-greenSoft"
    : data.verdict?.toLowerCase().includes("sell")
      ? "text-accent-redSoft"
      : "text-text-secondary";

  const recoColor = reco.data?.tone ? (TONE_COLOR[reco.data.tone] || "text-text-secondary") : "text-text-secondary";

  return (
    <div
      className={cn(
        "fixed top-14 left-0 right-0 z-30 backdrop-blur-xl bg-bg-base/85 border-b border-bg-border transition-all duration-200",
        visible
          ? "opacity-100 translate-y-0 pointer-events-auto"
          : "opacity-0 -translate-y-3 pointer-events-none"
      )}
      aria-hidden={!visible}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-11 flex items-center gap-3 sm:gap-5 text-[12px] overflow-x-auto">
        <div className="flex items-baseline gap-1.5 shrink-0">
          <span className="font-bold text-text-primary tracking-tight font-mono">{data.symbol}</span>
          {data.name && (
            <span className="hidden md:inline text-text-muted text-[11px] truncate max-w-[160px]">{data.name}</span>
          )}
        </div>

        {data.price != null && (
          <div className="flex items-baseline gap-1.5 shrink-0 tabular-nums">
            <span className="text-text-primary font-semibold">${data.price.toFixed(2)}</span>
            {change != null && (
              <span className={cn("font-medium", changeColor)}>
                {change >= 0 ? "+" : ""}{change.toFixed(2)}%
              </span>
            )}
          </div>
        )}

        <span className="hidden sm:inline-block w-px h-4 bg-bg-borderHi" />

        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-[10px] uppercase tracking-wider text-text-muted">Verdict</span>
          <span className={cn("font-semibold", verdictTone)}>{data.verdict}</span>
        </div>

        <div className="hidden sm:flex items-center gap-1.5 shrink-0">
          <span className="text-[10px] uppercase tracking-wider text-text-muted">Risk</span>
          <span className="font-semibold tabular-nums">{data.risk_rating}/5</span>
        </div>

        {score != null && (
          <div className="flex items-center gap-1.5 shrink-0">
            <Gauge size={11} className="text-text-muted" />
            <span className={cn("font-semibold tabular-nums", bubbleColor(score))}>
              {score.toFixed(0)}
            </span>
            <span className="hidden md:inline text-[10px] uppercase tracking-wider text-text-muted">
              {bubble.data?.label}
            </span>
          </div>
        )}

        {reco.data && (
          <div className="ml-auto flex items-center gap-1.5 shrink-0">
            <Target size={11} className="text-text-muted" />
            <span className={cn("font-semibold uppercase tracking-wider text-[11px]", recoColor)}>
              {reco.data.action_label}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
