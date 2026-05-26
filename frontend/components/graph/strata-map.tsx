"use client";

/**
 * Strata Map — vertical layered view of the knowledge-graph refresh pipeline.
 *
 * The 11 refresh kinds form 5 strata that feed each other:
 *
 *   FOUNDATION  · universe                              ← the nodes themselves
 *   STRUCTURE   · industries · conglomerates            ← what each node IS
 *   EDGES       · peers · 10-K · commodity · 13F        ← edges between nodes
 *   INSIGHT     · composite (cheap) · correlation · news ← trust score per edge
 *   HEALTH      · freshness scan                        ← what needs work
 *
 * INSIGHT has three sibling kinds — all populate `composite_confidence`,
 * but each adds different channels (cheap=local only; correlation pulls
 * Tiingo returns; news pulls Tavily/Exa/RSS).
 *
 * Each stratum is a horizontal band with kind-node cards inside. Vertical
 * connector strips between bands flow with the upstream tone color, and
 * pulse when an upstream node is being hovered or actively running.
 */

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  RefreshCw, Database, Tag, Layers, Users, Flame, FileText, Building2,
  Eye, Zap, CheckCircle2, AlertCircle, Loader2,
  Square, Newspaper,
  type LucideIcon,
} from "lucide-react";
import { cn, formatRelativeTime } from "@/lib/utils";
import { freshnessApi, refreshApi } from "@/lib/api/endpoints";
import type { RefreshJob, RefreshQualitySnapshot } from "@/lib/api/types";

// ── stratum definition ───────────────────────────────────────────────

type Tone = "blue" | "green" | "amber" | "red";

type KindSpec = {
  key: string;
  title: string;
  icon: LucideIcon;
  tone: Tone;
  /** kind keys this depends on (drives the connector animation) */
  upstream: string[];
  /** Pull a one-line "live stat" from the quality snapshot. */
  liveStat: (q: RefreshQualitySnapshot, queueCount: number) => {
    primary: string;
    secondary?: string;
    warn?: boolean;
  };
};

type Stratum = {
  band: string;     // display label on left rail
  legend: string;   // small descriptive line under band label
  kinds: KindSpec[];
};

const sumValues = (rec?: Record<string, number>): number =>
  rec ? Object.values(rec).reduce((a, b) => a + b, 0) : 0;

// 10-K supplier/customer edges are stored as relation types in the graph.
const TENK_RELATION_TYPES = ["supplier", "customer", "joint_venture"];

