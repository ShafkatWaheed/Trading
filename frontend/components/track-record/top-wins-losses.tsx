"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Trophy, AlertOctagon } from "lucide-react";
import { trackRecordApi } from "@/lib/api/endpoints";
import type { TopWinLossRow } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { days: number; limit?: number };

function shortDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return iso.slice(0, 10);
  }
}

function sourceBadge(src: string): string {
  if (src === "recommendation") return "REC";
  if (src === "ai_analyst") return "AI";
  if (src === "bubble_score") return "BUB";
  return src.toUpperCase().slice(0, 3);
}

export function TopWinsLosses({ days, limit = 10 }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["track-record-top", days, limit],
    queryFn: () => trackRecordApi.top({ days, limit }),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Skeleton className="h-72" />
        <Skeleton className="h-72" />
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Column
        title="Top wins"
        subtitle="Best returns from graded decisions"
        icon={Trophy}
        accent="text-accent-greenSoft"
        rows={data.wins}
      />
      <Column
        title="Top misses"
        subtitle="Worst returns from graded decisions"
        icon={AlertOctagon}
        accent="text-accent-redSoft"
        rows={data.losses}
      />
    </div>
  );
}

function Column({
  title, subtitle, icon: Icon, accent, rows,
}: {
  title: string; subtitle: string; icon: typeof Trophy; accent: string;
  rows: TopWinLossRow[];
}) {
  return (
    <section className="card-subtle p-5">
      <div className="flex items-center gap-2 mb-3">
        <Icon size={14} className={accent} />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">{title}</h3>
        <span className="text-[11px] text-text-muted ml-auto">{subtitle}</span>
      </div>
      {rows.length === 0 ? (
        <p className="text-text-muted text-sm">No graded decisions yet.</p>
      ) : (
        <ul className="divide-y divide-bg-border">
          {rows.map((r) => (
            <li key={r.id} className="py-2.5 flex items-center gap-3 text-sm">
              <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border border-bg-borderHi text-text-muted shrink-0">
                {sourceBadge(r.source)}
              </span>
              <Link
                href={`/deep-dive/${encodeURIComponent(r.symbol)}`}
                className="font-semibold text-text-primary hover:text-accent-cyan shrink-0 tabular-nums"
              >
                {r.symbol}
              </Link>
              <span className="text-text-muted text-[11px] truncate flex-1 min-w-0">
                {r.decision} · {shortDate(r.created_at)}
              </span>
              <span
                className={cn(
                  "tabular-nums font-bold shrink-0",
                  r.return_pct >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft",
                )}
              >
                {r.return_pct >= 0 ? "+" : ""}{r.return_pct.toFixed(1)}%
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
