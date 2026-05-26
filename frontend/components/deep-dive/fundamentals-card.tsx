"use client";

import { useQuery } from "@tanstack/react-query";
import { Gauge, Sparkles, AlertTriangle, TrendingUp, Banknote, ShieldCheck, Scale } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import type { FundamentalPillar } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

const PILLAR_META: Record<
  FundamentalPillar["name"],
  { Icon: typeof Banknote; accent: string; ring: string; soft: string; tag: string }
> = {
  valuation: {
    Icon: Scale,
    accent: "text-accent-violet",
    ring:   "border-accent-violet/40",
    soft:   "bg-accent-violet/5",
    tag:    "bg-accent-violet/10 text-accent-violet border-accent-violet/30",
  },
  growth: {
    Icon: TrendingUp,
    accent: "text-accent-blue",
    ring:   "border-accent-blue/40",
    soft:   "bg-accent-blue/5",
    tag:    "bg-accent-blue/10 text-accent-blue border-accent-blue/30",
  },
  profitability: {
    Icon: Banknote,
    accent: "text-accent-greenSoft",
    ring:   "border-accent-green/40",
    soft:   "bg-accent-green/5",
    tag:    "bg-accent-green/10 text-accent-greenSoft border-accent-green/30",
  },
  health: {
    Icon: ShieldCheck,
    accent: "text-accent-cyan",
    ring:   "border-accent-cyan/40",
    soft:   "bg-accent-cyan/5",
    tag:    "bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30",
  },
};

