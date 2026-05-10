"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock,
  Eye,
  Pin,
  RefreshCw,
  Shuffle,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { freshnessApi } from "@/lib/api/endpoints";
import type { FreshnessQueueRow } from "@/lib/api/types";
import { cn, formatRelativeTime } from "@/lib/utils";

const STATUS_TONE: Record<
  string,
  { label: string; badge: string; icon: typeof Activity; color: string }
> = {
  fresh:        { label: "Fresh",         badge: "badge-green",  icon: CheckCircle2, color: "text-accent-green" },
  aging:        { label: "Aging",         badge: "badge-amber",  icon: Clock,        color: "text-accent-amber" },
  needs_review: { label: "Needs Review",  badge: "badge-red",    icon: AlertCircle,  color: "text-accent-red" },
  stale:        { label: "Stale",         badge: "badge-zinc",   icon: AlertCircle,  color: "text-text-muted" },
};

const REASON_LABELS: Record<string, string> = {
  decay: "Edge has decayed past half-life — re-extract recommended",
  hash_change: "Business summary changed (M&A / segment reorg / spinoff)",
  peer_decoupling: "Stock decoupled from its tagged peers — identity may have shifted",
  news_tag_drift: "Recent news skews toward a different domain than current tags",
};

function reasonText(reason: string | null): string {
  if (!reason) return "—";
  if (reason.startsWith("new_filing:")) {
    const forms = reason.slice("new_filing:".length);
    return `New SEC filing(s): ${forms}`;
  }
  return REASON_LABELS[reason] ?? reason;
}

function ActionButton({
  label,
  icon: Icon,
  onClick,
  loading,
  tone = "default",
}: {
  label: string;
  icon: typeof RefreshCw;
  onClick: () => void;
  loading: boolean;
  tone?: "default" | "primary";
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={cn(
        "inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-md border transition-colors",
        tone === "primary"
          ? "bg-accent-violet/10 hover:bg-accent-violet/20 text-accent-violet border-accent-violet/30"
          : "bg-bg-card2 hover:bg-bg-card text-text-secondary hover:text-text-primary border-bg-border",
        loading && "opacity-50 cursor-not-allowed"
      )}
    >
      <Icon size={11} />
      {label}
    </button>
  );
}

function QueueRow({ row }: { row: FreshnessQueueRow }) {
  const qc = useQueryClient();

  const ack = useMutation({
    mutationFn: (action: "re_extract" | "skip_30d" | "pin_current") =>
      freshnessApi.acknowledge(row.symbol, action),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["freshness", "queue"] }),
  });

  return (
    <div className="card p-3 border-l-[3px] border-l-accent-red/60">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <Link
            href={`/neighborhood/${encodeURIComponent(row.symbol)}`}
            className="font-mono text-[14px] font-semibold tabular-nums hover:text-accent-violet"
          >
            {row.symbol}
          </Link>
          <span className="badge badge-red text-[10px]">
            {STATUS_TONE.needs_review.label}
          </span>
          {row.flagged_at && (
            <span className="text-[10px] text-text-muted">
              flagged {formatRelativeTime(row.flagged_at)}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          <ActionButton
            label="Re-extract"
            icon={RefreshCw}
            onClick={() => ack.mutate("re_extract")}
            loading={ack.isPending}
            tone="primary"
          />
          <ActionButton
            label="Skip 30d"
            icon={Clock}
            onClick={() => ack.mutate("skip_30d")}
            loading={ack.isPending}
          />
          <ActionButton
            label="Pin"
            icon={Pin}
            onClick={() => ack.mutate("pin_current")}
            loading={ack.isPending}
          />
        </div>
      </div>

      <div className="text-[11px] text-text-secondary mt-2 leading-relaxed">
        <span className="text-text-dim">Reason:</span> {reasonText(row.trigger_reason)}
      </div>

      {row.last_extracted_at && (
        <div className="text-[10px] text-text-muted mt-1 font-mono">
          last extracted: {formatRelativeTime(row.last_extracted_at)}
        </div>
      )}
    </div>
  );
}

export default function FreshnessPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["freshness", "queue"],
    queryFn: () => freshnessApi.queue(),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const queueLength = data?.queue.length ?? 0;

  return (
    <div>
      <PageHeader
        icon={Eye}
        title="Edge Freshness"
        subtitle="Stocks flagged by the 5-layer freshness system. Review and act."
        accent="text-accent-cyan"
        iconBg="bg-accent-cyan/10"
      />

      {/* Status histogram */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
          {(["fresh", "aging", "needs_review", "stale"] as const).map((status) => {
            const tone = STATUS_TONE[status];
            const count = data.counts_by_status[status] ?? 0;
            return (
              <div key={status} className="card p-3">
                <div className="flex items-center gap-1.5">
                  <tone.icon size={11} className={tone.color} strokeWidth={2.4} />
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">
                    {tone.label}
                  </div>
                </div>
                <div className={cn("text-xl font-semibold tabular-nums mt-1", tone.color)}>
                  {count}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-[80px] w-full" />
          ))}
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="card p-4 border-l-[3px] border-l-accent-red/70">
          <div className="text-[13px] text-accent-redSoft">
            Failed to fetch the freshness queue. Make sure the API is running on :8000.
          </div>
        </div>
      )}

      {/* Empty queue */}
      {data && queueLength === 0 && (
        <div className="card p-8 grid place-items-center text-center">
          <CheckCircle2 size={28} className="text-accent-green mb-3" strokeWidth={2.2} />
          <div className="text-[14px] font-medium">No stocks need review</div>
          <div className="text-[11px] text-text-muted mt-1 max-w-md">
            Run the orchestrator (<code className="font-mono">src.freshness.orchestrator</code>)
            to scan for hash changes, new filings, and decayed edges.
          </div>
        </div>
      )}

      {/* Queue */}
      {data && queueLength > 0 && (
        <>
          <div className="text-[11px] text-text-muted mb-3 flex items-center gap-1.5">
            <Shuffle size={11} />
            {queueLength} stock{queueLength === 1 ? "" : "s"} flagged for review
          </div>
          <div className="space-y-2">
            {data.queue.map((row) => (
              <QueueRow key={row.symbol} row={row} />
            ))}
          </div>
        </>
      )}

      {/* Footer: layer documentation */}
      <div className="card p-3 mt-4 text-[10px] text-text-muted leading-relaxed">
        <div className="font-semibold text-text-secondary mb-1">5-layer freshness system</div>
        <div className="grid sm:grid-cols-2 gap-1.5">
          <div>
            <span className="font-mono text-accent-cyan">Layer 1 · decay</span> —
            edges fade over time (half-life 540 days)
          </div>
          <div>
            <span className="font-mono text-accent-cyan">Layer 2 · hash diff</span> —
            yfinance business summary changed
          </div>
          <div>
            <span className="font-mono text-accent-cyan">Layer 3 · filing trigger</span> —
            new 10-K/Q/8-K from SEC EDGAR
          </div>
          <div>
            <span className="font-mono text-accent-cyan">Layer 4 · correlation drift</span> —
            stock decoupled from tagged peers
          </div>
          <div>
            <span className="font-mono text-accent-cyan">Layer 5 · news tag drift</span> —
            recent news skews to different domain
          </div>
        </div>
      </div>
    </div>
  );
}