const STRATA: Stratum[] = [
  {
    band: "FOUNDATION",
    legend: "the universe of nodes",
    kinds: [
      {
        key: "universe", title: "Universe membership", icon: Database, tone: "blue",
        upstream: [],
        liveStat: (q) => ({
          primary: q.universe.total.toLocaleString() + " stocks",
          secondary: Object.entries(q.universe.by_tier)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([t, n]) => `${t}:${n}`).join("·"),
        }),
      },
    ],
  },
  {
    band: "STRUCTURE",
    legend: "what each node is",
    kinds: [
      {
        key: "industries", title: "Industry tags", icon: Tag, tone: "amber",
        upstream: ["universe"],
        liveStat: (q) => {
          const total = q.universe.total || 1;
          const pct = Math.round((q.industries.tagged_symbols / total) * 100);
          return {
            primary: `${pct}% tagged`,
            secondary: `${q.industries.tagged_symbols.toLocaleString()} / ${total.toLocaleString()}`,
            warn: pct < 80,
          };
        },
      },
      {
        key: "conglomerate", title: "Conglomerate tags", icon: Layers, tone: "blue",
        upstream: ["industries"],
        liveStat: () => ({ primary: "rule overrides", secondary: "applied on industry tags" }),
      },
    ],
  },
  {
    band: "EDGES",
    legend: "relationships between nodes (four subgraphs)",
    kinds: [
      {
        key: "peers", title: "Peer graph", icon: Users, tone: "blue",
        upstream: ["industries"],
        liveStat: (q) => ({
          primary: sumValues(q.peers.by_source).toLocaleString() + " edges",
          secondary: `${Object.keys(q.peers.by_source).length} source(s)`,
        }),
      },
      {
        key: "tenk_mining", title: "10-K supply chain", icon: FileText, tone: "green",
        upstream: ["universe"],
        liveStat: (q, queueCount) => {
          const edges = TENK_RELATION_TYPES.reduce(
            (acc, t) => acc + (q.relations.by_type[t] ?? 0), 0,
          );
          return {
            primary: edges.toLocaleString() + " edges",
            secondary: queueCount > 0 ? `${queueCount} in review queue` : "supplier·customer·JV",
            warn: queueCount > 0,
          };
        },
      },
      {
        key: "causal", title: "Commodity exposures", icon: Flame, tone: "amber",
        upstream: ["universe"],
        liveStat: (q) => ({
          primary: sumValues(q.commodity_exposures.by_source).toLocaleString() + " stocks",
          secondary: "claude-mined per Tier A/B",
        }),
      },
      {
        key: "13f_overlap", title: "13F overlap", icon: Building2, tone: "blue",
        upstream: ["universe"],
        liveStat: (q) => ({
          primary: q.institutional.holdings_total.toLocaleString() + " holdings",
          secondary: `${sumValues(q.institutional.by_source).toLocaleString()} edges`,
        }),
      },
    ],
  },
  {
    band: "INSIGHT",
    legend: "per-edge trust — three alternatives populate composite_confidence",
    kinds: [
      {
        key: "composite_confidence", title: "Composite (cheap)", icon: Zap, tone: "amber",
        upstream: ["peers", "tenk_mining", "causal", "13f_overlap"],
        liveStat: (q) => {
          const total = sumValues(q.relations.by_type);
          return { primary: total.toLocaleString() + " scored", secondary: "hand·10-K·ETF — no network" };
        },
      },
      {
        key: "correlation_backfill", title: "Correlation channel", icon: Square, tone: "blue",
        upstream: ["peers", "tenk_mining", "causal", "13f_overlap"],
        liveStat: (q) => ({
          primary: sumValues(q.relations.by_type).toLocaleString() + " eligible",
          secondary: "Tiingo 60d r · 5-10 min",
        }),
      },
      {
        key: "news_co_mention_backfill", title: "News co-mention", icon: Newspaper, tone: "red",
        upstream: ["peers", "tenk_mining", "causal", "13f_overlap"],
        liveStat: (q) => ({
          primary: sumValues(q.relations.by_type).toLocaleString() + " eligible",
          secondary: "Tavily / Exa / RSS · 5-15 min",
        }),
      },
    ],
  },
  {
    band: "HEALTH",
    legend: "what needs re-extraction next",
    kinds: [
      {
        key: "freshness", title: "Freshness scan", icon: Eye, tone: "red",
        upstream: ["composite_confidence"],
        liveStat: (q, queueCount) => ({
          primary: queueCount.toLocaleString() + " in queue",
          secondary: `${(q.freshness.by_status?.fresh ?? 0).toLocaleString()} fresh`,
          warn: queueCount > 25,
        }),
      },
    ],
  },
];

// ── tone tokens — matches the 4-color palette discipline ─────────────

const TONE_TOKEN: Record<Tone, {
  bar: string; ring: string; text: string; bg: string; border: string;
}> = {
  blue:  { bar: "bg-accent-blue",     ring: "ring-accent-blue/40",  text: "text-accent-blueSoft",  bg: "bg-accent-blue/10",   border: "border-accent-blue/30"  },
  green: { bar: "bg-accent-green",    ring: "ring-accent-green/40", text: "text-accent-greenSoft", bg: "bg-accent-green/10",  border: "border-accent-green/30" },
  amber: { bar: "bg-accent-amber",    ring: "ring-accent-amber/40", text: "text-accent-amber",     bg: "bg-accent-amber/10",  border: "border-accent-amber/30" },
  red:   { bar: "bg-accent-red",      ring: "ring-accent-red/40",   text: "text-accent-redSoft",   bg: "bg-accent-red/10",    border: "border-accent-red/30"   },
};

// ── component ────────────────────────────────────────────────────────

