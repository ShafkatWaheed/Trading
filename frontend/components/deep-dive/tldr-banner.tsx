"use client";

import { useQuery } from "@tanstack/react-query";
import { Sparkles, ArrowUpRight, ArrowDownRight, Gauge } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

function scoreTone(score: number) {
  if (score < 25)  return { color: "text-accent-greenSoft", border: "border-accent-green/40" };
  if (score < 50)  return { color: "text-accent-blue",      border: "border-accent-blue/40" };
  if (score < 70)  return { color: "text-accent-amber",     border: "border-accent-amber/60" };
  if (score < 85)  return { color: "text-accent-amberSoft", border: "border-accent-amber/60" };
  return                   { color: "text-accent-redSoft",  border: "border-accent-red/40" };
}

function firstSentence(s: string | undefined): string {
  if (!s) return "";
  const trimmed = s.trim();
  const m = trimmed.match(/^[^.!?]*[.!?]/);
  return (m ? m[0] : trimmed).trim();
}

export function TldrBanner({ symbol }: Props) {
  const bull = useQuery({
    queryKey: ["bull-narrative", symbol],
    queryFn: () => stocksApi.bullNarrative(symbol),
    staleTime: 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });
  const bear = useQuery({
    queryKey: ["risk-narrative", symbol],
    queryFn: () => stocksApi.riskNarrative(symbol),
    staleTime: 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });
  const bubble = useQuery({
    queryKey: ["bubble-score", symbol],
    queryFn: () => stocksApi.bubbleScore(symbol),
    staleTime: 6 * 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });
  const analyst = useQuery({
    queryKey: ["analyst-consensus", symbol],
    queryFn: () => stocksApi.analystConsensus(symbol),
    staleTime: 12 * 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  const isLoading = bull.isLoading || bear.isLoading || bubble.isLoading;

  const bullPoint = firstSentence(
    bull.data?.growth_drivers || bull.data?.catalysts || bull.data?.competitive_moat
  );
  const bearPoint = firstSentence(
    bear.data?.worst_case || bear.data?.competitive_risks || bear.data?.industry_threats
  );

  const score = bubble.data?.score ?? null;
  const scoreLabel = bubble.data?.label ?? null;
  const tone = score != null ? scoreTone(score) : null;
  const upside = analyst.data?.upside_pct ?? null;
  const rating = analyst.data?.rating ?? null;

  if (isLoading && !bullPoint && !bearPoint) {
    return (
      <section className="card p-5">
        <Skeleton className="h-32 w-full" />
      </section>
    );
  }

  return (
    <section className={cn("card p-5 border-l-4", tone?.border || "border-bg-borderHi")}>
      <div className="flex items-center gap-2 mb-3">
        <Sparkles size={14} className="text-accent-blue" />
        <h3 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">TL;DR</h3>
        <span className="text-[10px] text-text-muted">3-second read</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-4">
        <div className="space-y-2.5">
          {bullPoint && (
            <div className="flex items-start gap-2.5">
              <ArrowUpRight size={14} className="text-accent-greenSoft mt-0.5 shrink-0" />
              <div>
                <span className="text-[10px] uppercase tracking-wider text-accent-greenSoft font-semibold mr-2">Bull</span>
                <span className="text-sm text-text-secondary leading-relaxed">{bullPoint}</span>
              </div>
            </div>
          )}
          {bearPoint && (
            <div className="flex items-start gap-2.5">
              <ArrowDownRight size={14} className="text-accent-redSoft mt-0.5 shrink-0" />
              <div>
                <span className="text-[10px] uppercase tracking-wider text-accent-redSoft font-semibold mr-2">Bear</span>
                <span className="text-sm text-text-secondary leading-relaxed">{bearPoint}</span>
              </div>
            </div>
          )}
          {(rating || upside != null) && (
            <div className="flex items-start gap-2.5">
              <span className="text-accent-blue text-[10px] mt-0.5 shrink-0 font-bold">$$</span>
              <div>
                <span className="text-[10px] uppercase tracking-wider text-accent-blue font-semibold mr-2">Street</span>
                <span className="text-sm text-text-secondary leading-relaxed">
                  Wall Street consensus: <span className="font-semibold text-text-primary">{rating || "—"}</span>
                  {upside != null && <>, target implies <span className={cn("font-semibold", upside >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft")}>{upside >= 0 ? "+" : ""}{upside.toFixed(1)}%</span> over 12 months.</>}
                </span>
              </div>
            </div>
          )}
        </div>

        {score != null && tone && (
          <div className={cn("flex flex-col items-center justify-center px-4 sm:border-l border-bg-border min-w-[110px]", tone.color)}>
            <Gauge size={14} className="mb-1 opacity-70" />
            <div className="text-2xl font-bold tabular-nums leading-none">{score.toFixed(0)}</div>
            <div className="text-[10px] uppercase tracking-wider mt-1">{scoreLabel}</div>
            <div className="text-[9px] text-text-muted mt-0.5">Bubble Score</div>
          </div>
        )}
      </div>
    </section>
  );
}
