"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { marketApi } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";

type Props = {
  showAfterPx?: number;
};

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

export function StickyMarketBar({ showAfterPx = 320 }: Props) {
  const [visible, setVisible] = useState(false);
  const { data } = useQuery({
    queryKey: ["market-dashboard"],
    queryFn: () => marketApi.dashboard(),
    staleTime: 2 * 60 * 1000,
    refetchInterval: 2 * 60 * 1000,
  });

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > showAfterPx);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [showAfterPx]);

  if (!data) return null;

  const indices = data.indices || [];
  const status = data.status;
  const countdown = status.status === "open"
    ? fmtCountdown(status.minutes_to_close)
    : fmtCountdown(status.minutes_to_open);

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
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-11 flex items-center gap-4 sm:gap-6 text-[12px] overflow-x-auto">
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={cn("w-1.5 h-1.5 rounded-full", statusDot(status.status))} />
          <span className={cn("uppercase tracking-wider font-semibold text-[10px]", statusColor(status.status))}>
            {status.label}
          </span>
          {countdown && (
            <span className="text-[10px] text-text-muted">
              {status.status === "open" ? "closes in " : "opens in "}{countdown}
            </span>
          )}
        </div>

        <span className="hidden sm:inline-block w-px h-4 bg-bg-borderHi" />

        {indices.slice(0, 5).map((i) => (
          <div key={i.key} className="flex items-baseline gap-1.5 shrink-0 tabular-nums">
            <span className="text-text-muted text-[10px] uppercase tracking-wider">{i.display}</span>
            <span className="text-text-primary font-semibold">
              {i.price != null ? i.price.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
            </span>
            {i.change_pct != null && (
              <span className={cn("font-medium", priceColor(i.change_pct))}>
                {i.change_pct >= 0 ? "+" : ""}{i.change_pct.toFixed(2)}%
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