function ScoreDots({ score, accent }: { score: number; accent: string }) {
  return (
    <div className="flex items-center gap-1" aria-label={`Score ${score} of 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <span
          key={n}
          className={cn(
            "h-1.5 rounded-full transition-all",
            n <= score
              ? cn("w-4", accent.replace("text-", "bg-"))
              : "w-2 bg-bg-border",
          )}
        />
      ))}
    </div>
  );
}

function fmtMetric(value: number | null, unit: string): string {
  if (value == null) return "—";
  if (unit === "%") {
    const sign = value > 0 && Math.abs(value) < 1000 ? "" : "";
    return `${sign}${value.toFixed(1)}%`;
  }
  if (unit === "x") return `${value.toFixed(2)}×`;
  return `${value}${unit}`;
}

function metricTone(value: number | null, label: string, unit: string): string {
  if (value == null) return "text-text-muted";
  // Heuristic colorization for at-a-glance read
  if (unit === "%") {
    if (label.toLowerCase().includes("growth")) {
      if (value >= 15) return "text-accent-greenSoft";
      if (value < 0)   return "text-accent-redSoft";
    }
    if (label.toLowerCase().includes("margin") || label.toLowerCase().includes("equity")) {
      if (value >= 20) return "text-accent-greenSoft";
      if (value < 5 && value > 0)  return "text-accent-amber";
      if (value <= 0)  return "text-accent-redSoft";
    }
  }
  if (label === "PEG") {
    if (value < 1) return "text-accent-greenSoft";
    if (value > 2) return "text-accent-redSoft";
  }
  if (label.includes("P/E")) {
    if (value > 35) return "text-accent-amber";
    if (value < 15 && value > 0) return "text-accent-greenSoft";
  }
  if (label === "Debt / equity") {
    if (value > 2) return "text-accent-redSoft";
    if (value < 0.5) return "text-accent-greenSoft";
  }
  return "text-text-primary";
}

export function FundamentalsCard({ symbol }: Props) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["fundamentals", symbol],
    queryFn: () => stocksApi.fundamentals(symbol),
    staleTime: 12 * 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <Gauge size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">Business Quality</h3>
        </div>
        <Skeleton className="h-64 w-full" />
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <Gauge size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">Business Quality</h3>
        </div>
        <p className="text-text-muted text-sm">
          {(error as Error)?.message || "Fundamentals unavailable."}
        </p>
      </section>
    );
  }

  if (!data.available) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <Gauge size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">Business Quality</h3>
        </div>
        <p className="text-text-muted text-sm">
          {data.error || "Upstream didn't return fundamentals for this ticker."}
        </p>
      </section>
    );
  }

  return (
    <section className="card-subtle p-6 overflow-hidden relative">
      {/* Decorative gradient behind the lede — gives the "story" feel */}
      <div
        className="absolute inset-x-0 top-0 h-32 pointer-events-none opacity-60"
        style={{
          background:
            "radial-gradient(ellipse 60% 100% at 30% 0%, rgba(168, 85, 247, 0.10) 0%, transparent 70%)",
        }}
      />

      <div className="relative">
        <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Gauge size={16} className="text-accent-violet" />
            <h3 className="text-base font-semibold">Business Quality</h3>
            {data.from_cache && (
              <span className="text-[10px] uppercase tracking-wider text-text-muted">cached</span>
            )}
          </div>
          {data.archetype && (
            <span className="badge text-[10px] bg-accent-violet/10 text-accent-violet border-accent-violet/40 uppercase tracking-wider font-semibold">
              <Sparkles size={10} className="mr-1" />
              {data.archetype}
            </span>
          )}
        </div>

        {/* Lede — the story opens here */}
        {data.lede && (
          <p className="text-text-primary text-[15px] leading-relaxed italic mb-5 max-w-3xl">
            “{data.lede}”
          </p>
        )}

        {/* Overall score belt */}
        <div className="flex items-center gap-3 mb-6 pb-5 border-b border-bg-border">
          <span className="text-[10px] uppercase tracking-wider text-text-muted shrink-0">
            Overall
          </span>
          <ScoreDots score={data.overall_score ?? 0} accent="text-accent-violet" />
          <span className="font-numeric text-sm tabular-nums text-text-secondary">
            {data.overall_score}/5
          </span>
          <span className="ml-auto text-[10px] text-text-muted">
            valuation · growth · profitability · health
          </span>
        </div>

        {/* Four pillars — 2x2 grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {data.pillars.map((p) => {
            const meta = PILLAR_META[p.name];
            const Icon = meta.Icon;
            return (
              <div
                key={p.name}
                className={cn(
                  "rounded-lg border-l-2 border border-bg-border p-4 transition-colors",
                  meta.ring,
                  meta.soft,
                )}
              >
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <Icon size={14} className={meta.accent} />
                    <span className={cn("text-xs font-semibold uppercase tracking-wider", meta.accent)}>
                      {p.label}
                    </span>
                  </div>
                  <ScoreDots score={p.score} accent={meta.accent} />
                </div>

                <p className="text-text-secondary text-[13px] leading-snug mb-3">
                  {p.story}
                </p>

                <div className="flex flex-wrap gap-x-4 gap-y-1.5 pt-2 border-t border-bg-divider">
                  {p.metrics.map((m) => (
                    <div key={m.label} className="flex flex-col">
                      <span className="text-[9px] uppercase tracking-wider text-text-muted">
                        {m.label}
                      </span>
                      <span
                        className={cn(
                          "font-numeric text-sm tabular-nums font-semibold",
                          metricTone(m.value, m.label, m.unit),
                        )}
                      >
                        {fmtMetric(m.value, m.unit)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Strengths / weaknesses — quick tally at the bottom */}
        {(data.strengths.length > 0 || data.weaknesses.length > 0) && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-5">
            {data.strengths.length > 0 && (
              <div className="rounded-md border border-accent-green/20 bg-accent-green/[0.04] p-3">
                <div className="text-[10px] uppercase tracking-wider font-semibold text-accent-greenSoft mb-2 flex items-center gap-1.5">
                  <Sparkles size={11} /> Strengths · {data.strengths.length}
                </div>
                <ul className="space-y-1">
                  {data.strengths.map((s, i) => (
                    <li key={i} className="text-[12px] text-text-secondary leading-snug">
                      · {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {data.weaknesses.length > 0 && (
              <div className="rounded-md border border-accent-amber/20 bg-accent-amber/[0.04] p-3">
                <div className="text-[10px] uppercase tracking-wider font-semibold text-accent-amber mb-2 flex items-center gap-1.5">
                  <AlertTriangle size={11} /> Watch · {data.weaknesses.length}
                </div>
                <ul className="space-y-1">
                  {data.weaknesses.map((w, i) => (
                    <li key={i} className="text-[12px] text-text-secondary leading-snug">
                      · {w}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
