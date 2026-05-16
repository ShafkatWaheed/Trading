"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ScrollText, CheckCircle2, XCircle, Clock, ChevronDown, ChevronRight } from "lucide-react";
import { trackRecordApi } from "@/lib/api/endpoints";
import type { DecisionLogItem, DecisionStatus, TrackRecordSource } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { RefreshButton } from "@/components/ui/refresh-button";
import { cn } from "@/lib/utils";

const SOURCE_FILTERS: { value: TrackRecordSource | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "recommendation", label: "Rec" },
  { value: "ai_analyst", label: "AI" },
  { value: "bubble_score", label: "Bubble" },
];

function shortDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

function statusMeta(s: DecisionStatus) {
  if (s === "correct")   return { Icon: CheckCircle2, color: "text-accent-greenSoft", label: "Correct" };
  if (s === "incorrect") return { Icon: XCircle,      color: "text-accent-redSoft",   label: "Incorrect" };
  return { Icon: Clock, color: "text-text-muted", label: "Pending" };
}

function sourceBadge(src: TrackRecordSource): string {
  if (src === "recommendation") return "REC";
  if (src === "ai_analyst") return "AI";
  if (src === "bubble_score") return "BUB";
  return src;
}

export function DecisionsLog() {
  const [filter, setFilter] = useState<TrackRecordSource | "all">("all");
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set());

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["track-record-recent", filter],
    queryFn: () => trackRecordApi.decisions({
      source: filter === "all" ? undefined : filter,
      limit: 50,
    }),
    staleTime: 5 * 60 * 1000,
  });

  const toggle = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <section className="card-subtle p-5">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <ScrollText size={14} className="text-accent-blue" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
          Decisions log
        </h3>
        <span className="text-[11px] text-text-muted">most recent 50</span>
        <div className="ml-auto flex items-center gap-1">
          {SOURCE_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={cn(
                "px-2 py-0.5 rounded text-[11px] font-medium uppercase tracking-wider transition-colors",
                filter === f.value
                  ? "bg-bg-card2 text-text-primary"
                  : "text-text-muted hover:text-text-secondary hover:bg-bg-card/60",
              )}
            >
              {f.label}
            </button>
          ))}
          <RefreshButton onClick={() => refetch()} isFetching={isFetching} title="Refresh" />
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-48" />
      ) : !data || data.items.length === 0 ? (
        <p className="text-text-muted text-sm">
          No decisions logged yet. AI verdicts will appear here as Recommendation, AI Analyst, and
          Bubble Score features are exercised.
        </p>
      ) : (
        <ul className="divide-y divide-bg-border">
          {data.items.map((it) => (
            <Row
              key={it.id}
              item={it}
              open={expanded.has(it.id)}
              onToggle={() => toggle(it.id)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function Row({
  item, open, onToggle,
}: { item: DecisionLogItem; open: boolean; onToggle: () => void }) {
  const meta = statusMeta(item.status);
  const StatusIcon = meta.Icon;

  return (
    <li className="py-2.5">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 text-left hover:bg-bg-card2/30 -mx-2 px-2 py-1 rounded transition-colors"
      >
        {open ? <ChevronDown size={12} className="text-text-muted shrink-0" /> : <ChevronRight size={12} className="text-text-muted shrink-0" />}

        <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border border-bg-borderHi text-text-muted shrink-0 w-12 text-center">
          {sourceBadge(item.source)}
        </span>

        <Link
          href={`/deep-dive/${encodeURIComponent(item.symbol)}`}
          onClick={(e) => e.stopPropagation()}
          className="font-semibold text-text-primary hover:text-accent-cyan tabular-nums shrink-0 w-16"
        >
          {item.symbol}
        </Link>

        <span className="text-sm text-text-secondary truncate flex-1 min-w-0">
          {item.decision}
          {item.score !== null && (
            <span className="text-text-muted ml-1.5">({item.score.toFixed(0)})</span>
          )}
        </span>

        <span className="text-[11px] text-text-muted tabular-nums shrink-0 hidden sm:inline">
          {shortDate(item.created_at)}
        </span>

        {item.return_pct !== null ? (
          <span
            className={cn(
              "tabular-nums font-bold shrink-0 text-sm w-16 text-right",
              item.return_pct >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft",
            )}
          >
            {item.return_pct >= 0 ? "+" : ""}{item.return_pct.toFixed(1)}%
          </span>
        ) : (
          <span className="text-[11px] text-text-muted shrink-0 w-16 text-right">—</span>
        )}

        <span className={cn("flex items-center gap-1 text-[11px] font-medium shrink-0 w-20 justify-end", meta.color)}>
          <StatusIcon size={12} />
          {meta.label}
        </span>
      </button>

      {open && (
        <div className="mt-2 ml-6 pl-3 border-l border-bg-border text-[11px] space-y-1">
          <div className="grid grid-cols-2 gap-x-6 gap-y-1">
            <div>
              <span className="text-text-muted">Logged at: </span>
              <span className="text-text-secondary tabular-nums">{item.created_at}</span>
            </div>
            <div>
              <span className="text-text-muted">Price at call: </span>
              <span className="text-text-secondary tabular-nums">${item.price_at_call.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-text-muted">Window: </span>
              <span className="text-text-secondary">{item.prediction_window_days} days</span>
            </div>
            {item.evaluated_at && (
              <div>
                <span className="text-text-muted">Graded at: </span>
                <span className="text-text-secondary tabular-nums">{item.evaluated_at}</span>
              </div>
            )}
            {item.price_now !== null && (
              <div>
                <span className="text-text-muted">Price now: </span>
                <span className="text-text-secondary tabular-nums">${item.price_now.toFixed(2)}</span>
              </div>
            )}
          </div>
          {item.context && Object.keys(item.context).length > 0 && (
            <div>
              <div className="text-text-muted mt-2 mb-0.5">Inputs at decision time:</div>
              <ul className="text-text-secondary space-y-0.5">
                {Object.entries(item.context).map(([k, v]) => (
                  <li key={k} className="tabular-nums">
                    <span className="text-text-muted">{k}: </span>
                    <span>{v === null ? "—" : typeof v === "number" ? v.toString() : String(v)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </li>
  );
}
