"use client";

import { useQuery } from "@tanstack/react-query";
import { TrendingUp, Loader2, RefreshCw } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

type Sections = {
  growth_drivers?: string;
  competitive_moat?: string;
  multiple_expansion?: string;
  catalysts?: string;
  best_case?: string;
  invalidates_if?: string;
};

const SECTIONS: { key: keyof Sections; label: string }[] = [
  { key: "growth_drivers",     label: "Growth Drivers" },
  { key: "competitive_moat",   label: "Competitive Moat" },
  { key: "multiple_expansion", label: "Multiple Expansion Path" },
  { key: "catalysts",          label: "Near-term Catalysts" },
  { key: "best_case",          label: "Realistic Best Case" },
];

export function BullNarrative({ symbol }: Props) {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["bull-narrative", symbol],
    queryFn: () => stocksApi.bullNarrative(symbol),
    staleTime: 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  return (
    <section className="card p-6 border-l-4 border-accent-green/40">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <TrendingUp size={16} className="text-accent-greenSoft" />
          <h3 className="text-base font-semibold">Bull Brief</h3>
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
          {isFetching ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
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
            Claude is writing the upside narrative — first run is ~15s, then cached for 24h.
          </p>
        </div>
      )}

      {isError && (
        <p className="text-accent-redSoft text-sm">
          {(error as Error)?.message || "Failed to load bull narrative."}
        </p>
      )}

      {data?.error && <p className="text-accent-amber text-sm">{data.error}</p>}

      {data && !data.error && !isLoading && (
        <div className="space-y-4">
          {SECTIONS.map((s) => {
            const text = (data as Sections)[s.key];
            if (!text) return null;
            return (
              <div key={s.key}>
                <div className="text-xs font-semibold uppercase tracking-wider text-accent-greenSoft mb-1.5">
                  {s.label}
                </div>
                <p className="text-text-secondary text-sm leading-relaxed">{text}</p>
              </div>
            );
          })}
          {data.invalidates_if && (
            <div className="bg-bg-base rounded-md p-3 border border-bg-border">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-accent-amber mb-1">
                Bull thesis invalidates if
              </div>
              <p className="text-text-secondary text-sm leading-relaxed">{data.invalidates_if}</p>
            </div>
          )}
          <p className="text-[10px] text-text-muted pt-2 border-t border-bg-border">
            AI-generated upside framing — pair with the Downside Brief for symmetric view.
          </p>
        </div>
      )}
    </section>
  );
}
