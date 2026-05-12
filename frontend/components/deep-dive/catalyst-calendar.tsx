"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Banknote, TrendingUp, Globe2 } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { CatalystEvent } from "@/lib/api/types";

type Props = { symbol: string };

const KIND_TONE: Record<string, { color: string; bg: string; Icon: typeof CalendarDays; label: string }> = {
  earnings: { color: "text-accent-violet",     bg: "bg-accent-violet/10 border-accent-violet/40", Icon: TrendingUp,   label: "Earnings" },
  dividend: { color: "text-accent-greenSoft",  bg: "bg-accent-green/10  border-accent-green/40",  Icon: Banknote,     label: "Dividend" },
  macro:    { color: "text-accent-blue",       bg: "bg-accent-blue/10   border-accent-blue/40",   Icon: Globe2,       label: "Macro" },
  split:    { color: "text-accent-cyan",       bg: "bg-accent-cyan/10   border-accent-cyan/40",   Icon: CalendarDays, label: "Split" },
};

const WEIGHT_TONE: Record<string, string> = {
  very_high: "text-accent-redSoft",
  high:      "text-accent-amber",
  med:       "text-text-secondary",
  low:       "text-text-muted",
};

function dayLabel(daysOut: number): string {
  if (daysOut === 0) return "today";
  if (daysOut === 1) return "tomorrow";
  return `in ${daysOut}d`;
}

export function CatalystCalendar({ symbol }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["catalyst-calendar", symbol],
    queryFn: () => stocksApi.catalystCalendar(symbol),
    staleTime: 6 * 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <CalendarDays size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">30-Day Catalyst Calendar</h3>
        </div>
        <Skeleton className="h-32 w-full" />
      </section>
    );
  }

  if (isError || !data) return null;
  const events = data.events || [];

  return (
    <section className="card-subtle p-6">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <CalendarDays size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">30-Day Catalyst Calendar</h3>
          {data.from_cache && (
            <span className="text-[10px] uppercase tracking-wider text-text-muted">cached</span>
          )}
        </div>
        <div className="flex items-center gap-3 text-[10px] uppercase tracking-wider text-text-muted">
          <span>{data.earnings_count} earnings</span>
          <span>·</span>
          <span>{data.macro_count} macro</span>
          <span>·</span>
          <span>{data.dividend_count} dividend</span>
        </div>
      </div>

      {events.length === 0 ? (
        <p className="text-text-muted text-sm">No major catalysts in the next 30 days.</p>
      ) : (
        <ol className="relative border-l border-bg-borderHi ml-2 space-y-3">
          {events.map((e: CatalystEvent, i) => {
            const tone = KIND_TONE[e.kind] || KIND_TONE.macro;
            const Icon = tone.Icon;
            const weightColor = WEIGHT_TONE[e.weight] || "text-text-muted";
            return (
              <li key={i} className="ml-4">
                <span
                  className={cn(
                    "absolute -left-[7px] mt-1 w-3.5 h-3.5 rounded-full border-2 border-bg-card grid place-items-center",
                    tone.color, tone.bg
                  )}
                >
                  <Icon size={8} strokeWidth={3} />
                </span>
                <div className="bg-bg-base rounded-md p-3 border border-bg-border">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="text-sm font-medium text-text-primary">{e.title}</span>
                    <span className={cn("badge text-[10px]", tone.bg, tone.color)}>{tone.label}</span>
                    <span className={cn("text-[10px] uppercase tracking-wider font-semibold ml-auto", weightColor)}>
                      {e.weight.replace("_", " ")}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-text-muted tabular-nums">
                    <span>{e.date}</span>
                    <span>·</span>
                    <span>{dayLabel(e.days_out)}</span>
                  </div>
                  {e.detail && (
                    <p className="text-xs text-text-secondary mt-1.5 leading-relaxed">{e.detail}</p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}

      <p className="text-[10px] text-text-muted mt-3 pt-3 border-t border-bg-border">
        Source: yfinance for stock-specific events; macro releases (FOMC / CPI / NFP) curated quarterly.
      </p>
    </section>
  );
}
