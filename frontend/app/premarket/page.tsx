"use client";

/**
 * Pre-market gainers + losers, with today's predictions overlaid.
 *
 * Why this exists
 * ---------------
 * We added pre-market gap as a prediction signal in Phase 8 but had no
 * surface that just showed the raw pre-market tape. This is that surface:
 * top N gainers, top N losers, plus the predicted picks with their
 * pre-market gap stamped on each.
 *
 * Use before the open to spot:
 *   - Predictions already moving in the right direction
 *   - Unexpected gappers not in the prediction list
 *   - Predictions that are getting sold pre-open (worry signal)
 */

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Sunrise, TrendingUp, TrendingDown, Target } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { premarketApi } from "@/lib/api/endpoints";
import type { PremarketPayload, PremarketRow, PremarketPredictedRow } from "@/lib/api/types";
import { cn } from "@/lib/utils";


function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function pctTone(v: number | null | undefined): string {
  if (v == null) return "text-text-muted";
  if (v > 0) return "text-accent-greenSoft";
  if (v < 0) return "text-accent-redSoft";
  return "text-text-muted";
}


function MoverRow({ r }: { r: PremarketRow }) {
  return (
    <div className="card p-3 flex items-center gap-3">
      <span className="font-mono text-[12px] font-semibold text-text-primary w-16 shrink-0">
        {r.symbol}
      </span>
      <span className={cn("font-mono text-[12px] tabular-nums w-20 shrink-0", pctTone(r.gap_pct))}>
        {fmtPct(r.gap_pct)}
      </span>
      <div className="flex-1 min-w-0">
        {r.in_predictions ? (
          <Link
            href="/predictions"
            className="badge text-[9px] bg-accent-blue/10 text-accent-blueSoft border-accent-blue/30 inline-flex items-center gap-1"
          >
            <Target size={9} />
            Predicted #{r.predicted_rank}
          </Link>
        ) : null}
      </div>
    </div>
  );
}


function PredictedPremarketRow({ r }: { r: PremarketPredictedRow }) {
  return (
    <div className="card p-3 flex items-center gap-3 border-l-4 border-accent-blue/30">
      <span className="font-mono text-[11px] text-text-muted w-6 shrink-0">#{r.rank}</span>
      <span className="font-mono text-[12px] font-semibold text-text-primary w-16 shrink-0">
        {r.symbol}
      </span>
      <span className={cn("font-mono text-[12px] tabular-nums w-20 shrink-0", pctTone(r.gap_pct))}>
        {r.gap_pct == null ? "no premkt" : fmtPct(r.gap_pct)}
      </span>
    </div>
  );
}


export default function PremarketPage() {
  const q = useQuery<PremarketPayload>({
    queryKey: ["premarket", 20],
    queryFn: () => premarketApi.get(20),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });

  return (
    <div>
      <PageHeader
        icon={Sunrise}
        title="Pre-Market"
        subtitle="Top gainers + losers from Tier A; predictions overlaid"
        accent="text-accent-amber"
        iconBg="bg-accent-amber/10"
        trailing={
          q.data && (
            <span className="text-[11px] text-text-muted font-mono">
              {q.data.scored_size ?? q.data.universe_size} scored · {q.data.as_of?.slice(11, 16)} UTC
            </span>
          )
        }
      />

      {q.isLoading && (
        <div className="card p-6 text-text-muted text-[12px] italic">
          Fetching pre-market quotes from Yahoo (~10s for full Tier A)…
        </div>
      )}

      {q.error && (
        <div className="card p-6 border-l-4 border-accent-red/40">
          <p className="text-accent-redSoft text-[13px]">Could not load pre-market data.</p>
          <p className="text-text-muted text-[11px] mt-1">{(q.error as Error).message}</p>
        </div>
      )}

      {q.data && q.data.scored_size === 0 && (
        <div className="card p-6 text-text-muted text-[12px] italic">
          No pre-market data available. Likely off-hours (markets closed,
          or pre-market session not started yet).
        </div>
      )}

      {q.data && (q.data.scored_size ?? 0) > 0 && (
        <>
          {/* Predicted picks with pre-market overlay */}
          {q.data.predicted_premarket.length > 0 && (
            <section className="mb-8">
              <div className="flex items-baseline gap-3 mb-3">
                <Target size={14} className="text-accent-blue translate-y-[2px]" />
                <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-accent-blueSoft">
                  Today's predictions · pre-market check
                </span>
              </div>
              <div className="space-y-2">
                {q.data.predicted_premarket.map((r) => (
                  <PredictedPremarketRow key={r.symbol} r={r} />
                ))}
              </div>
            </section>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Top gainers */}
            <section>
              <div className="flex items-baseline gap-3 mb-3">
                <TrendingUp size={14} className="text-accent-greenSoft translate-y-[2px]" />
                <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-accent-greenSoft">
                  Top gainers
                </span>
                <span className="text-[11px] text-text-muted">
                  {q.data.gainers.length} of Tier A
                </span>
              </div>
              <div className="space-y-2">
                {q.data.gainers.map((r) => <MoverRow key={r.symbol} r={r} />)}
              </div>
            </section>

            {/* Top losers */}
            <section>
              <div className="flex items-baseline gap-3 mb-3">
                <TrendingDown size={14} className="text-accent-redSoft translate-y-[2px]" />
                <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-accent-redSoft">
                  Top losers
                </span>
                <span className="text-[11px] text-text-muted">
                  {q.data.losers.length} of Tier A
                </span>
              </div>
              <div className="space-y-2">
                {q.data.losers.map((r) => <MoverRow key={r.symbol} r={r} />)}
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
