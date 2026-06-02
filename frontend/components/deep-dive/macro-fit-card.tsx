"use client";

import { useQuery } from "@tanstack/react-query";
import { Wind, Tornado, CloudFog, Sun, AlertCircle } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

function verdictMeta(verdict: string): { label: string; color: string; bg: string; Icon: typeof Wind } {
  if (verdict === "tailwind")       return { label: "Strong tailwind", color: "text-accent-greenSoft", bg: "bg-accent-green/10 border-accent-green/40", Icon: Sun };
  if (verdict === "mild_tailwind")  return { label: "Mild tailwind",   color: "text-accent-greenSoft", bg: "bg-accent-green/[0.05] border-accent-green/30", Icon: Wind };
  if (verdict === "headwind")       return { label: "Strong headwind", color: "text-accent-redSoft",   bg: "bg-accent-red/10 border-accent-red/40", Icon: Tornado };
  if (verdict === "mild_headwind")  return { label: "Mild headwind",   color: "text-accent-redSoft",   bg: "bg-accent-red/[0.05] border-accent-red/30", Icon: CloudFog };
  return { label: "Neutral", color: "text-text-secondary", bg: "bg-bg-card2 border-bg-borderHi", Icon: Wind };
}

function factorChip(f: string): string {
  return f.replace(/_/g, " ");
}

function fmtPct(v: number | null | undefined): string {
  return v != null ? `${v.toFixed(2)}%` : "—";
}

