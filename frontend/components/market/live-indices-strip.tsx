"use client";

import { useQuery } from "@tanstack/react-query";
import { marketApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { Sparkline } from "@/components/market/sparkline";
import { cn } from "@/lib/utils";

function fmtCountdown(mins: number | null | undefined): string {
  if (mins == null || mins <= 0) return "";
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h <= 0) return `${m}m`;
  return `${h}h ${m}m`;
}

function statusColor(s: string): string {
  if (s === "open")        return "text-accent-greenSoft";
  if (s === "pre_market" || s === "after_hours") return "text-accent-amber";
  return "text-text-muted";
}

function statusDot(s: string): string {
  if (s === "open")        return "bg-accent-green animate-pulse";
  if (s === "pre_market" || s === "after_hours") return "bg-accent-amber";
  return "bg-text-dim";
}

function priceColor(pct: number | null | undefined): string {
  if (pct == null) return "text-text-muted";
  return pct >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft";
}

export function LiveIndicesStrip() {
  const { data, isLoading } = useQuery({
    queryKey: ["market-dashboard"],
    queryFn: () => marketApi.dashboard(),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });

  if (isLoading) {
    return <Skeleton className="h-20 w-full" />;
  }
  if (!data) return null;

  const status = data.status;
  const countdown = status.status === "open"
    ? fmtCountdown(status.minutes_to_close)
    : fmtCountdown(status.minutes_to_open);

  return (
    <section className="card p-4 flex items-center gap-x-6 gap-y-3 flex-wrap">
      <div className="flex items-center gap-2 shrink-0">
        <span className={cn("w-2 h-2 rounded-full", statusDot(status.status))} />
        <span className={cn("uppercase tracking-wider font-semibold text-[11px]", statusColor(status.status))}>
          {status.label}
        </span>
        {countdown && (
          <span className="text-[10px] text-text-muted">
            {status.status === "open" ? "closes in " : "opens in "}{countdown}
          </span>
        )}
      </div>

      <span className="hidden sm:inline-block w-px h-6 bg-bg-borderHi" />

      <div className="flex items-center gap-4 sm:gap-6 flex-wrap text-sm">
        {(data.indices || []).map((i) => (
          <div key={i.key} className="flex items-center gap-2.5 tabular-nums">
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] uppercase tracking-wider text-text-muted">{i.display}</span>
              <div className="flex items-baseline gap-1.5">
                <span className="text-text-primary font-semibold">
                  {i.price != null ? i.price.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
                </span>
                {i.change_pct != null && (
                  <span className={cn("text-[11px] font-medium", priceColor(i.change_pct))}>
                    {i.change_pct >= 0 ? "+" : ""}{i.change_pct.toFixed(2)}%
                  </span>
                )}
              </div>
            </div>
            {i.spark && i.spark.length >= 2 && (
              <div
                className="flex flex-col items-end"
                title={
                  i.change_30d_pct != null
                    ? `30-day trend: ${i.change_30d_pct >= 0 ? "+" : ""}${i.change_30d_pct.toFixed(1)}%`
                    : "30-day trend"
                }
              >
                <Sparkline points={i.spark} width={56} height={20} />
                {i.change_30d_pct != null && (
                  <span className={cn("text-[10px] tabular-nums", priceColor(i.change_30d_pct))}>
                    30d {i.change_30d_pct >= 0 ? "+" : ""}{i.change_30d_pct.toFixed(1)}%
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
