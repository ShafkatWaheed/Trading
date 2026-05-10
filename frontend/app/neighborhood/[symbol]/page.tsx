"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Network,
  ArrowUp,
  ArrowDown,
  GitBranch,
  Repeat,
  Plus,
  ArrowLeft,
  Loader2,
  Info,
  ExternalLink,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { graphApi } from "@/lib/api/endpoints";
import type { NeighborEdge, Tier } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const TIER_TONE: Record<
  Tier,
  { badge: string; ring: string }
> = {
  A: { badge: "badge-amber", ring: "ring-accent-amber/40" },
  B: { badge: "badge-blue", ring: "ring-accent-blue/40" },
  C: { badge: "badge-zinc", ring: "ring-bg-borderHi/40" },
  D: { badge: "badge-zinc", ring: "ring-bg-border/40" },
};

const CONFIDENCE_TONE: Record<string, string> = {
  high: "badge-green",
  medium: "badge-blue",
  low: "badge-zinc",
};

function tierBadge(t: Tier | null) {
  if (!t) return <span className="badge badge-zinc text-[9px]">?</span>;
  const tone = TIER_TONE[t];
  return (
    <span className={cn("badge text-[10px] tabular-nums px-1.5 py-0.5", tone.badge)}>
      {t}
    </span>
  );
}

function NeighborChip({ edge, role }: { edge: NeighborEdge; role: string }) {
  const isNegative = edge.polarity < 0;
  return (
    <Link
      href={`/neighborhood/${encodeURIComponent(edge.symbol)}`}
      className={cn(
        "block card p-3 hover:bg-bg-card2 transition-colors group",
        isNegative ? "border-l-[3px] border-l-accent-red/50" : ""
      )}
      title={edge.evidence ?? edge.edge_type}
    >
      <div className="flex items-center gap-2 flex-wrap">
        {tierBadge(edge.tier)}
        <span className="font-mono text-[13px] font-semibold tabular-nums group-hover:text-accent-violet">
          {edge.symbol}
        </span>
        {edge.name && (
          <span className="text-[11px] text-text-muted truncate max-w-[180px]">
            {edge.name}
          </span>
        )}
        <ExternalLink size={10} className="text-text-muted ml-auto opacity-0 group-hover:opacity-100" />
      </div>
      <div className="flex items-center gap-2 mt-1.5">
        <div className="flex items-center gap-1 flex-1 min-w-0">
          <div className="flex-1 h-1 bg-bg-border rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full",
                isNegative ? "bg-accent-red" : "bg-accent-cyan"
              )}
              style={{ width: `${Math.abs(edge.strength) * 100}%` }}
            />
          </div>
          <span className="text-[10px] tabular-nums text-text-muted">
            {(edge.strength * 100).toFixed(0)}
          </span>
        </div>
        {edge.confidence && (
          <span
            className={cn(
              "badge text-[9px] px-1 py-0",
              CONFIDENCE_TONE[edge.confidence] ?? "badge-zinc"
            )}
          >
            {edge.confidence}
          </span>
        )}
      </div>
      {edge.evidence && (
        <div className="text-[10px] text-text-muted mt-1.5 line-clamp-2">
          {edge.evidence.replace(/^seed:hand\s*\|?\s*/, "").replace(/^10k_mined:\s*/, "")}
        </div>
      )}
    </Link>
  );
}

