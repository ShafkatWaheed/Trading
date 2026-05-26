"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  GitBranch, ArrowLeftCircle, ArrowRightCircle, Users, Swords, Puzzle,
} from "lucide-react";
import { graphApi } from "@/lib/api/endpoints";
import type { NeighborEdge } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

type LaneKey = "suppliers" | "customers" | "peers" | "substitutes" | "complements";

const LANE_META: Record<
  LaneKey,
  {
    label: string;
    Icon: typeof Users;
    accent: string;
    soft: string;
    direction: string;     // visual hint for the story
  }
> = {
  suppliers: {
    label: "Buys from",
    Icon: ArrowLeftCircle,
    accent: "text-accent-amber",
    soft:   "bg-accent-amber/[0.04] border-accent-amber/30",
    direction: "upstream",
  },
  customers: {
    label: "Sells to",
    Icon: ArrowRightCircle,
    accent: "text-accent-greenSoft",
    soft:   "bg-accent-green/[0.04] border-accent-green/30",
    direction: "downstream",
  },
  peers: {
    label: "Competes with",
    Icon: Users,
    accent: "text-accent-violet",
    soft:   "bg-accent-violet/[0.04] border-accent-violet/30",
    direction: "peer",
  },
  substitutes: {
    label: "Loses share to",
    Icon: Swords,
    accent: "text-accent-redSoft",
    soft:   "bg-accent-red/[0.04] border-accent-red/30",
    direction: "zero-sum",
  },
  complements: {
    label: "Moves with",
    Icon: Puzzle,
    accent: "text-accent-cyan",
    soft:   "bg-accent-cyan/[0.04] border-accent-cyan/30",
    direction: "paired",
  },
};

const LANE_ORDER: LaneKey[] = ["suppliers", "customers", "peers", "substitutes", "complements"];

function composeLede(
  symbol: string,
  counts: Record<LaneKey, NeighborEdge[]>,
): string {
  const total =
    counts.suppliers.length +
    counts.customers.length +
    counts.peers.length +
    counts.substitutes.length +
    counts.complements.length;

  if (total === 0) {
    return `${symbol} has no mapped supply-chain or peer relationships yet — the graph is sparse here.`;
  }

  const pieces: string[] = [];
  if (counts.suppliers.length)
    pieces.push(`depends on ${counts.suppliers.length} supplier${counts.suppliers.length === 1 ? "" : "s"}`);
  if (counts.customers.length)
    pieces.push(`sells into ${counts.customers.length} customer market${counts.customers.length === 1 ? "" : "s"}`);
  if (counts.peers.length)
    pieces.push(`competes with ${counts.peers.length} peer${counts.peers.length === 1 ? "" : "s"}`);
  if (counts.substitutes.length)
    pieces.push(`faces ${counts.substitutes.length} substitute${counts.substitutes.length === 1 ? "" : "s"}`);
  if (counts.complements.length)
    pieces.push(`moves alongside ${counts.complements.length} complement${counts.complements.length === 1 ? "" : "s"}`);

  // Top neighbour as a flavor anchor
  const topPeer = counts.peers[0] ?? counts.suppliers[0] ?? counts.customers[0];
  const anchor = topPeer ? ` Closest neighbor: ${topPeer.symbol}.` : "";

  return `${symbol} sits at the center of a ${total}-stock neighborhood — ${pieces.join(", ")}.${anchor}`;
}

function EdgeChip({ edge }: { edge: NeighborEdge }) {
  // Strength meter (0..1) — small visual bar after the ticker
  const pct = Math.max(8, Math.min(100, Math.round(edge.strength * 100)));
  return (
    <Link
      href={`/deep-dive/${encodeURIComponent(edge.symbol)}`}
      title={edge.evidence ?? `${edge.edge_type} · strength ${edge.strength.toFixed(2)}`}
      className="group block rounded-md border border-bg-border hover:border-text-secondary
                 bg-bg-base/40 hover:bg-bg-card2 p-2 transition-colors"
    >
      <div className="flex items-baseline justify-between gap-2 mb-1">
        <span className="font-mono font-bold text-sm text-text-primary">{edge.symbol}</span>
        {edge.tier && (
          <span className="text-[9px] uppercase tracking-wider text-text-muted">
            tier {edge.tier}
          </span>
        )}
      </div>
      {edge.name && (
        <p className="text-[11px] text-text-secondary truncate group-hover:text-text-primary">
          {edge.name}
        </p>
      )}
      <div className="mt-1.5 h-[3px] rounded-full bg-bg-border overflow-hidden">
        <div
          className="h-full bg-text-secondary group-hover:bg-text-primary transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </Link>
  );
}

