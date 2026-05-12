"use client";

import { useQuery } from "@tanstack/react-query";
import { Users, ArrowUp, ArrowDown, Minus } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatPercent } from "@/lib/utils";

type Props = { symbol: string };

function ratingTone(r?: string | null) {
  if (!r) return { label: "—", color: "text-text-muted" };
  const k = r.toLowerCase();
  if (k.includes("strong") && k.includes("buy")) return { label: "Strong Buy", color: "text-accent-greenSoft" };
  if (k.includes("buy"))  return { label: "Buy",   color: "text-accent-greenSoft" };
  if (k.includes("hold")) return { label: "Hold",  color: "text-accent-amber" };
  if (k.includes("sell")) return { label: "Sell",  color: "text-accent-redSoft" };
  return { label: r.toUpperCase(), color: "text-text-secondary" };
}

function Bar({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="w-20 text-text-muted shrink-0">{label}</div>
      <div className="flex-1 h-1.5 bg-bg-base rounded-full overflow-hidden">
        <div className={cn("h-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
      <div className="w-8 text-right tabular-nums text-text-secondary">{count}</div>
    </div>
  );
}

export function AnalystConsensus({ symbol }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["analyst-consensus", symbol],
    queryFn: () => stocksApi.analystConsensus(symbol),
    staleTime: 12 * 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <Users size={16} className="text-accent-blue" />
          <h3 className="text-base font-semibold">Wall Street Consensus</h3>
        </div>
        <Skeleton className="h-32 w-full" />
      </section>
    );
  }

  if (isError || !data || data.error) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <Users size={16} className="text-accent-blue" />
          <h3 className="text-base font-semibold">Wall Street Consensus</h3>
        </div>
        <p className="text-text-muted text-sm">{data?.error || "Analyst data unavailable."}</p>
      </section>
    );
  }

  const tone = ratingTone(data.rating);
  const breakdown = data.ratings_breakdown || { strong_buy: 0, buy: 0, hold: 0, sell: 0, strong_sell: 0 };
  const total = breakdown.strong_buy + breakdown.buy + breakdown.hold + breakdown.sell + breakdown.strong_sell;
  const upside = data.upside_pct ?? 0;
  const UpDown = upside >= 1 ? ArrowUp : upside <= -1 ? ArrowDown : Minus;
  const upDownColor = upside >= 1 ? "text-accent-greenSoft" : upside <= -1 ? "text-accent-redSoft" : "text-text-muted";

  return (
    <section className="card-subtle p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Users size={16} className="text-accent-blue" />
          <h3 className="text-base font-semibold">Wall Street Consensus</h3>
          {data.from_cache && (
            <span className="text-[10px] uppercase tracking-wider text-text-muted">cached</span>
          )}
        </div>
        <div className="text-[10px] text-text-muted">
          {data.analyst_count ? `${data.analyst_count} analysts` : "—"}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
        <div className="bg-bg-base rounded-md p-3 border border-bg-border">
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Rating</div>
          <div className={cn("text-xl font-bold mt-1", tone.color)}>{tone.label}</div>
          {data.rating_mean != null && (
            <div className="text-[10px] text-text-muted mt-0.5">
              avg score {data.rating_mean.toFixed(2)} (1=Strong Buy, 5=Strong Sell)
            </div>
          )}
        </div>

        <div className="bg-bg-base rounded-md p-3 border border-bg-border">
          <div className="text-[10px] uppercase tracking-wider text-text-muted">12mo Target</div>
          <div className="text-xl font-bold tabular-nums mt-1">
            {data.target_mean != null ? `$${data.target_mean.toFixed(0)}` : "—"}
          </div>
          {data.target_low != null && data.target_high != null && (
            <div className="text-[10px] text-text-muted mt-0.5 tabular-nums">
              range ${data.target_low.toFixed(0)} – ${data.target_high.toFixed(0)}
            </div>
          )}
        </div>

        <div className="bg-bg-base rounded-md p-3 border border-bg-border">
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Implied Upside</div>
          <div className={cn("text-xl font-bold tabular-nums mt-1 flex items-center gap-1", upDownColor)}>
            <UpDown size={16} />
            {data.upside_pct != null ? formatPercent(data.upside_pct) : "—"}
          </div>
          {data.current_price != null && (
            <div className="text-[10px] text-text-muted mt-0.5 tabular-nums">
              from ${data.current_price.toFixed(2)} now
            </div>
          )}
        </div>
      </div>

      {total > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider text-text-muted mb-2">Ratings breakdown</div>
          <Bar label="Strong Buy" count={breakdown.strong_buy} total={total} color="bg-accent-green" />
          <Bar label="Buy"        count={breakdown.buy}        total={total} color="bg-accent-greenSoft" />
          <Bar label="Hold"       count={breakdown.hold}       total={total} color="bg-accent-amber" />
          <Bar label="Sell"       count={breakdown.sell}       total={total} color="bg-accent-redSoft" />
          <Bar label="Strong Sell" count={breakdown.strong_sell} total={total} color="bg-accent-red" />
        </div>
      )}

      <p className="text-[10px] text-text-muted mt-4 pt-3 border-t border-bg-border">
        Source: Wall Street analyst consensus via yfinance. Targets are 12-month forward.
      </p>
    </section>
  );
}
