"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Network, Users, ArrowRight, Building2 } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

function fmtUsd(v: number | null | undefined): string {
  if (v == null || v <= 0) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6)  return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3)  return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

function institutionTypeLabel(type: string | null | undefined): string {
  if (!type) return "fund";
  return type.replace(/_/g, " ");
}

export function CoHoldersCard({ symbol }: Props) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["co-holders", symbol],
    queryFn: () => stocksApi.coHolders(symbol),
    staleTime: 6 * 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <Network size={16} className="text-accent-cyan" />
          <h3 className="text-base font-semibold">Who Else Owns This</h3>
        </div>
        <Skeleton className="h-64 w-full" />
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <Network size={16} className="text-accent-cyan" />
          <h3 className="text-base font-semibold">Who Else Owns This</h3>
        </div>
        <p className="text-text-muted text-sm">
          {(error as Error)?.message || "Holder data unavailable."}
        </p>
      </section>
    );
  }

  if (!data.available || data.holders.length === 0) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <Network size={16} className="text-accent-cyan" />
          <h3 className="text-base font-semibold">Who Else Owns This</h3>
        </div>
        <p className="text-text-muted text-sm">{data.lede}</p>
      </section>
    );
  }

  // Max co_holder_count is used to scale the overlap bars
  const maxOverlap = Math.max(1, ...data.co_held.map((c) => c.co_holder_count));

  return (
    <section className="card-subtle p-6 overflow-hidden relative">
      <div
        className="absolute inset-x-0 top-0 h-32 pointer-events-none opacity-60"
        style={{
          background:
            "radial-gradient(ellipse 70% 100% at 70% 0%, rgba(6, 182, 212, 0.10) 0%, transparent 70%)",
        }}
      />

      <div className="relative">
        <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Network size={16} className="text-accent-cyan" />
            <h3 className="text-base font-semibold">Who Else Owns This</h3>
            {data.from_cache && (
              <span className="text-[10px] uppercase tracking-wider text-text-muted">cached</span>
            )}
          </div>
          <span className="badge text-[10px] bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30">
            <Users size={10} className="mr-1" />
            {data.total_holders} institution{data.total_holders === 1 ? "" : "s"}
          </span>
        </div>

        {/* The opening line — synthesized story */}
        <p className="text-text-primary text-[15px] leading-relaxed italic mb-6 max-w-3xl">
          “{data.lede}”
        </p>

        {/* Two-column composition: holders on the left, the shared thesis on the right */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
          {/* ── Who holds it ────────────────────────────────────────── */}
          <div className="lg:col-span-3">
            <div className="text-[10px] uppercase tracking-wider font-semibold text-text-muted mb-3 flex items-center gap-2">
              <Building2 size={11} />
              The institutions
              <span className="h-px flex-1 bg-bg-border" />
            </div>
            <ul className="space-y-2.5">
              {data.holders.slice(0, 8).map((h) => (
                <li
                  key={h.cik}
                  className="rounded-md border border-bg-border bg-bg-base/40 p-3 hover:border-accent-cyan/30 transition-colors"
                >
                  <div className="flex items-baseline justify-between gap-2 flex-wrap mb-1.5">
                    <div className="flex items-baseline gap-2 flex-wrap min-w-0">
                      <span className="font-semibold text-text-primary text-sm truncate">
                        {h.name || "Unknown"}
                      </span>
                      <span className="text-[10px] uppercase tracking-wider text-text-muted">
                        {institutionTypeLabel(h.type)}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-[11px] font-numeric tabular-nums shrink-0">
                      {h.pct_outstanding != null && (
                        <span className="text-accent-cyan font-semibold">
                          {h.pct_outstanding.toFixed(2)}%
                          <span className="text-text-muted font-normal ml-1">of float</span>
                        </span>
                      )}
                      <span className="text-text-secondary">{fmtUsd(h.value_usd)}</span>
                    </div>
                  </div>

                  {/* "Also holds" chip strip — the interconnection part */}
                  {h.also_holds.length > 0 && (
                    <div className="flex items-center gap-2 flex-wrap mt-2 pt-2 border-t border-bg-divider">
                      <span className="text-[9px] uppercase tracking-wider text-text-muted shrink-0">
                        also holds
                      </span>
                      {h.also_holds.map((o) => (
                        <Link
                          key={o.symbol}
                          href={`/deep-dive/${encodeURIComponent(o.symbol)}`}
                          className="inline-flex items-baseline gap-1 px-2 py-0.5 rounded
                                     bg-bg-card2 hover:bg-accent-cyan/10
                                     border border-bg-borderHi hover:border-accent-cyan/40
                                     text-[11px] font-mono font-semibold transition-colors"
                        >
                          <span className="text-text-primary">{o.symbol}</span>
                          {o.pct_portfolio != null && (
                            <span className="text-text-muted text-[9px]">
                              {o.pct_portfolio.toFixed(1)}%
                            </span>
                          )}
                        </Link>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>

          {/* ── The shared thesis ───────────────────────────────────── */}
          <div className="lg:col-span-2">
            <div className="text-[10px] uppercase tracking-wider font-semibold text-text-muted mb-3 flex items-center gap-2">
              <ArrowRight size={11} />
              Their shared thesis
              <span className="h-px flex-1 bg-bg-border" />
            </div>

            {data.co_held.length === 0 ? (
              <p className="text-text-muted text-sm italic">
                No overlap — these institutions diverge after {symbol}.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {data.co_held.slice(0, 10).map((c, idx) => {
                  const pct = (c.co_holder_count / maxOverlap) * 100;
                  const rankColor =
                    idx === 0
                      ? "text-accent-amber"
                      : idx <= 2
                        ? "text-accent-cyan"
                        : "text-text-secondary";
                  return (
                    <li key={c.symbol} className="group">
                      <Link
                        href={`/deep-dive/${encodeURIComponent(c.symbol)}`}
                        className="block rounded-md border border-bg-border hover:border-accent-cyan/40 bg-bg-base/30 p-2.5 transition-colors"
                      >
                        <div className="flex items-baseline justify-between gap-2 mb-1">
                          <div className="flex items-baseline gap-2 min-w-0">
                            <span className={cn("font-mono font-bold text-sm", rankColor)}>
                              {c.symbol}
                            </span>
                            {c.stock_name && (
                              <span className="text-[11px] text-text-muted truncate">
                                {c.stock_name}
                              </span>
                            )}
                          </div>
                          <span className="text-[11px] font-numeric tabular-nums text-text-secondary shrink-0">
                            {c.co_holder_count} of {data.total_holders} also hold
                          </span>
                        </div>
                        <div className="h-1 rounded-full bg-bg-border overflow-hidden">
                          <div
                            className={cn(
                              "h-full transition-all",
                              idx === 0
                                ? "bg-accent-amber"
                                : idx <= 2
                                  ? "bg-accent-cyan"
                                  : "bg-accent-cyan/60"
                            )}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        <p className="text-[10px] text-text-muted mt-5 pt-3 border-t border-bg-border">
          Source: institutional 13F holdings. The “also holds” chips reveal what each fund
          buys alongside {symbol} — when the same names recur, you're seeing a thesis.
          Click any ticker to jump to its Deep Dive.
        </p>
      </div>
    </section>
  );
}