function Lane({
  laneKey, edges,
}: { laneKey: LaneKey; edges: NeighborEdge[] }) {
  const meta = LANE_META[laneKey];
  const Icon = meta.Icon;

  return (
    <div className={cn("rounded-lg border p-3", meta.soft)}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <Icon size={12} className={meta.accent} />
          <span className={cn("text-[11px] font-semibold uppercase tracking-wider", meta.accent)}>
            {meta.label}
          </span>
        </div>
        <span className="text-[10px] font-numeric tabular-nums text-text-muted">
          {edges.length}
        </span>
      </div>

      {edges.length === 0 ? (
        <p className="text-[11px] text-text-muted italic py-3 text-center">
          none mapped
        </p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-1 gap-1.5">
          {edges.slice(0, 6).map((e) => (
            <EdgeChip key={`${laneKey}-${e.symbol}`} edge={e} />
          ))}
        </div>
      )}
    </div>
  );
}

export function NeighborhoodCard({ symbol }: Props) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["neighborhood", symbol],
    queryFn: () => graphApi.neighborhood(symbol),
    staleTime: 24 * 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <GitBranch size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">Connected To</h3>
        </div>
        <Skeleton className="h-64 w-full" />
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <GitBranch size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">Connected To</h3>
        </div>
        <p className="text-text-muted text-sm">
          {(error as Error)?.message || "Neighborhood graph unavailable."}
        </p>
      </section>
    );
  }

  const lanes = {
    suppliers: data.suppliers,
    customers: data.customers,
    peers: data.peers,
    substitutes: data.substitutes,
    complements: data.complements,
  };

  const lede = composeLede(symbol, lanes);
  const total =
    lanes.suppliers.length + lanes.customers.length + lanes.peers.length +
    lanes.substitutes.length + lanes.complements.length;

  return (
    <section className="card-subtle p-6 overflow-hidden relative">
      <div
        className="absolute inset-x-0 top-0 h-32 pointer-events-none opacity-60"
        style={{
          background:
            "radial-gradient(ellipse 60% 100% at 50% 0%, rgba(139, 92, 246, 0.08) 0%, transparent 70%)",
        }}
      />

      <div className="relative">
        <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
          <div className="flex items-center gap-2">
            <GitBranch size={16} className="text-accent-violet" />
            <h3 className="text-base font-semibold">Connected To</h3>
            {data.sector && (
              <span className="text-[10px] uppercase tracking-wider text-text-muted">
                · {data.sector}
              </span>
            )}
          </div>
          <span className="badge text-[10px] bg-accent-violet/10 text-accent-violet border-accent-violet/30">
            {total} edge{total === 1 ? "" : "s"}
          </span>
        </div>

        <p className="text-text-primary text-[15px] leading-relaxed italic mb-6 max-w-3xl">
          “{lede}”
        </p>

        {total === 0 ? (
          <p className="text-text-muted text-sm italic">
            No graph edges yet for {symbol}. Suppliers, customers, peers, and
            substitutes are extracted from 10-Ks and curated peer maps — coverage
            grows as we ingest more filings.
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {LANE_ORDER.map((k) => (
              <Lane key={k} laneKey={k} edges={lanes[k]} />
            ))}
          </div>
        )}

        <div className="mt-5 pt-3 border-t border-bg-border flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-text-muted">
          <span className="flex items-center gap-1">
            <ArrowLeftCircle size={10} className="text-accent-amber" /> Buys from
          </span>
          <span className="flex items-center gap-1">
            <ArrowRightCircle size={10} className="text-accent-greenSoft" /> Sells to
          </span>
          <span className="flex items-center gap-1">
            <Users size={10} className="text-accent-violet" /> Peer
          </span>
          <span className="flex items-center gap-1">
            <Swords size={10} className="text-accent-redSoft" /> Substitute
          </span>
          <span className="flex items-center gap-1">
            <Puzzle size={10} className="text-accent-cyan" /> Complement
          </span>
          <span className="ml-auto">Click any ticker to deep-dive.</span>
        </div>
      </div>
    </section>
  );
}
