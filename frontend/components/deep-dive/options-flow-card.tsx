"use client";

import { useQuery } from "@tanstack/react-query";
import { Sigma, TrendingUp, TrendingDown, Activity, AlertCircle } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

function signalTone(signal: string): { color: string; bg: string; Icon: typeof TrendingUp } {
  if (signal === "bullish") return { color: "text-accent-greenSoft", bg: "bg-accent-green/10 border-accent-green/30", Icon: TrendingUp };
  if (signal === "bearish") return { color: "text-accent-redSoft", bg: "bg-accent-red/10 border-accent-red/30", Icon: TrendingDown };
  return { color: "text-text-secondary", bg: "bg-bg-card2 border-bg-borderHi", Icon: Activity };
}

function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v == null) return "—";
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toFixed(digits);
}

export function OptionsFlowCard({ symbol }: Props) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["options-flow", symbol],
    queryFn: () => stocksApi.optionsFlow(symbol),
    staleTime: 30 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <Sigma size={16} className="text-accent-amber" />
          <h3 className="text-base font-semibold">Options Flow</h3>
        </div>
        <Skeleton className="h-40 w-full" />
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <Sigma size={16} className="text-accent-amber" />
          <h3 className="text-base font-semibold">Options Flow</h3>
        </div>
        <p className="text-text-muted text-sm">{(error as Error)?.message || "Options flow unavailable."}</p>
      </section>
    );
  }

  if (!data.available) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <Sigma size={16} className="text-accent-amber" />
          <h3 className="text-base font-semibold">Options Flow</h3>
        </div>
        <div className="flex items-start gap-2 p-3 rounded-md border border-bg-borderHi bg-bg-base/40">
          <AlertCircle size={14} className="text-text-muted mt-0.5 shrink-0" />
          <p className="text-[12px] text-text-secondary leading-relaxed">
            {data.reason || "Options data is not configured."} Set a paid Polygon
            API key to enable this card (free tier doesn't include options snapshots).
          </p>
        </div>
      </section>
    );
  }

  const tone = signalTone(data.signal);
  const ToneIcon = tone.Icon;
  const callRatio = data.put_call_ratio != null && data.put_call_ratio > 0
    ? 1 / (1 + data.put_call_ratio) : 0.5;

  return (
    <section className="card-subtle p-6 overflow-hidden relative">
      <div
        className="absolute inset-x-0 top-0 h-32 pointer-events-none opacity-50"
        style={{
          background:
            "radial-gradient(ellipse 60% 100% at 50% 0%, rgba(245, 158, 11, 0.08) 0%, transparent 70%)",
        }}
      />

      <div className="relative">
        <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Sigma size={16} className="text-accent-amber" />
            <h3 className="text-base font-semibold">Options Flow</h3>
            {data.data_source && (
              <span
                className={cn(
                  "text-[10px] uppercase tracking-wider font-mono",
                  data.data_source === "polygon" ? "text-accent-violet" : "text-text-muted",
                )}
                title={
                  data.data_source === "polygon"
                    ? "Sourced from Polygon — includes IV rank + unusual flow"
                    : "Sourced from yfinance (free) — IV rank unavailable on this source"
                }
              >
                via {data.data_source}
              </span>
            )}
            {data.from_cache && (
              <span className="text-[10px] uppercase tracking-wider text-text-muted">cached</span>
            )}
          </div>
          <span className={cn("badge text-[10px] uppercase tracking-wider font-semibold inline-flex items-center gap-1", tone.bg, tone.color)}>
            <ToneIcon size={10} />
            {data.signal}
          </span>
        </div>

        {data.lede && (
          <p className="text-text-primary text-[15px] leading-relaxed italic mb-5 max-w-3xl">
            “{data.lede}”
          </p>
        )}

        {/* P/C ratio visualization — split bar */}
        <div className="mb-5">
          <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-text-muted mb-1.5">
            <span>Calls {fmtNum(data.total_call_volume)}</span>
            <span>Put / Call · {data.put_call_ratio?.toFixed(2) ?? "—"}</span>
            <span>Puts {fmtNum(data.total_put_volume)}</span>
          </div>
          <div className="h-2 rounded-full bg-bg-border overflow-hidden flex">
            <div className="bg-accent-greenSoft h-full" style={{ width: `${callRatio * 100}%` }} />
            <div className="bg-accent-redSoft h-full flex-1" />
          </div>
        </div>

        {/* Key metrics grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-5">
          <div className="rounded-md border border-bg-border bg-bg-base/30 p-2.5">
            <div className="text-[9px] uppercase tracking-wider text-text-muted">P/C ratio</div>
            <div className="font-numeric text-base font-semibold tabular-nums">
              {data.put_call_ratio?.toFixed(2) ?? "—"}
            </div>
          </div>
          <div className="rounded-md border border-bg-border bg-bg-base/30 p-2.5">
            <div className="text-[9px] uppercase tracking-wider text-text-muted">
              {data.iv_rank != null ? "IV rank" : "Avg IV"}
            </div>
            <div className={cn(
              "font-numeric text-base font-semibold tabular-nums",
              // IV-rank coloring (relative percentile)
              data.iv_rank != null && data.iv_rank > 80 ? "text-accent-amber"
                : data.iv_rank != null && data.iv_rank < 20 ? "text-accent-greenSoft"
                // Absolute IV coloring (rough thresholds — >50% rich, <20% cheap)
                : data.iv_rank == null && data.iv_avg_pct != null && data.iv_avg_pct > 50 ? "text-accent-amber"
                : data.iv_rank == null && data.iv_avg_pct != null && data.iv_avg_pct < 20 ? "text-accent-greenSoft"
                : "text-text-primary",
            )}>
              {data.iv_rank != null
                ? `${data.iv_rank.toFixed(0)}%`
                : data.iv_avg_pct != null
                  ? `${data.iv_avg_pct.toFixed(0)}%`
                  : "—"}
            </div>
          </div>
          <div className="rounded-md border border-bg-border bg-bg-base/30 p-2.5">
            <div className="text-[9px] uppercase tracking-wider text-text-muted">Max pain</div>
            <div className="font-numeric text-base font-semibold tabular-nums">
              {data.max_pain != null ? `$${data.max_pain.toFixed(0)}` : "—"}
            </div>
          </div>
          <div className="rounded-md border border-bg-border bg-bg-base/30 p-2.5">
            <div className="text-[9px] uppercase tracking-wider text-text-muted">Spot</div>
            <div className="font-numeric text-base font-semibold tabular-nums">
              {data.underlying_price != null ? `$${data.underlying_price.toFixed(2)}` : "—"}
            </div>
          </div>
        </div>

        {/* Factors */}
        {data.factors.length > 0 && (
          <ul className="space-y-1 mb-4">
            {data.factors.map((f, i) => (
              <li key={i} className="text-[12px] text-text-secondary leading-snug">· {f}</li>
            ))}
          </ul>
        )}

        {/* Unusual activity */}
        {data.unusual_top.length > 0 && (
          <div className="pt-3 border-t border-bg-border">
            <div className="text-[10px] uppercase tracking-wider font-semibold text-text-muted mb-2">
              Unusual activity · {data.unusual_top.length}
            </div>
            <div className="overflow-x-auto -mx-2">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-text-muted text-left uppercase tracking-wider border-b border-bg-border">
                    <th className="px-3 py-1.5"></th>
                    <th className="px-3 py-1.5">Strike / Exp</th>
                    <th className="px-3 py-1.5 text-right">Vol</th>
                    <th className="px-3 py-1.5 text-right">OI</th>
                    <th className="px-3 py-1.5 text-right">V/OI</th>
                    <th className="px-3 py-1.5 text-right">Premium</th>
                  </tr>
                </thead>
                <tbody>
                  {data.unusual_top.map((u, i) => {
                    const isCall = u.contract_type?.toLowerCase().includes("call");
                    return (
                      <tr key={i} className="border-b border-bg-divider">
                        <td className="px-3 py-1.5">
                          <span className={cn(
                            "badge text-[9px] py-0",
                            isCall ? "bg-accent-green/10 text-accent-greenSoft border-accent-green/30"
                                   : "bg-accent-red/10 text-accent-redSoft border-accent-red/30",
                          )}>
                            {isCall ? "C" : "P"}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 font-mono">
                          {u.strike != null ? `$${u.strike}` : "—"}
                          <span className="text-text-muted ml-1">{u.expiration}</span>
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{fmtNum(u.volume)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-text-muted">{fmtNum(u.open_interest)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums font-semibold">
                          {u.volume_oi_ratio?.toFixed(1) ?? "—"}×
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums">${fmtNum(u.premium)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <p className="text-[10px] text-text-muted mt-4 pt-3 border-t border-bg-border">
          P/C ratio &lt; 0.7 bullish, &gt; 1.0 bearish. IV rank above 80% = options
          expensive (high fear); below 20% = cheap (complacency). Unusual = volume far
          above open interest, often informed positioning.
        </p>
      </div>
    </section>
  );
}
