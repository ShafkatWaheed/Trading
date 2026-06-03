"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { TrendingUp, TrendingDown, Building2, ChevronDown } from "lucide-react";
import { flowsApi } from "@/lib/api/endpoints";
import type { SectorTapeEntry } from "@/lib/api/types";
import { PeriodChips } from "@/components/ui/period-chips";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const WINDOW_OPTIONS = ["90", "180", "365"] as const;
const WINDOW_LABEL: Record<string, string> = { "90": "90D", "180": "6M", "365": "1Y" };

function fmtUsd(v: number | null | undefined): string {
  if (v == null || v === 0) return "$0";
  const abs = Math.abs(v);
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toFixed(0)}`;
}

type FlowType = "active" | "passive" | "all";
const FLOW_TYPES: { key: FlowType; label: string; hint: string }[] = [
  { key: "active",  label: "Active",  hint: "conviction flow — hedge funds, active managers, sovereigns" },
  { key: "passive", label: "Passive", hint: "mechanical flow — index funds (BlackRock, Vanguard, State Street)" },
  { key: "all",     label: "All",     hint: "every institution combined" },
];

export function SmartMoneyTape() {
  const [windowDays, setWindowDays] = useState<"90" | "180" | "365">("180");
  const [flowType, setFlowType] = useState<FlowType>("active");
  const { data, isLoading } = useQuery({
    queryKey: ["smart-money-tape", windowDays],
    queryFn: () => flowsApi.smartMoneyTape(Number(windowDays) as 90 | 180 | 365),
    staleTime: 5 * 60_000,
  });

  // Pick the right view from by_flow_type, falling back to top-level sectors
  // (which equals by_flow_type.all) if the breakdown isn't present.
  const view = data?.by_flow_type?.[flowType];
  const sectors = view?.sectors ?? data?.sectors ?? [];
  const ciksCount = view?.ciks_count;

  return (
    <div className="card p-6">
      <div className="flex items-start justify-between mb-4 gap-2">
        <div className="flex items-center gap-2.5">
          <Building2 size={16} className="text-accent-blue" />
          <div>
            <h3 className="text-[13px] font-semibold text-text-primary">13F sector flow</h3>
            <p className="text-[11px] text-text-muted">
              {FLOW_TYPES.find((f) => f.key === flowType)?.hint}
            </p>
          </div>
        </div>
        <PeriodChips
          value={windowDays}
          onChange={(v) => setWindowDays(v as "90" | "180" | "365")}
          periods={[...WINDOW_OPTIONS]}
          accent="blue"
          size="sm"
        />
      </div>

      {/* Flow-type tabs — active is the most informative view */}
      <div className="flex items-center gap-1 mb-3 p-0.5 bg-bg-base border border-bg-border rounded-md self-start">
        {FLOW_TYPES.map((f) => (
          <button
            key={f.key}
            onClick={() => setFlowType(f.key)}
            title={f.hint}
            className={cn(
              "px-2.5 py-1 rounded-[4px] text-[10px] font-semibold uppercase tracking-wider transition-colors",
              flowType === f.key
                ? "bg-accent-blue/15 text-accent-blueSoft border border-accent-blue/30"
                : "text-text-muted hover:text-text-primary border border-transparent",
            )}
          >
            {f.label}
            {data?.by_flow_type && (
              <span className="ml-1 text-text-dim font-normal">
                {data.by_flow_type[f.key]?.ciks_count ?? 0}
              </span>
            )}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <SectorList
          sectors={sectors}
          coverageNote={data?.coverage_note ?? ""}
          windowLabel={WINDOW_LABEL[windowDays]}
          flowType={flowType}
          ciksCount={ciksCount}
        />
      )}
    </div>
  );
}

function SectorList({
  sectors, coverageNote, windowLabel, flowType, ciksCount,
}: {
  sectors: SectorTapeEntry[]; coverageNote: string; windowLabel: string;
  flowType?: FlowType; ciksCount?: number;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (sectors.length === 0) {
    const emptyNote = flowType === "active"
      ? `No conviction flow data in the ${windowLabel} window yet (${ciksCount ?? 0} institutions). Try "All" or wait for more 13F snapshots.`
      : flowType === "passive"
      ? `No passive flow data in the ${windowLabel} window yet (${ciksCount ?? 0} institutions).`
      : coverageNote;
    return (
      <div className="rounded-md border border-bg-border bg-bg-base/40 p-4">
        <p className="text-[12px] text-text-muted leading-relaxed">{emptyNote}</p>
      </div>
    );
  }

  const max = Math.max(...sectors.map((s) => Math.abs(s.net_dollar_flow ?? 0)), 1);

  return (
    <>
      <div className="space-y-2">
        {sectors.slice(0, 8).map((s) => {
          const flow = s.net_dollar_flow ?? 0;
          const positive = flow >= 0;
          const widthPct = (Math.abs(flow) / max) * 50;
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
                        ? "left-1/2 bg-gradient-to-r from-accent-blue/30 to-accent-blue/60"
                        : "right-1/2 bg-gradient-to-l from-accent-red/30 to-accent-red/60",
                    )}
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
                <div
                  className={cn(
                    "w-20 text-right tabular-nums text-[12px] font-semibold shrink-0",
                    positive ? "text-accent-blueSoft" : "text-accent-redSoft",
                  )}
                >
                  {flow >= 0 ? "+" : ""}{fmtUsd(flow)}
                </div>
                <div className="w-24 text-right shrink-0 text-[10px] text-text-muted tabular-nums">
                  +{s.adds_count ?? 0} / -{s.drops_count ?? 0}
                </div>
                <ChevronDown
                  size={12}
                  className={cn("text-text-muted shrink-0 transition-transform", isOpen && "rotate-180")}
                />
              </button>
              {isOpen && (
                <div className="ml-44 mr-32 mt-1 mb-2 grid grid-cols-2 gap-3 text-[11px]">
                  <div>
                    <div className="text-text-muted mb-1">Top added</div>
                    {(s.top_added ?? []).length === 0 ? (
                      <div className="text-text-dim italic">none</div>
                    ) : (
                      <ul className="space-y-0.5">
                        {(s.top_added ?? []).slice(0, 5).map((x) => (
                          <li key={x.symbol} className="flex justify-between gap-2 tabular-nums">
                            <span className="text-text-secondary">{x.symbol}</span>
                            <span className="text-accent-blueSoft">+{fmtUsd(x.delta_usd ?? 0)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div>
                    <div className="text-text-muted mb-1">Top trimmed</div>
                    {(s.top_trimmed ?? []).length === 0 ? (
                      <div className="text-text-dim italic">none</div>
                    ) : (
                      <ul className="space-y-0.5">
                        {(s.top_trimmed ?? []).slice(0, 3).map((x) => (
                          <li key={x.symbol} className="flex justify-between gap-2 tabular-nums">
                            <span className="text-text-secondary">{x.symbol}</span>
                            <span className="text-accent-redSoft">{fmtUsd(x.delta_usd ?? 0)}</span>
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
        {windowLabel} net adds − trims across {ciksCount ?? "all"} institutions with sequential 13F filings.
        {" "}Active = conviction (hedge funds, active managers, sovereigns).
        {" "}Passive = mechanical index-flow (BlackRock, Vanguard, State Street).
        {" "}45-day disclosure lag applies.
      </p>
    </>
  );
}
