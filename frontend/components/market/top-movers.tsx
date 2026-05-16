"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { TrendingUp, TrendingDown, ArrowRight } from "lucide-react";
import { marketApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { MoverRow } from "@/lib/api/types";

type Window = "1d" | "5d";

export function TopMovers() {
  const [window, setWindow] = useState<Window>("1d");
  const { data, isLoading } = useQuery({
    queryKey: ["market-dashboard"],
    queryFn: () => marketApi.dashboard(),
    staleTime: 2 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp size={16} className="text-accent-greenSoft" />
          <h3 className="text-base font-semibold">Top Movers</h3>
        </div>
        <Skeleton className="h-40 w-full" />
      </section>
    );
  }
  if (!data?.movers) return null;

  const gainers = window === "1d" ? data.movers.gainers_1d : data.movers.gainers_5d;
  const losers  = window === "1d" ? data.movers.losers_1d  : data.movers.losers_5d;

  return (
    <section className="card-subtle p-6">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <TrendingUp size={16} className="text-accent-greenSoft" />
        <h3 className="text-base font-semibold">Top Movers</h3>
        <span className="text-[10px] uppercase tracking-wider text-text-muted">
          {window === "1d" ? "today's price moves" : "5-day trend"} · click to deep-dive
        </span>
        <div className="ml-auto flex gap-1 p-1 rounded-md bg-bg-base border border-bg-border">
          {(["1d", "5d"] as Window[]).map((w) => (
            <button
              key={w}
              onClick={() => setWindow(w)}
              className={cn(
                "px-2.5 py-1 rounded text-[11px] font-semibold uppercase tracking-wider transition-colors",
                window === w
                  ? "bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/40"
                  : "text-text-muted hover:text-text-primary"
              )}
            >
              {w === "1d" ? "today" : "5-day"}
            </button>
          ))}
        </div>
      </div>

      {window === "5d" && (
        <p className="text-[10px] text-text-muted mb-3 leading-relaxed">
          5-day shows multi-day trends — filters out single-day noise; better for spotting
          real setups vs one-off pumps.
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Column title="Gainers" rows={gainers} positive />
        <Column title="Losers"  rows={losers}  positive={false} />
      </div>
    </section>
  );
}

function Column({ title, rows, positive }: { title: string; rows: MoverRow[]; positive: boolean }) {
  const TrendIcon = positive ? TrendingUp : TrendingDown;
  const toneColor = positive ? "text-accent-greenSoft" : "text-accent-redSoft";

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <TrendIcon size={12} className={toneColor} />
        <span className={cn("text-[11px] uppercase tracking-wider font-semibold", toneColor)}>
          {title}
        </span>
      </div>
      <ul className="space-y-1.5">
        {rows.length === 0 && (
          <li className="text-text-muted text-xs">No data.</li>
        )}
        {rows.map((r) => (
          <li key={r.symbol}>
            <Link
              href={`/deep-dive/${encodeURIComponent(r.symbol)}`}
              className="group flex items-center gap-3 px-3 py-2 rounded-md bg-bg-base border border-bg-border hover:border-bg-borderHi hover:bg-bg-card2 transition-colors"
            >
              <span className="font-mono font-bold text-sm text-text-primary group-hover:text-accent-cyan w-16 shrink-0">
                {r.symbol}
              </span>
              <span className="text-text-secondary tabular-nums text-xs w-20">
                ${r.price.toFixed(2)}
              </span>
              <span className={cn("font-semibold tabular-nums text-sm ml-auto", toneColor)}>
                {r.change_pct >= 0 ? "+" : ""}{r.change_pct.toFixed(2)}%
              </span>
              <ArrowRight size={12} className="text-text-muted group-hover:text-accent-cyan group-hover:translate-x-0.5 transition-transform" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