export function StrataMap() {
  const [hovered, setHovered] = useState<string | null>(null);

  const { data: quality, isLoading: qLoading } = useQuery({
    queryKey: ["refresh", "quality"],
    queryFn: () => refreshApi.quality(),
    refetchInterval: 6_000,
  });

  const { data: latest } = useQuery({
    queryKey: ["refresh", "latest"],
    queryFn: () => refreshApi.latest(),
    refetchInterval: 4_000,
  });

  const { data: queueData } = useQuery({
    queryKey: ["freshness", "queue"],
    queryFn: () => freshnessApi.queue(),
    refetchInterval: 60_000,
  });
  const queueCount = queueData?.queue?.length ?? 0;

  // Map of every kind that's currently mid-run → highlighted active set
  const activeKinds = useMemo(() => {
    if (!latest) return new Set<string>();
    return new Set(
      Object.entries(latest)
        .filter(([_, j]) => j?.status === "queued" || j?.status === "running")
        .map(([k]) => k),
    );
  }, [latest]);

  // Build the set of downstream kinds for the currently-hovered kind, so we
  // can subtly highlight what would be affected if it ran. Walks the upstream
  // map in reverse.
  const downstreamOf = useMemo(() => {
    const map: Record<string, Set<string>> = {};
    for (const stratum of STRATA) {
      for (const k of stratum.kinds) {
        map[k.key] = map[k.key] ?? new Set();
        for (const up of k.upstream) {
          map[up] = map[up] ?? new Set();
          map[up].add(k.key);
        }
      }
    }
    // Transitive closure
    let changed = true;
    while (changed) {
      changed = false;
      for (const k of Object.keys(map)) {
        const before = map[k].size;
        for (const d of Array.from(map[k])) {
          for (const d2 of map[d] ?? []) map[k].add(d2);
        }
        if (map[k].size !== before) changed = true;
      }
    }
    return map;
  }, []);

  const highlightedSet = useMemo(() => {
    if (!hovered) return new Set<string>();
    const s = new Set<string>(downstreamOf[hovered] ?? []);
    s.add(hovered);
    return s;
  }, [hovered, downstreamOf]);

  return (
    <section
      className="relative"
      onMouseLeave={() => setHovered(null)}
      aria-label="Knowledge graph refresh pipeline"
    >
      <div className="flex items-baseline gap-2 mb-3">
        <h2 className="text-[12px] uppercase tracking-[0.18em] text-text-muted font-semibold font-display">
          Pipeline map
        </h2>
        <span className="text-[10px] text-text-dim">
          hover a node → see what it feeds · click Run to refresh that subgraph
        </span>
      </div>

      <div className="flex flex-col">
        {STRATA.map((stratum, i) => (
          <div key={stratum.band}>
            <Band
              stratum={stratum}
              quality={quality ?? null}
              qLoading={qLoading}
              latestMap={latest ?? null}
              queueCount={queueCount}
              hovered={hovered}
              setHovered={setHovered}
              highlightedSet={highlightedSet}
              activeKinds={activeKinds}
            />
            {i < STRATA.length - 1 && (
              <Tendrils
                fromKinds={stratum.kinds}
                toKinds={STRATA[i + 1].kinds}
                hovered={hovered}
                highlightedSet={highlightedSet}
                activeKinds={activeKinds}
              />
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

// ── one stratum band ─────────────────────────────────────────────────

function Band({
  stratum, quality, qLoading, latestMap, queueCount,
  hovered, setHovered, highlightedSet, activeKinds,
}: {
  stratum: Stratum;
  quality: RefreshQualitySnapshot | null;
  qLoading: boolean;
  latestMap: Record<string, RefreshJob> | null;
  queueCount: number;
  hovered: string | null;
  setHovered: (k: string | null) => void;
  highlightedSet: Set<string>;
  activeKinds: Set<string>;
}) {
  // A band that contains the focused kind gets a brighter rail.
  const bandFocused = stratum.kinds.some((k) => highlightedSet.has(k.key));

  return (
    <div className="grid grid-cols-[88px_1fr] gap-3">
      {/* Left rail with band name vertically stacked */}
      <div className="flex flex-col items-end pt-3">
        <div className={cn(
          "font-display text-[11px] tracking-[0.22em] font-semibold transition-colors",
          bandFocused ? "text-text-primary" : "text-text-muted",
        )}>
          {stratum.band}
        </div>
        <div className="text-[10px] text-text-dim text-right max-w-[88px] leading-snug mt-0.5">
          {stratum.legend}
        </div>
      </div>

      {/* Cards row */}
      <div className={cn(
        "grid gap-2.5 py-2",
        stratum.kinds.length === 1 && "grid-cols-1",
        stratum.kinds.length === 2 && "grid-cols-1 sm:grid-cols-2",
        stratum.kinds.length >= 3 && "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
      )}>
        {stratum.kinds.map((k) => (
          <KindNode
            key={k.key}
            spec={k}
            quality={quality}
            qLoading={qLoading}
            latest={latestMap?.[k.key] ?? null}
            queueCount={queueCount}
            isHovered={hovered === k.key}
            isHighlighted={highlightedSet.has(k.key)}
            isActive={activeKinds.has(k.key)}
            dimOthers={hovered !== null && !highlightedSet.has(k.key)}
            onHover={(on) => setHovered(on ? k.key : null)}
          />
        ))}
      </div>
    </div>
  );
}

// ── one kind node card ───────────────────────────────────────────────

function KindNode({
  spec, quality, qLoading, latest, queueCount,
  isHovered, isHighlighted, isActive, dimOthers, onHover,
}: {
  spec: KindSpec;
  quality: RefreshQualitySnapshot | null;
  qLoading: boolean;
  latest: RefreshJob | null;
  queueCount: number;
  isHovered: boolean;
  isHighlighted: boolean;
  isActive: boolean;
  dimOthers: boolean;
  onHover: (on: boolean) => void;
}) {
  const tone = TONE_TOKEN[spec.tone];
  const Icon = spec.icon;
  const qc = useQueryClient();

  const [trackedJobId, setTrackedJobId] = useState<number | null>(null);
  const liveJobId = trackedJobId ?? latest?.id ?? null;

  const { data: job } = useQuery({
    queryKey: ["refresh", "job", liveJobId],
    queryFn: () => refreshApi.job(liveJobId as number),
    enabled: liveJobId != null,
    refetchInterval: (q) => {
      const j = q.state.data;
      if (!j) return 4_000;
      return j.status === "queued" || j.status === "running" ? 2_000 : false;
    },
  });

  const start = useMutation({
    mutationFn: () => refreshApi.start(spec.key),
    onSuccess: (j) => {
      setTrackedJobId(j.id);
      qc.invalidateQueries({ queryKey: ["refresh", "latest"] });
    },
  });

  const active = job?.status === "queued" || job?.status === "running";
  const progress = job?.progress ?? 0;
  const stat = quality
    ? spec.liveStat(quality, queueCount)
    : { primary: qLoading ? "…" : "—", secondary: "" };
  const finishedAgo = latest?.finished_at ? formatRelativeTime(latest.finished_at) : null;

  return (
    <div
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      className={cn(
        "group relative card p-3 transition-all duration-200 overflow-hidden",
        "border", tone.border,
        isHighlighted && `ring-1 ${tone.ring}`,
        isHovered && "translate-y-[-1px]",
        dimOthers && "opacity-40",
        isActive && "ring-1 ring-accent-amber/40",
      )}
    >
      {/* Left tone stripe — the "track" indicator */}
      <div className={cn(
        "absolute left-0 top-2 bottom-2 w-[3px] rounded-r-full transition-opacity",
        tone.bar,
        isHighlighted || isActive ? "opacity-100" : "opacity-50",
      )} />

      {/* Active glow under card */}
      {isActive && (
        <div className="absolute inset-0 pointer-events-none animate-pulse bg-accent-amber/[0.04]" />
      )}

      <div className="flex items-start gap-2.5 pl-2 relative">
        <div className={cn(
          "w-7 h-7 rounded-md grid place-items-center shrink-0",
          tone.bg, "ring-1 ring-inset ring-white/5",
        )}>
          <Icon size={13} className={tone.text} strokeWidth={2.2} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <div className="text-[12px] font-semibold leading-tight truncate">{spec.title}</div>
            {stat.warn && (
              <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", "bg-accent-red animate-pulse")} />
            )}
          </div>
          <div className={cn("text-[14px] font-mono tabular-nums leading-tight mt-1", tone.text)}>
            {stat.primary}
          </div>
          {stat.secondary && (
            <div className="text-[10px] text-text-muted leading-tight mt-0.5 truncate">
              {stat.secondary}
            </div>
          )}
        </div>
        <RunButton
          tone={spec.tone}
          active={active}
          pending={start.isPending}
          onClick={() => start.mutate()}
        />
      </div>

      {/* Progress line under card content when active */}
      {active && (
        <div className="mt-2.5 pl-2">
          <div className="h-[2px] bg-bg-card2 rounded overflow-hidden">
            {job?.total ? (
              <div className={cn("h-full transition-[width] duration-500", tone.bar)} style={{ width: `${progress * 100}%` }} />
            ) : (
              <div className="h-full w-1/3 bg-gradient-to-r from-transparent via-accent-amber to-transparent animate-[slide_1.4s_ease-in-out_infinite]" />
            )}
          </div>
          <div className="flex items-center gap-2 mt-1 text-[9px] text-text-muted font-mono">
            <Loader2 size={9} className="animate-spin" />
            {job?.total
              ? `${job.processed.toLocaleString()} / ${job.total.toLocaleString()}`
              : "in progress"}
          </div>
        </div>
      )}

      {/* Footer: last-run ago */}
      {!active && finishedAgo && (
        <div className="flex items-center gap-1 mt-1.5 pl-2 text-[9px] text-text-dim font-mono">
          {latest?.status === "done" ? (
            <CheckCircle2 size={9} className="text-accent-greenSoft" />
          ) : latest?.status === "failed" ? (
            <AlertCircle size={9} className="text-accent-redSoft" />
          ) : null}
          {finishedAgo}
        </div>
      )}

      {/* Failure excerpt — only show on focus to avoid noise */}
      {!active && latest?.status === "failed" && latest.error && isHovered && (
        <div className="mt-2 pl-2 text-[10px] text-accent-redSoft bg-accent-red/5 rounded p-1.5 font-mono leading-tight max-h-12 overflow-hidden">
          {latest.error.split("\n")[0]}
        </div>
      )}
    </div>
  );
}

// ── inline run button ────────────────────────────────────────────────

function RunButton({
  tone, active, pending, onClick,
}: {
  tone: Tone; active: boolean; pending: boolean; onClick: () => void;
}) {
  const t = TONE_TOKEN[tone];
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      disabled={active || pending}
      className={cn(
        "shrink-0 self-start inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded-md border whitespace-nowrap transition-colors",
        active || pending
          ? "bg-bg-card2 text-text-muted border-bg-border cursor-not-allowed"
          : `${t.bg} ${t.text} ${t.border} hover:brightness-125`,
      )}
    >
      <RefreshCw size={9} className={active ? "animate-spin" : ""} />
      {active ? "Running" : "Run"}
    </button>
  );
}

// ── tendrils between two strata ──────────────────────────────────────

function Tendrils({
  fromKinds, toKinds, hovered, highlightedSet, activeKinds,
}: {
  fromKinds: KindSpec[];
  toKinds: KindSpec[];
  hovered: string | null;
  highlightedSet: Set<string>;
  activeKinds: Set<string>;
}) {
  // Build the set of (from, to) connections that actually exist based on
  // declared upstream dependencies between these two adjacent bands.
  const edges = useMemo(() => {
    const e: Array<{ from: KindSpec; to: KindSpec }> = [];
    for (const t of toKinds) {
      for (const f of fromKinds) {
        if (t.upstream.includes(f.key)) e.push({ from: f, to: t });
      }
    }
    return e;
  }, [fromKinds, toKinds]);

  // One thin vertical strip per edge, spaced evenly within the rail.
  return (
    <div className="grid grid-cols-[88px_1fr] gap-3" aria-hidden>
      <div /> {/* keeps alignment with the left rail */}
      <div className="relative h-6 flex items-stretch justify-center gap-1">
        {edges.map(({ from, to }, idx) => {
          const tone = TONE_TOKEN[from.tone];
          const live =
            activeKinds.has(from.key) ||
            (hovered != null && highlightedSet.has(from.key) && highlightedSet.has(to.key));
          return (
            <span
              key={`${from.key}-${to.key}-${idx}`}
              className={cn(
                "relative w-px transition-all duration-200",
                live ? tone.bar : "bg-bg-border",
                live ? "opacity-100" : "opacity-60",
              )}
              title={`${from.title} → ${to.title}`}
            >
              {live && (
                <span
                  className={cn(
                    "absolute left-1/2 -translate-x-1/2 w-[3px] h-2 rounded-full animate-[tendril_1.4s_ease-in-out_infinite]",
                    tone.bar,
                  )}
                />
              )}
            </span>
          );
        })}
      </div>
    </div>
  );
}
