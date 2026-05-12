"use client";

import { useQuery } from "@tanstack/react-query";
import { Layers } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import type { PeerValuationRow } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

function richness(value: number | null | undefined, median: number | null | undefined): "rich" | "cheap" | "fair" | "na" {
  if (value == null || median == null) return "na";
  if (median <= 0) return "na";
  const ratio = value / median;
  if (ratio >= 1.25) return "rich";
  if (ratio <= 0.8)  return "cheap";
  return "fair";
}

function valColor(r: ReturnType<typeof richness>): string {
  switch (r) {
    case "rich":  return "text-accent-amber";
    case "cheap": return "text-accent-greenSoft";
    case "fair":  return "text-text-primary";
    default:      return "text-text-muted";
  }
}

function fmt(v: number | null | undefined, suffix = ""): string {
  if (v == null) return "—";
  return `${v.toFixed(1)}${suffix}`;
}

function MetricCell({ label, value, median }: {
  label: string; value: number | null | undefined; median: number | null | undefined;
}) {
  return (
    <td className="px-3 py-2 text-right tabular-nums">
      <div className={cn("text-sm font-semibold", valColor(richness(value, median)))}>
        {fmt(value, label === "1Y" ? "%" : "")}
      </div>
    </td>
  );
}

export function PeerValuationStrip({ symbol }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["peer-valuation", symbol],
    queryFn: () => stocksApi.peerValuation(symbol),
    staleTime: 6 * 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <Layers size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">Peer Valuation</h3>
        </div>
        <Skeleton className="h-40 w-full" />
      </section>
    );
  }

  if (isError || !data) {
    return null;
  }

  const rows = data.rows || [];
  const m = data.medians || {};

  if (rows.length <= 1) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <Layers size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">Peer Valuation</h3>
        </div>
        <p className="text-text-muted text-sm">No peer data available for {symbol} yet.</p>
      </section>
    );
  }

  return (
    <section className="card-subtle p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Layers size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">Peer Valuation</h3>
          <span className="text-[10px] uppercase tracking-wider text-text-muted">
            vs {rows.length - 1} peer{rows.length - 1 === 1 ? "" : "s"}
          </span>
          {data.from_cache && (
            <span className="text-[10px] uppercase tracking-wider text-text-dim">cached</span>
          )}
        </div>
      </div>

      <div className="overflow-x-auto -mx-2">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text-muted text-left uppercase tracking-wider border-b border-bg-border">
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2 text-right">P/E</th>
              <th className="px-3 py-2 text-right">P/S</th>
              <th className="px-3 py-2 text-right">P/FCF</th>
              <th className="px-3 py-2 text-right">1Y</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r: PeerValuationRow) => (
              <tr
                key={r.symbol}
                className={cn(
                  "border-b border-bg-divider",
                  r.is_self ? "bg-accent-violet/5" : ""
                )}
              >
                <td className="px-3 py-2 font-mono font-bold">
                  <span className={r.is_self ? "text-accent-violet" : "text-text-primary"}>
                    {r.symbol}
                  </span>
                  {r.is_self && (
                    <span className="ml-2 text-[9px] uppercase tracking-wider text-accent-violet">this stock</span>
                  )}
                </td>
                <MetricCell label="P/E"   value={r.pe_ratio}            median={m.pe_ratio} />
                <MetricCell label="P/S"   value={r.ps_ratio}            median={m.ps_ratio} />
                <MetricCell label="P/FCF" value={r.pfcf_ratio}          median={m.pfcf_ratio} />
                <MetricCell label="1Y"    value={r.price_change_1y_pct} median={m.price_change_1y_pct} />
              </tr>
            ))}
            <tr className="bg-bg-base">
              <td className="px-3 py-2 font-mono text-text-muted text-[11px]">peer median</td>
              <td className="px-3 py-2 text-right tabular-nums text-text-muted">{fmt(m.pe_ratio)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-text-muted">{fmt(m.ps_ratio)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-text-muted">{fmt(m.pfcf_ratio)}</td>
              <td className="px-3 py-2 text-right tabular-nums text-text-muted">{fmt(m.price_change_1y_pct, "%")}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-3 mt-4 pt-3 border-t border-bg-border text-[10px] text-text-muted">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-accent-amber" /> ≥25% above median (rich)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-accent-greenSoft" /> ≥20% below (cheap)
        </span>
        <span className="ml-auto">Lower P/E, P/S, P/FCF = cheaper relative to peers</span>
      </div>
    </section>
  );
}