export function MacroFitCard({ symbol }: Props) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["macro-fit", symbol],
    queryFn: () => stocksApi.macroFit(symbol),
    staleTime: 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <Wind size={16} className="text-accent-cyan" />
          <h3 className="text-base font-semibold">Macro Fit</h3>
        </div>
        <Skeleton className="h-44 w-full" />
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <Wind size={16} className="text-accent-cyan" />
          <h3 className="text-base font-semibold">Macro Fit</h3>
        </div>
        <p className="text-text-muted text-sm">{(error as Error)?.message || "Macro fit unavailable."}</p>
      </section>
    );
  }

  if (!data.available) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <Wind size={16} className="text-accent-cyan" />
          <h3 className="text-base font-semibold">Macro Fit</h3>
        </div>
        <div className="flex items-start gap-2 p-3 rounded-md border border-bg-borderHi bg-bg-base/40">
          <AlertCircle size={14} className="text-text-muted mt-0.5 shrink-0" />
          <p className="text-[12px] text-text-secondary leading-relaxed">{data.reason}</p>
        </div>
      </section>
    );
  }

  const v = verdictMeta(data.verdict);
  const VIcon = v.Icon;
  const s = data.snapshot;

  return (
    <section className="card-subtle p-6 overflow-hidden relative">
      <div
        className="absolute inset-x-0 top-0 h-32 pointer-events-none opacity-50"
        style={{
          background:
            data.verdict.includes("tailwind")
              ? "radial-gradient(ellipse 60% 100% at 50% 0%, rgba(34, 197, 94, 0.08) 0%, transparent 70%)"
              : data.verdict.includes("headwind")
                ? "radial-gradient(ellipse 60% 100% at 50% 0%, rgba(239, 68, 68, 0.08) 0%, transparent 70%)"
                : "radial-gradient(ellipse 60% 100% at 50% 0%, rgba(6, 182, 212, 0.08) 0%, transparent 70%)",
        }}
      />

      <div className="relative">
        <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Wind size={16} className="text-accent-cyan" />
            <h3 className="text-base font-semibold">Macro Fit</h3>
            {data.sector && (
              <span className="text-[10px] uppercase tracking-wider text-text-muted">· {data.sector}</span>
            )}
            {data.from_cache && (
              <span className="text-[10px] uppercase tracking-wider text-text-muted">cached</span>
            )}
          </div>
          <span className={cn(
            "badge text-[10px] uppercase tracking-wider font-semibold inline-flex items-center gap-1",
            v.bg, v.color,
          )}>
            <VIcon size={10} />
            {v.label}
          </span>
        </div>

        {data.verdict_lede && (
          <p className="text-text-primary text-[15px] leading-relaxed italic mb-5 max-w-3xl">
            “{data.verdict_lede}”
          </p>
        )}

        {/* Active regime chips */}
        {data.active_factors.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap mb-5">
            <span className="text-[10px] uppercase tracking-wider text-text-muted">Active regime</span>
            {data.active_factors.map((f) => (
              <span
                key={f}
                className="badge text-[10px] bg-accent-amber/10 text-accent-amber border-accent-amber/30"
              >
                {factorChip(f)}
              </span>
            ))}
          </div>
        )}

        {/* Two-column body */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-5">
          {/* Macro side */}
          <div className="rounded-md border border-bg-border bg-bg-base/30 p-3">
            <div className="flex items-baseline justify-between mb-2">
              <span className="text-[11px] uppercase tracking-wider font-semibold text-accent-cyan">
                Macro backdrop
              </span>
              <span className={cn(
                "text-[11px] font-mono tabular-nums font-semibold",
                data.regime_score > 0 ? "text-accent-greenSoft"
                  : data.regime_score < 0 ? "text-accent-redSoft" : "text-text-muted",
              )}>
                {data.regime_score > 0 ? "+" : ""}{data.regime_score}
              </span>
            </div>
            {data.regime_factors.length > 0 ? (
              <ul className="space-y-1">
                {data.regime_factors.map((f, i) => (
                  <li key={i} className="text-[12px] text-text-secondary leading-snug">· {f}</li>
                ))}
              </ul>
            ) : (
              <p className="text-[12px] text-text-muted italic">No notable macro drivers right now.</p>
            )}
          </div>

          {/* Sector side */}
          <div className="rounded-md border border-bg-border bg-bg-base/30 p-3">
            <div className="flex items-baseline justify-between mb-2">
              <span className="text-[11px] uppercase tracking-wider font-semibold text-accent-violet">
                Sector tilt
              </span>
              <span className={cn(
                "text-[11px] font-mono tabular-nums font-semibold",
                data.sector_score > 0 ? "text-accent-greenSoft"
                  : data.sector_score < 0 ? "text-accent-redSoft" : "text-text-muted",
              )}>
                {data.sector_score > 0 ? "+" : ""}{data.sector_score.toFixed(1)}
              </span>
            </div>
            {data.sector_drivers.length > 0 ? (
              <ul className="space-y-1">
                {data.sector_drivers.map((d, i) => (
                  <li key={i} className="text-[12px] text-text-secondary leading-snug">· {d}</li>
                ))}
              </ul>
            ) : (
              <p className="text-[12px] text-text-muted italic">
                {data.sector
                  ? `No active regime factor especially affects ${data.sector}.`
                  : "Sector unknown — falling back to macro-only verdict."}
              </p>
            )}
            {data.sector_note && (
              <p className="text-[10px] text-text-muted italic mt-2 pt-2 border-t border-bg-divider">
                {data.sector_note}
              </p>
            )}
          </div>
        </div>

        {/* Snapshot of underlying numbers */}
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 pt-3 border-t border-bg-border">
          {[
            { label: "Fed funds",   v: fmtPct(s.fed_funds_rate) },
            { label: "10Y",         v: fmtPct(s.treasury_10y) },
            { label: "2Y",          v: fmtPct(s.treasury_2y) },
            { label: "VIX",         v: s.vix != null ? s.vix.toFixed(1) : "—" },
            { label: "Unemploy.",   v: fmtPct(s.unemployment) },
            { label: "GDP",         v: fmtPct(s.gdp_growth) },
          ].map(({ label, v }) => (
            <div key={label} className="text-center">
              <div className="text-[9px] uppercase tracking-wider text-text-muted">{label}</div>
              <div className="font-numeric text-xs font-semibold tabular-nums">{v}</div>
            </div>
          ))}
        </div>

        <p className="text-[10px] text-text-muted mt-4 pt-3 border-t border-bg-border">
          Macro score from yield curve, VIX, Fed rate, jobs, GDP. Sector tilt uses
          historical sector behavior under each regime factor. Combined verdict
          tells you whether the wind is at this stock's back or in its face.
        </p>
      </div>
    </section>
  );
}
