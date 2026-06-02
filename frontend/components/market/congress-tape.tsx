"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { TrendingUp, TrendingDown, Vote, ChevronDown } from "lucide-react";
import { flowsApi } from "@/lib/api/endpoints";
import type { SectorTapeEntry } from "@/lib/api/types";
import { PeriodChips } from "@/components/ui/period-chips";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const WINDOW_OPTIONS = ["90", "180", "365"] as const;
const WINDOW_LABEL: Record<string, string> = { "90": "90D", "180": "6M", "365": "1Y" };

export function CongressTape() {
  const [windowDays, setWindowDays] = useState<"90" | "180" | "365">("180");
  const { data, isLoading } = useQuery({
    queryKey: ["congress-tape", windowDays],
    queryFn: () => flowsApi.congressTape(Number(windowDays) as 90 | 180 | 365),
    staleTime: 5 * 60_000,
  });

  return (
    <div className="card p-6">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <Vote size={16} className="text-accent-violet" />
          <div>
            <h3 className="text-[13px] font-semibold text-text-primary">Congress sector flow</h3>
            <p className="text-[11px] text-text-muted">political insider buys / sells by sector</p>
          </div>
        </div>
        <PeriodChips
          value={windowDays}
          onChange={(v) => setWindowDays(v as "90" | "180" | "365")}
          periods={[...WINDOW_OPTIONS]}
          accent="violet"
          size="sm"
        />
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <SectorList
          sectors={data?.sectors ?? []}
          coverageNote={data?.coverage_note ?? ""}
          windowLabel={WINDOW_LABEL[windowDays]}
        />
      )}
    </div>
  );
}

function SectorList({
  sectors, coverageNote, windowLabel,
}: { sectors: SectorTapeEntry[]; coverageNote: string; windowLabel: string }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (sectors.length === 0) {
    return (
      <div className="rounded-md border border-bg-border bg-bg-base/40 p-4">
        <p className="text-[12px] text-text-muted leading-relaxed">{coverageNote}</p>
      </div>
    );
  }

  const max = Math.max(...sectors.map((s) => Math.abs(s.net_trades ?? 0)), 1);

  return (
    <>
      <div className="space-y-2">
        {sectors.slice(0, 8).map((s) => {
          const net = s.net_trades ?? 0;
          const positive = net >= 0;
          const widthPct = (Math.abs(net) / max) * 50;
          const isOpen = expanded === s.sector;
          return (
            <div key={s.sector} className="text-sm">
              <button
                onClick={() => setExpanded(isOpen ? null : s.sector)}
                className="w-full flex items-center gap-3 hover:bg-bg-card/60 rounded-md px-2 py-1.5 transition-colors text-left"
              >
                <div className="w-40 truncate text-[12px] text-text-secondary flex items-center gap-2 shrink-0">
                  {positive ? (
                    <TrendingUp size={11} className="text-accent-greenSoft shrink-0" strokeWidth={2.4} />
                  ) : (
                    <TrendingDown size={11} className="text-accent-redSoft shrink-0" strokeWidth={2.4} />
                  )}
                  <span className="font-medium">{s.sector}</span>
                </div>
                <div className="flex-1 relative h-5 flex items-center bg-bg-base/30 rounded">
                  <div className="absolute inset-y-0 left-1/2 w-px bg-bg-borderHi" />
                  <div
                    className={cn(
                      "absolute h-3.5 rounded-sm transition-all duration-500",
                      positive
                        ? "left-1/2 bg-gradient-to-r from-accent-violet/30 to-accent-violet/60"
                        : "right-1/2 bg-gradient-to-l from-accent-red/30 to-accent-red/60",
                    )}
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
                <div
                  className={cn(
                    "w-16 text-right tabular-nums text-[12px] font-semibold shrink-0",
                    positive ? "text-accent-violet" : "text-accent-redSoft",
                  )}
                >
                  {net >= 0 ? "+" : ""}{net}
                </div>
                <div className="w-28 text-right shrink-0 text-[10px] text-text-muted tabular-nums">
                  {s.buys_count ?? 0} buys / {s.sells_count ?? 0} sells
                </div>
                <ChevronDown
                  size={12}
                  className={cn("text-text-muted shrink-0 transition-transform", isOpen && "rotate-180")}
                />
              </button>
              {isOpen && (
                <div className="ml-44 mr-32 mt-1 mb-2 grid grid-cols-2 gap-3 text-[11px]">
                  <div>
                    <div className="text-text-muted mb-1">Top bought ({s.unique_politicians ?? 0} politicians)</div>
                    {(s.top_bought ?? []).length === 0 ? (
                      <div className="text-text-dim italic">none</div>
                    ) : (
                      <ul className="space-y-0.5">
                        {(s.top_bought ?? []).slice(0, 5).map((x) => (
                          <li key={x.symbol} className="flex justify-between gap-2 tabular-nums">
                            <span className="text-text-secondary">{x.symbol}</span>
                            <span className="text-accent-violet">+{x.net ?? 0}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div>
                    <div className="text-text-muted mb-1">Top sold</div>
                    {(s.top_sold ?? []).length === 0 ? (
                      <div className="text-text-dim italic">none</div>
                    ) : (
                      <ul className="space-y-0.5">
                        {(s.top_sold ?? []).slice(0, 3).map((x) => (
                          <li key={x.symbol} className="flex justify-between gap-2 tabular-nums">
                            <span className="text-text-secondary">{x.symbol}</span>
                            <span className="text-accent-redSoft">{x.net ?? 0}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-text-muted mt-3 pt-2 border-t border-bg-border leading-relaxed">
        {windowLabel} net buys − sells from Capitol Trades disclosures.
        STOCK Act disclosures lag up to 45 days.
      </p>
    </>
  );
}
