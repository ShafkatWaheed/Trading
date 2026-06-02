"use client";

import { useQuery } from "@tanstack/react-query";
import { TrendingUp, TrendingDown, Megaphone, Sparkles, AlertCircle, Target } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import type { RatingAction } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

function actionTone(a: string): { color: string; bg: string; Icon: typeof TrendingUp; label: string } {
  if (a === "upgrade")    return { color: "text-accent-greenSoft", bg: "bg-accent-green/10 border-accent-green/30", Icon: TrendingUp, label: "Upgrade" };
  if (a === "downgrade")  return { color: "text-accent-redSoft",   bg: "bg-accent-red/10 border-accent-red/30",     Icon: TrendingDown, label: "Downgrade" };
  if (a === "initiation") return { color: "text-accent-violet",    bg: "bg-accent-violet/10 border-accent-violet/30", Icon: Sparkles, label: "New coverage" };
  return                       { color: "text-text-secondary",     bg: "bg-bg-card2 border-bg-borderHi",            Icon: Megaphone, label: "Reiteration" };
}

function consensusColor(c: string | null): string {
  if (!c) return "text-text-muted";
  if (c.includes("Strong Buy")) return "text-accent-greenSoft";
  if (c === "Buy")              return "text-accent-greenSoft";
  if (c === "Hold")             return "text-text-secondary";
  if (c === "Sell")             return "text-accent-redSoft";
  if (c.includes("Strong Sell"))return "text-accent-redSoft";
  return "text-text-muted";
}

