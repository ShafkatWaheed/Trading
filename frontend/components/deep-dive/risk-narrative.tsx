"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

const SECTIONS: { key: keyof Sections; label: string; tone: string }[] = [
  { key: "industry_threats",  label: "Industry Threats",        tone: "text-accent-amber" },
  { key: "competitive_risks", label: "Competitive Risks",       tone: "text-accent-amber" },
  { key: "balance_sheet",     label: "Balance Sheet",           tone: "text-accent-redSoft" },
  { key: "macro_exposure",    label: "Macro Exposure",          tone: "text-accent-amber" },
  { key: "worst_case",        label: "Realistic Worst Case",    tone: "text-accent-redSoft" },
];

type Sections = {
  industry_threats?: string;
  competitive_risks?: string;
  balance_sheet?: string;
  macro_exposure?: string;
  worst_case?: string;
};

export function RiskNarrative({ symbol }: Props) {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["risk-narrative", symbol],
    queryFn: () => stocksApi.riskNarrative(symbol),
    staleTime: 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  return (
    <section className="card p-6 border-l-4 border-accent-red/40">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <AlertTriangle size={16} className="text-accent-redSoft" />
          <h3 className="text-base font-semibold">Downside Brief</h3>
          {data?.from_cache && (
            <span className="text-[10px] uppercase tracking-wider text-text-muted">cached</span>
          )}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          title="Regenerate"
          className="text-xs text-text-muted hover:text-text-primary flex items-center gap-1.5 disabled:opacity-40"
        >
          {isFetching
            ? <Loader2 size={12} className="animate-spin" />
            : <RefreshCw size={12} />}
          Refresh
        </button>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {SECTIONS.map((s) => (
            <div key={s.key}>
              <div className="text-xs font-medium text-text-muted mb-1.5">{s.label}</div>
              <Skeleton className="h-12 w-full" />
            </div>
          ))}
          <p className="text-[10px] text-text-muted mt-2">
            Claude is writing the downside narrative — first run is ~15s, then cached for 24h.
          </p>
        </div>
      )}

      {isError && (
        <p className="text-accent-redSoft text-sm">
          {(error as Error)?.message || "Failed to load risk narrative."}
        </p>
      )}

      {data?.error && (
        <p className="text-accent-amber text-sm">{data.error}</p>
      )}

      {data && !data.error && !isLoading && (
        <div className="space-y-4">
          {SECTIONS.map((s) => {
            const text = (data as Sections)[s.key];
            if (!text) return null;
            return (
              <div key={s.key}>
                <div className={cn("text-xs font-semibold uppercase tracking-wider mb-1.5", s.tone)}>
                  {s.label}
                </div>
                <p className="text-text-secondary text-sm leading-relaxed">{text}</p>
              </div>
            );
          })}
          {data.invalidates_if && (
            <div className="bg-bg-base rounded-md p-3 border border-bg-border">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-accent-greenSoft mb-1">
                Bear thesis invalidates if
              </div>
              <p className="text-text-secondary text-sm leading-relaxed">{data.invalidates_if}</p>
            </div>
          )}
          <p className="text-[10px] text-text-muted pt-2 border-t border-bg-border">
            AI-generated downside framing — not a forecast. Cross-check against your own due diligence.
          </p>
        </div>
      )}
    </section>
  );
}