function Panel({
  title,
  icon: Icon,
  edges,
  emptyText,
  accentClass,
}: {
  title: string;
  icon: typeof Network;
  edges: NeighborEdge[];
  emptyText: string;
  accentClass: string;
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon size={14} className={accentClass} strokeWidth={2.4} />
        <h3 className="text-[13px] font-semibold tracking-tight">
          {title}
        </h3>
        <span className="text-[10px] text-text-muted ml-auto tabular-nums">
          {edges.length}
        </span>
      </div>
      {edges.length === 0 ? (
        <div className="text-[11px] text-text-muted italic py-3 text-center">
          {emptyText}
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {edges.map((e) => (
            <NeighborChip key={`${e.edge_type}-${e.symbol}`} edge={e} role={title} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function NeighborhoodPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const resolved = use(params);
  const symbol = (resolved.symbol || "").toUpperCase();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["graph", "neighborhood", symbol],
    queryFn: () => graphApi.neighborhood(symbol),
    staleTime: 60_000,
    enabled: Boolean(symbol),
  });

  return (
    <div>
      <PageHeader
        icon={Network}
        title={data?.tier ? `${symbol} — ${data.name ?? ""}` : symbol}
        subtitle={
          data?.tier
            ? `Tier ${data.tier} · ${data.sector ?? "—"} · 1-hop graph neighborhood`
            : "Loading…"
        }
        accent="text-accent-violet"
        iconBg="bg-accent-violet/10"
        trailing={
          <Link
            href="/news-impact"
            className="text-[11px] text-text-secondary hover:text-text-primary inline-flex items-center gap-1"
          >
            <ArrowLeft size={12} />
            News Impact
          </Link>
        }
      />

      {isLoading && (
        <div className="grid gap-3 grid-cols-1 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[200px] w-full" />
          ))}
        </div>
      )}

      {isError && (
        <div className="card p-4 border-l-[3px] border-l-accent-red/70">
          <div className="text-[13px] text-accent-redSoft">
            Failed to fetch neighborhood. Make sure the API is running on :8000.
          </div>
        </div>
      )}

      {data && data.tier === null && (
        <div className="card p-8 grid place-items-center text-center">
          <Info size={18} className="text-text-muted mb-2" />
          <div className="text-[13px] font-medium">{symbol} not in our universe</div>
          <div className="text-[11px] text-text-muted mt-1 max-w-md">
            This stock isn't loaded into <code className="font-mono">stocks_universe</code> yet.
            The Tier A spine has 160 names; Tier B/C/D arrive after the network refresh
            (yfinance industry pull + ETF holdings).
          </div>
          <Link
            href="/universe"
            className="mt-4 text-[12px] text-accent-violet hover:underline inline-flex items-center gap-1"
          >
            Browse the universe <ExternalLink size={11} />
          </Link>
        </div>
      )}

      {data && data.tier !== null && (
        <>
          {/* Layout: suppliers (top), customers (bottom), peers + substitutes + complements (right column on lg) */}
          <div className="grid gap-3 grid-cols-1 lg:grid-cols-3">
            {/* Left column: Suppliers (up), Customers (down) */}
            <div className="space-y-3 lg:col-span-2">
              <Panel
                title="Suppliers"
                icon={ArrowUp}
                edges={data.suppliers}
                emptyText="No supplier edges yet — load the spine + run 10-K extraction."
                accentClass="text-accent-amber"
              />
              <Panel
                title="Customers"
                icon={ArrowDown}
                edges={data.customers}
                emptyText="No customer edges recorded for this stock."
                accentClass="text-accent-green"
              />
            </div>

            {/* Right column: Peers, Substitutes, Complements */}
            <div className="space-y-3">
              <Panel
                title="Peers"
                icon={GitBranch}
                edges={data.peers}
                emptyText="No peers — Tier A is hand-curated; Tier B/C arrives via Claude batches."
                accentClass="text-accent-violet"
              />
              {data.substitutes.length > 0 && (
                <Panel
                  title="Substitutes"
                  icon={Repeat}
                  edges={data.substitutes}
                  emptyText=""
                  accentClass="text-accent-red"
                />
              )}
              {data.complements.length > 0 && (
                <Panel
                  title="Complements"
                  icon={Plus}
                  edges={data.complements}
                  emptyText=""
                  accentClass="text-accent-cyan"
                />
              )}
            </div>
          </div>

          {/* Source legend / footer */}
          <div className="card p-3 mt-4 text-[10px] text-text-muted leading-relaxed">
            <span className="font-semibold text-text-secondary">Edge sources:</span>{" "}
            <span className="font-mono">seed:hand</span> = curated spine ·{" "}
            <span className="font-mono">10k_mined</span> = SEC 10-K Item 1A extraction ·{" "}
            <span className="font-mono">claude_batch</span> = per-industry LLM ranker ·
            substitutes carry negative polarity (zero-sum).
          </div>
        </>
      )}
    </div>
  );
}