export function EstimateRevisionsCard({ symbol }: Props) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["estimate-revisions", symbol],
    queryFn: () => stocksApi.estimateRevisions(symbol),
    staleTime: 12 * 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <Megaphone size={16} className="text-accent-blue" />
          <h3 className="text-base font-semibold">Analyst Revisions</h3>
        </div>
        <Skeleton className="h-40 w-full" />
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <Megaphone size={16} className="text-accent-blue" />
          <h3 className="text-base font-semibold">Analyst Revisions</h3>
        </div>
        <p className="text-text-muted text-sm">{(error as Error)?.message || "Unavailable."}</p>
      </section>
    );
  }

  if (!data.available) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <Megaphone size={16} className="text-accent-blue" />
          <h3 className="text-base font-semibold">Analyst Revisions</h3>
        </div>
        <div className="flex items-start gap-2 p-3 rounded-md border border-bg-borderHi bg-bg-base/40">
          <AlertCircle size={14} className="text-text-muted mt-0.5 shrink-0" />
          <p className="text-[12px] text-text-secondary leading-relaxed">{data.reason}</p>
        </div>
      </section>
    );
  }

  const net = data.net_change_30d;
  const netTone = net > 0 ? "text-accent-greenSoft" : net < 0 ? "text-accent-redSoft" : "text-text-muted";

  return (
    <section className="card-subtle p-6 overflow-hidden relative">
      <div
        className="absolute inset-x-0 top-0 h-32 pointer-events-none opacity-50"
        style={{
          background: "radial-gradient(ellipse 60% 100% at 50% 0%, rgba(59, 130, 246, 0.10) 0%, transparent 70%)",
        }}
      />

      <div className="relative">
        <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Megaphone size={16} className="text-accent-blue" />
            <h3 className="text-base font-semibold">Analyst Revisions</h3>
            {data.from_cache && (
              <span className="text-[10px] uppercase tracking-wider text-text-muted">cached</span>
            )}
          </div>
          {data.consensus && (
            <span className={cn(
              "badge text-[10px] uppercase tracking-wider font-semibold",
              "bg-bg-card2 border-bg-borderHi",
              consensusColor(data.consensus),
            )}>
              Consensus · {data.consensus}
            </span>
          )}
        </div>

        {data.lede && (
          <p className="text-text-primary text-[15px] leading-relaxed italic mb-5 max-w-3xl">
            “{data.lede}”
          </p>
        )}

        {data.consensus_shift && (
          <p className="text-[12px] text-accent-amber mb-4">
            <Sparkles size={11} className="inline mr-1" />
            {data.consensus_shift}
          </p>
        )}

        {/* 30-day action tally */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-5">
          <div className="rounded-md border border-bg-border bg-bg-base/30 p-2.5">
            <div className="text-[9px] uppercase tracking-wider text-text-muted">Upgrades · 30d</div>
            <div className="font-numeric text-xl font-bold text-accent-greenSoft tabular-nums">
              {data.upgrades_30d}
            </div>
          </div>
          <div className="rounded-md border border-bg-border bg-bg-base/30 p-2.5">
            <div className="text-[9px] uppercase tracking-wider text-text-muted">Downgrades · 30d</div>
            <div className="font-numeric text-xl font-bold text-accent-redSoft tabular-nums">
              {data.downgrades_30d}
            </div>
          </div>
          <div className="rounded-md border border-bg-border bg-bg-base/30 p-2.5">
            <div className="text-[9px] uppercase tracking-wider text-text-muted">New coverage</div>
            <div className="font-numeric text-xl font-bold text-accent-violet tabular-nums">
              {data.initiations_30d}
            </div>
          </div>
          <div className="rounded-md border border-bg-border bg-bg-base/30 p-2.5">
            <div className="text-[9px] uppercase tracking-wider text-text-muted">Net change</div>
            <div className={cn("font-numeric text-xl font-bold tabular-nums", netTone)}>
              {net > 0 ? "+" : ""}{net}
            </div>
          </div>
        </div>

        {/* Price targets (Yahoo Finance) */}
        {data.price_targets && data.price_targets.mean != null && (
          <div className="rounded-md border border-bg-border bg-bg-base/30 p-3 mb-4">
            <div className="flex items-baseline justify-between gap-2 mb-2">
              <div className="text-[10px] uppercase tracking-wider font-semibold text-text-muted flex items-center gap-1.5">
                <Target size={11} className="text-accent-blue" />
                12-month price targets
              </div>
              {data.analyst_count != null && (
                <div className="text-[10px] text-text-muted tabular-nums">
                  {data.analyst_count} analysts
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div>
                <div className="text-[9px] uppercase tracking-wider text-text-muted">Mean</div>
                <div className="font-numeric text-lg font-bold tabular-nums text-text-primary">
                  ${data.price_targets.mean.toFixed(2)}
                </div>
              </div>
              {data.price_targets.median != null && (
                <div>
                  <div className="text-[9px] uppercase tracking-wider text-text-muted">Median</div>
                  <div className="font-numeric text-lg font-bold tabular-nums text-text-secondary">
                    ${data.price_targets.median.toFixed(2)}
                  </div>
                </div>
              )}
              {data.price_targets.high != null && (
                <div>
                  <div className="text-[9px] uppercase tracking-wider text-text-muted">High</div>
                  <div className="font-numeric text-sm tabular-nums text-accent-greenSoft">
                    ${data.price_targets.high.toFixed(2)}
                  </div>
                </div>
              )}
              {data.price_targets.low != null && (
                <div>
                  <div className="text-[9px] uppercase tracking-wider text-text-muted">Low</div>
                  <div className="font-numeric text-sm tabular-nums text-accent-redSoft">
                    ${data.price_targets.low.toFixed(2)}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* EPS trend */}
        {data.eps_trend && (
          <div className="rounded-md border border-bg-border bg-bg-base/30 p-3 mb-4">
            <div className="text-[10px] uppercase tracking-wider font-semibold text-text-muted mb-2">
              Forward EPS · {data.eps_trend.next_period ?? "next quarter"}
            </div>
            <div className="flex items-baseline gap-4 flex-wrap">
              <div>
                <div className="text-[9px] uppercase tracking-wider text-text-muted">Avg estimate</div>
                <div className="font-numeric text-lg font-bold tabular-nums">
                  {data.eps_trend.next_eps_avg != null ? `$${data.eps_trend.next_eps_avg.toFixed(2)}` : "—"}
                </div>
              </div>
              <div>
                <div className="text-[9px] uppercase tracking-wider text-text-muted">Range</div>
                <div className="font-numeric text-sm tabular-nums">
                  {data.eps_trend.next_eps_low != null && data.eps_trend.next_eps_high != null
                    ? `$${data.eps_trend.next_eps_low.toFixed(2)} – $${data.eps_trend.next_eps_high.toFixed(2)}`
                    : "—"}
                </div>
              </div>
              <div>
                <div className="text-[9px] uppercase tracking-wider text-text-muted">Analysts</div>
                <div className="font-numeric text-sm tabular-nums">{data.eps_trend.analyst_count ?? "—"}</div>
              </div>
              {data.eps_trend.growth_pct != null && (
                <div className="ml-auto">
                  <div className="text-[9px] uppercase tracking-wider text-text-muted">FY growth path</div>
                  <div className={cn(
                    "font-numeric text-sm font-semibold tabular-nums",
                    data.eps_trend.growth_pct > 0 ? "text-accent-greenSoft" : "text-accent-redSoft",
                  )}>
                    {data.eps_trend.growth_pct > 0 ? "+" : ""}{data.eps_trend.growth_pct.toFixed(1)}%
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Recent actions feed */}
        {data.recent_actions.length > 0 ? (
          <div>
            <div className="text-[10px] uppercase tracking-wider font-semibold text-text-muted mb-2">
              Recent rating actions
            </div>
            <ul className="space-y-1.5">
              {data.recent_actions.map((a: RatingAction, i: number) => {
                const t = actionTone(a.action);
                const Icon = t.Icon;
                return (
                  <li key={i} className="flex items-start gap-2 p-2 rounded-md border border-bg-divider bg-bg-base/20">
                    <span className={cn("badge text-[9px] py-0 inline-flex items-center gap-1 shrink-0", t.bg, t.color)}>
                      <Icon size={9} />
                      {t.label}
                    </span>
                    <div className="flex-1 min-w-0 text-[12px]">
                      <span className="font-semibold text-text-primary">{a.firm || "—"}</span>
                      {a.from_grade && a.to_grade && (
                        <span className="text-text-muted ml-2">
                          {a.from_grade} → <span className="text-text-secondary">{a.to_grade}</span>
                        </span>
                      )}
                      {!a.from_grade && a.to_grade && (
                        <span className="text-text-muted ml-2">@ {a.to_grade}</span>
                      )}
                    </div>
                    <span className="text-[10px] text-text-muted shrink-0">{a.date}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : (
          <p className="text-[12px] text-text-muted italic">
            No analyst rating actions in the last 30 days for {symbol}.
          </p>
        )}

        <p className="text-[10px] text-text-muted mt-4 pt-3 border-t border-bg-border">
          Direction of estimate revisions is one of the strongest near-term price
          predictors (PEAD).
          {data.source && (
            <> Source: <span className="text-text-secondary">{data.source}</span>.</>
          )}
          {" "}EPS estimates are quarterly averages from covering analysts.
        </p>
      </div>
    </section>
  );
}
