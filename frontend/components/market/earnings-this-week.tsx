"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Sun, Moon } from "lucide-react";
import { marketApi } from "@/lib/api/endpoints";
import type { EarningsWeekCompany, EarningsWeekDay } from "@/lib/api/types";
import { PeriodChips } from "@/components/ui/period-chips";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const WINDOW_OPTIONS = ["3", "7", "14"] as const;
const WINDOW_LABEL: Record<string, string> = { "3": "3D", "7": "1W", "14": "2W" };

function verdictPill(v: string | null | undefined): { label: string; cls: string } | null {
  if (!v) return null;
  switch (v) {
    case "pricing_in_beat":   return { label: "beat",         cls: "bg-accent-green/15 text-accent-greenSoft border-accent-green/30" };
    case "leaning_bullish":   return { label: "lean bull",    cls: "bg-accent-green/10 text-accent-greenSoft border-accent-green/20" };
    case "mixed":             return { label: "mixed",        cls: "bg-bg-card2 text-text-muted border-bg-borderHi" };
    case "leaning_bearish":   return { label: "lean bear",    cls: "bg-accent-red/10 text-accent-redSoft border-accent-red/20" };
    case "pricing_in_miss":   return { label: "miss",         cls: "bg-accent-red/15 text-accent-redSoft border-accent-red/30" };
    default:                  return null;
  }
}

function HourBadge({ hour }: { hour: string | null | undefined }) {
  if (hour === "bmo") return (
    <span title="Before market open" className="inline-flex items-center gap-0.5 text-[9px] text-text-muted">
      <Sun size={9} />BMO
    </span>
  );
  if (hour === "amc") return (
    <span title="After market close" className="inline-flex items-center gap-0.5 text-[9px] text-text-muted">
      <Moon size={9} />AMC
    </span>
  );
  return null;
}

function fmtMcap(mc: number | null | undefined): string | null {
  if (!mc || mc <= 0) return null;
  if (mc >= 1e12) return `$${(mc / 1e12).toFixed(1)}T`;
  if (mc >= 1e9)  return `$${(mc / 1e9).toFixed(mc >= 100e9 ? 0 : 1)}B`;
  if (mc >= 1e6)  return `$${(mc / 1e6).toFixed(0)}M`;
  return `$${mc.toFixed(0)}`;
}

function fmtEps(eps: number | null | undefined): string | null {
  if (eps === null || eps === undefined) return null;
  // Keep sign for losses
  const sign = eps < 0 ? "−" : "";
  return `${sign}$${Math.abs(eps).toFixed(2)}`;
}

function CompanyChip({ c }: { c: EarningsWeekCompany }) {
  const pill = verdictPill(c.pre_earnings_verdict);
  const mcap = fmtMcap(c.market_cap);
  const eps  = fmtEps(c.eps_estimate);
  return (
    <Link
      href={`/deep-dive/${encodeURIComponent(c.symbol)}`}
      className="group flex flex-col gap-0.5 px-2 py-1.5 rounded-md bg-bg-base/40 hover:bg-bg-card2 border border-bg-border hover:border-bg-borderHi transition-colors"
      title={c.name || c.symbol}
    >
      <div className="flex items-center gap-2 text-[11px]">
        <span className="font-mono font-semibold text-text-primary">{c.symbol}</span>
        <HourBadge hour={c.hour} />
        {pill && (
          <span className={cn("ml-auto text-[9px] px-1.5 py-px rounded border font-mono uppercase tracking-wider", pill.cls)}>
            {pill.label}
          </span>
        )}
      </div>
      {(mcap || eps) && (
        <div className="flex items-center gap-2 text-[9px] text-text-muted tabular-nums">
          {mcap && <span title="Market cap">{mcap}</span>}
          {mcap && eps && <span className="text-text-dim">·</span>}
          {eps && <span title="EPS estimate">EPS est {eps}</span>}
        </div>
      )}
    </Link>
  );
}

function DayBlock({ day }: { day: EarningsWeekDay }) {
  return (
    <div className="card-subtle p-3">
      <div className="flex items-baseline justify-between mb-2">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent-blueSoft">
            {day.weekday}
          </span>
          <span className="text-[11px] text-text-muted tabular-nums">
            {day.date.slice(5)}
          </span>
        </div>
        <span className="text-[10px] text-text-muted tabular-nums">{day.count} co.</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
        {day.companies.map((c) => (
          <CompanyChip key={c.symbol} c={c} />
        ))}
      </div>
    </div>
  );
}

export function EarningsThisWeek() {
  const [windowDays, setWindowDays] = useState<"3" | "7" | "14">("7");
  const { data, isLoading } = useQuery({
    queryKey: ["earnings-this-week", windowDays],
    queryFn: () => marketApi.earningsThisWeek(Number(windowDays) as 3 | 7 | 14),
    staleTime: 15 * 60_000,
  });

  return (
    <div className="card p-6">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <CalendarDays size={16} className="text-accent-blue" />
          <div>
            <h3 className="text-[13px] font-semibold text-text-primary">Earnings this week</h3>
            <p className="text-[11px] text-text-muted">
              {data
                ? `${data.total_companies} companies reporting in the next ${WINDOW_LABEL[windowDays]}`
                : `companies reporting in the next ${WINDOW_LABEL[windowDays]}`}
            </p>
          </div>
        </div>
        <PeriodChips
          value={windowDays}
          onChange={(v) => setWindowDays(v as "3" | "7" | "14")}
          periods={[...WINDOW_OPTIONS]}
          accent="blue"
          size="sm"
        />
      </div>

      {isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : !data || data.by_day.length === 0 ? (
        <div className="rounded-md border border-bg-border bg-bg-base/40 p-4">
          <p className="text-[12px] text-text-muted leading-relaxed">
            {data?.coverage_note ?? "No earnings reported in the window."}
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
            {data.by_day.map((day) => (
              <DayBlock key={day.date} day={day} />
            ))}
          </div>
          <p className="text-[10px] text-text-muted mt-3 pt-2 border-t border-bg-border leading-relaxed">
            BMO = before market open, AMC = after market close. Verdict pills come from the
            Pre-Earnings Setup signal where it&apos;s cached — click any symbol for full deep dive.
          </p>
        </>
      )}
    </div>
  );
}
