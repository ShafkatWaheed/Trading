"use client";

/**
 * Unified Graph Health & Refresh page.
 *
 * Single-scroll surface that combines what was previously split across
 * /refresh and /edge-freshness:
 *
 *   1. HealthStrip   — compact row of metrics from /refresh/quality
 *   2. RefreshGrid   — 8 manual-refresh action cards
 *   3. ReviewQueue   — per-symbol freshness queue with bulk filter + per-row
 *                       Re-extract / Skip / Pin actions (now actually runs the
 *                       10-K extractor after the orchestrator wiring fix).
 *
 * The page polls /refresh/quality + /refresh/latest every few seconds so the
 * top strip stays live while a job runs in the background.
 */

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Database,
  Tag,
  Layers,
  Users,
  Flame,
  FileText,
  Building2,
  Eye,
  Clock,
  Pin,
  Network,
  Compass,
  TrendingDown,
  TrendingUp,
  Search,
  ArrowRight,
  Zap,
  Square,
  Newspaper,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { StrataMap } from "@/components/graph/strata-map";
import { freshnessApi, graphApi, refreshApi } from "@/lib/api/endpoints";
import type {
  ActiveTheme,
  DiscoverImpactResponse,
  FreshnessQueueRow,
  RefreshJob,
  RelevanceScoreItem,
} from "@/lib/api/types";
import { cn, formatRelativeTime } from "@/lib/utils";

// Curated commodity dropdown — covers the most-actionable trader themes.
// (32 commodities exist in the DB; this short list keeps the form focused.)
const COMMODITY_OPTIONS: { code: string; label: string }[] = [
  { code: "crude_oil",   label: "Crude Oil (WTI)" },
  { code: "brent_oil",   label: "Crude Oil (Brent)" },
  { code: "natural_gas", label: "Natural Gas" },
  { code: "gasoline",    label: "Gasoline" },
  { code: "uranium",     label: "Uranium" },
  { code: "copper",      label: "Copper" },
  { code: "gold",        label: "Gold" },
  { code: "silver",      label: "Silver" },
  { code: "steel",       label: "Steel" },
  { code: "aluminum",    label: "Aluminum" },
  { code: "lithium",     label: "Lithium" },
  { code: "corn",        label: "Corn" },
  { code: "wheat",       label: "Wheat" },
  { code: "coffee",      label: "Coffee" },
];

// ── refresh kind metadata ────────────────────────────────────────────

const KIND_META: Record<
  string,
  { title: string; icon: typeof RefreshCw; accent: string; eta: string }
> = {
  universe:     { title: "Universe membership",  icon: Database,   accent: "text-accent-violet", eta: "~30s" },
  nasdaq_listings: { title: "NASDAQ Capital (D)", icon: Database,   accent: "text-accent-blue",   eta: "~10s" },
  industries:   { title: "Industry tags",        icon: Tag,        accent: "text-accent-amber",  eta: "~3 hr" },
  conglomerate: { title: "Conglomerate tags",    icon: Layers,     accent: "text-accent-cyan",   eta: "<1s" },
  peers:        { title: "Peer ranking (B/C)",   icon: Users,      accent: "text-accent-blue",   eta: "hours" },
  causal:       { title: "Commodity exposures",  icon: Flame,      accent: "text-accent-pink",   eta: "hours" },
  tenk_mining:  { title: "10-K supply chain",    icon: FileText,   accent: "text-accent-green",  eta: "1-2 hr" },
  "13f_overlap":{ title: "13F overlap edges",    icon: Building2,  accent: "text-accent-violet", eta: "<1s" },
  "13f_holdings": { title: "13F holdings (SEC)",  icon: Building2,  accent: "text-accent-violet", eta: "~30s" },
  "discover_ciks": { title: "Discover institutions", icon: Building2, accent: "text-accent-cyan", eta: "~20s" },
  freshness:    { title: "Freshness scan",       icon: Eye,        accent: "text-accent-cyan",   eta: "minutes" },
  composite_confidence: { title: "Composite confidence (cheap)", icon: Zap, accent: "text-accent-amber", eta: "<5s" },
  correlation_backfill: { title: "Correlation channel (Tiingo)", icon: Square, accent: "text-accent-blue", eta: "5-10 min" },
  news_co_mention_backfill: { title: "News co-mention (Tavily/RSS)", icon: Newspaper, accent: "text-accent-pink", eta: "5-15 min" },
};

// ── freshness queue metadata ─────────────────────────────────────────

const REASON_LABELS: Record<string, string> = {
  decay: "Edge has decayed past half-life — re-extract recommended",
  hash_change: "Business summary changed (M&A / segment reorg / spinoff)",
  peer_decoupling: "Stock decoupled from its tagged peers",
  news_tag_drift: "Recent news skews toward a different domain than current tags",
};

function reasonText(reason: string | null): string {
  if (!reason) return "—";
  if (reason.startsWith("new_filing:")) {
    return `New SEC filing: ${reason.slice("new_filing:".length)}`;
  }
  return REASON_LABELS[reason] ?? reason;
}

// ── shared primitives ────────────────────────────────────────────────

function statusBadge(status: RefreshJob["status"]): { label: string; cls: string; Icon: typeof RefreshCw } {
  switch (status) {
    case "queued":  return { label: "Queued",  cls: "badge-zinc",  Icon: Loader2 };
    case "running": return { label: "Running", cls: "badge-amber", Icon: Loader2 };
    case "done":    return { label: "Done",    cls: "badge-green", Icon: CheckCircle2 };
    case "failed":  return { label: "Failed",  cls: "badge-red",   Icon: AlertCircle };
  }
}

function ProgressBar({ value, indeterminate }: { value: number; indeterminate: boolean }) {
  if (indeterminate) {
    return (
      <div className="relative h-1.5 bg-bg-card2 rounded overflow-hidden">
        <div className="absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-accent-blue to-transparent animate-[slide_1.4s_ease-in-out_infinite]" />
      </div>
    );
  }
  const pct = Math.max(0, Math.min(100, value * 100));
  return (
    <div className="h-1.5 bg-bg-card2 rounded overflow-hidden">
      <div
        className="h-full bg-gradient-to-r from-accent-blue via-accent-violet to-accent-pink transition-[width] duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

// ── 1. Health strip (compact, top) ───────────────────────────────────

function HealthStrip() {
  const { data, isLoading } = useQuery({
    queryKey: ["refresh", "quality"],
    queryFn: () => refreshApi.quality(),
    refetchInterval: 6_000,
  });

  if (isLoading || !data) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mb-5">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-[68px] w-full" />
        ))}
      </div>
    );
  }

  const peerTotal   = Object.values(data.peers.by_source).reduce((a, b) => a + b, 0);
  const relTotal    = Object.values(data.relations.by_type).reduce((a, b) => a + b, 0);
  const taggedPct   = data.universe.total > 0
    ? Math.round((data.industries.tagged_symbols / data.universe.total) * 100)
    : 0;
  const fresh       = data.freshness.by_status?.fresh ?? 0;
  const needsReview = data.freshness.by_status?.needs_review ?? 0;
  const universe    = data.universe.total;

  const cards: { label: string; value: string; sub?: string; tone: string }[] = [
    { label: "Universe",   value: universe.toLocaleString(),    sub: Object.entries(data.universe.by_tier).sort(([a],[b])=>a.localeCompare(b)).map(([t,n])=>`${t}:${n}`).join(" · "), tone: "text-accent-violet" },
    { label: "Peer edges", value: peerTotal.toLocaleString(),   sub: `${Object.keys(data.peers.by_source).length} source(s)`,                                                          tone: "text-accent-blue" },
    { label: "Relations",  value: relTotal.toLocaleString(),    sub: `${Object.keys(data.relations.by_type).length} type(s)`,                                                          tone: "text-accent-green" },
    { label: "Tagged",     value: `${taggedPct}%`,              sub: `${data.industries.tagged_symbols.toLocaleString()} / ${universe.toLocaleString()}`,                              tone: "text-accent-amber" },
    { label: "Fresh",      value: fresh.toLocaleString(),       sub: "edges current",                                                                                                  tone: "text-accent-greenSoft" },
    { label: "Needs review", value: needsReview.toLocaleString(), sub: needsReview > 0 ? "flagged below" : "all caught up",                                                            tone: needsReview > 0 ? "text-accent-red" : "text-text-muted" },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mb-5">
      {cards.map((c) => (
        <div key={c.label} className="card p-3">
          <div className="text-[10px] uppercase tracking-wider text-text-muted">{c.label}</div>
          <div className={cn("text-lg font-semibold tabular-nums mt-0.5", c.tone)}>{c.value}</div>
          {c.sub && <div className="text-[10px] text-text-secondary mt-0.5 truncate" title={c.sub}>{c.sub}</div>}
        </div>
      ))}
    </div>
  );
}

// ── 2. Refresh job card (one per kind) ───────────────────────────────

function JobCard({ kind, description }: { kind: string; description: string }) {
  const meta = KIND_META[kind] ?? { title: kind, icon: RefreshCw, accent: "text-text-secondary", eta: "" };
  const Icon = meta.icon;
  const qc = useQueryClient();

  const { data: latestMap } = useQuery({
    queryKey: ["refresh", "latest"],
    queryFn: () => refreshApi.latest(),
    refetchInterval: 4_000,
  });

  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const latestForKind = latestMap?.[kind] as RefreshJob | undefined;
  const trackedId = activeJobId ?? latestForKind?.id ?? null;

  const { data: job } = useQuery({
    queryKey: ["refresh", "job", trackedId],
    queryFn: () => refreshApi.job(trackedId as number),
    enabled: trackedId != null,
    refetchInterval: (q) => {
      const j = q.state.data;
      if (!j) return 4_000;
      return j.status === "queued" || j.status === "running" ? 2_000 : false;
    },
  });

  const start = useMutation({
    mutationFn: () => refreshApi.start(kind),
    onSuccess: (j) => {
      setActiveJobId(j.id);
      qc.invalidateQueries({ queryKey: ["refresh", "latest"] });
    },
  });

  const active = job?.status === "queued" || job?.status === "running";
  const badge = job ? statusBadge(job.status) : null;
  const progress = job?.progress ?? 0;
  const processed = job?.processed ?? 0;
  const total = job?.total ?? 0;
  const isIndeterminate = active && total === 0;

  return (
    <div className="card p-3.5 flex flex-col gap-2.5">
      <div className="flex items-start gap-3">
        <div className={cn("w-9 h-9 rounded-lg grid place-items-center shrink-0 bg-bg-card2", meta.accent)}>
          <Icon size={16} className={meta.accent} strokeWidth={2.2} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="text-[13px] font-semibold">{meta.title}</div>
            {badge && (
              <span className={cn("badge text-[10px] flex items-center gap-1", badge.cls)}>
                <badge.Icon size={10} className={active ? "animate-spin" : ""} />
                {badge.label}
              </span>
            )}
            {meta.eta && <span className="text-[10px] text-text-muted font-mono">{meta.eta}</span>}
          </div>
          <div className="text-[11px] text-text-secondary mt-0.5 leading-relaxed">{description}</div>
        </div>
        <button
          onClick={() => start.mutate()}
          disabled={active || start.isPending}
          className={cn(
            "inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded-md border transition-colors whitespace-nowrap shrink-0",
            active || start.isPending
              ? "bg-bg-card2 text-text-muted border-bg-border cursor-not-allowed"
              : "bg-accent-blue/10 hover:bg-accent-blue/20 text-accent-blue border-accent-blue/30",
          )}
        >
          <RefreshCw size={11} className={active ? "animate-spin" : ""} />
          {active ? "Running…" : "Run"}
        </button>
      </div>

      {(active || job?.status === "done") && (
        <div>
          <ProgressBar value={progress} indeterminate={isIndeterminate} />
          <div className="flex items-center justify-between mt-1.5 text-[10px] text-text-muted font-mono">
            <span>
              {isIndeterminate
                ? "in progress"
                : total > 0
                  ? `${processed.toLocaleString()} / ${total.toLocaleString()}`
                  : `${(progress * 100).toFixed(0)}%`}
            </span>
            {job?.finished_at && job.status === "done" && (
              <span>finished {formatRelativeTime(job.finished_at)}</span>
            )}
            {job?.started_at && active && (
              <span>started {formatRelativeTime(job.started_at)}</span>
            )}
          </div>
        </div>
      )}

      {job?.status === "failed" && job.error && (
        <div className="text-[10px] text-accent-redSoft bg-accent-red/10 rounded p-2 font-mono leading-relaxed max-h-20 overflow-y-auto">
          {job.error.split("\n").slice(0, 4).join("\n")}
        </div>
      )}
    </div>
  );
}

// ── 3. Review queue (per-symbol, filterable) ─────────────────────────

function QueueRow({ row }: { row: FreshnessQueueRow }) {
  const qc = useQueryClient();
  const ack = useMutation({
    mutationFn: (action: "re_extract" | "skip_30d" | "pin_current") =>
      freshnessApi.acknowledge(row.symbol, action),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["freshness", "queue"] }),
  });

  return (
    <div className="card p-2.5 border-l-[3px] border-l-accent-red/60">
      <div className="flex items-center gap-3 flex-wrap">
        <Link
          href={`/neighborhood/${encodeURIComponent(row.symbol)}`}
          className="font-mono text-[13px] font-semibold tabular-nums hover:text-accent-violet min-w-[60px]"
        >
          {row.symbol}
        </Link>
        <div className="text-[11px] text-text-secondary flex-1 min-w-0 truncate">
          {reasonText(row.trigger_reason)}
        </div>
        {row.flagged_at && (
          <span className="text-[10px] text-text-muted whitespace-nowrap">
            flagged {formatRelativeTime(row.flagged_at)}
          </span>
        )}
        <div className="flex items-center gap-1">
          <button
            onClick={() => ack.mutate("re_extract")}
            disabled={ack.isPending}
            className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded-md border border-accent-violet/30 bg-accent-violet/10 hover:bg-accent-violet/20 text-accent-violet disabled:opacity-50"
            title="Run the 10-K extractor on this symbol"
          >
            <RefreshCw size={10} className={ack.isPending ? "animate-spin" : ""} />
            Re-extract
          </button>
          <button
            onClick={() => ack.mutate("skip_30d")}
            disabled={ack.isPending}
            className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded-md border border-bg-border bg-bg-card2 hover:bg-bg-card text-text-secondary disabled:opacity-50"
            title="Defer review for 30 days"
          >
            <Clock size={10} /> Skip 30d
          </button>
          <button
            onClick={() => ack.mutate("pin_current")}
            disabled={ack.isPending}
            className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded-md border border-bg-border bg-bg-card2 hover:bg-bg-card text-text-secondary disabled:opacity-50"
            title="Mark as verified — stop flagging"
          >
            <Pin size={10} /> Pin
          </button>
        </div>
      </div>
    </div>
  );
}

function ReviewQueue() {
  const [reasonFilter, setReasonFilter] = useState<string>("all");
  const [showAll, setShowAll] = useState(false);
  const qcRoot = useQueryClient();

  // Bulk re-extract state — sequential through the filtered subset so we don't
  // hammer SEC + Claude in parallel. cancelRef lets us abort mid-run.
  const [bulk, setBulk] = useState<{
    running: boolean;
    done: number;
    total: number;
    errors: number;
    currentSymbol?: string;
  }>({ running: false, done: 0, total: 0, errors: 0 });
  const cancelRef = useRef(false);

  const { data, isLoading } = useQuery({
    queryKey: ["freshness", "queue"],
    queryFn: () => freshnessApi.queue(),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const queue = data?.queue ?? [];

  // Build reason buckets for the filter chips
  const buckets = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of queue) {
      const key = r.trigger_reason?.startsWith("new_filing:")
        ? "new_filing"
        : (r.trigger_reason ?? "unknown");
      m.set(key, (m.get(key) ?? 0) + 1);
    }
    return Array.from(m.entries()).sort((a, b) => b[1] - a[1]);
  }, [queue]);

  const filtered = useMemo(() => {
    if (reasonFilter === "all") return queue;
    return queue.filter((r) => {
      const key = r.trigger_reason?.startsWith("new_filing:") ? "new_filing" : (r.trigger_reason ?? "unknown");
      return key === reasonFilter;
    });
  }, [queue, reasonFilter]);

  const visible = showAll ? filtered : filtered.slice(0, 25);

  if (isLoading) {
    return (
      <div className="space-y-1.5">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-[44px] w-full" />
        ))}
      </div>
    );
  }

  if (queue.length === 0) {
    return (
      <div className="card p-6 grid place-items-center text-center">
        <CheckCircle2 size={24} className="text-accent-green mb-2" strokeWidth={2.2} />
        <div className="text-[13px] font-medium">No stocks need review</div>
        <div className="text-[11px] text-text-muted mt-1 max-w-md">
          Run the <span className="font-mono">Freshness scan</span> action above
          to populate the queue.
        </div>
      </div>
    );
  }

  const runBulkReExtract = async () => {
    if (bulk.running) return;
    const targets = filtered.map((r) => r.symbol);
    if (targets.length === 0) return;
    const ok = window.confirm(
      `Re-extract ${targets.length} stock${targets.length === 1 ? "" : "s"}?` +
      `\n\nEach one runs the SEC 10-K extractor + a Claude call via the local ` +
      `CLI (~5–15s per symbol). You can cancel mid-run.`,
    );
    if (!ok) return;

    cancelRef.current = false;
    setBulk({ running: true, done: 0, total: targets.length, errors: 0 });

    let done = 0;
    let errors = 0;
    for (const symbol of targets) {
      if (cancelRef.current) break;
      setBulk((b) => ({ ...b, currentSymbol: symbol }));
      try {
        await freshnessApi.acknowledge(symbol, "re_extract");
      } catch {
        errors += 1;
      }
      done += 1;
      setBulk({ running: true, done, total: targets.length, errors, currentSymbol: symbol });
    }

    setBulk({ running: false, done, total: targets.length, errors });
    qcRoot.invalidateQueries({ queryKey: ["freshness", "queue"] });
  };

  return (
    <div>
      {/* Filter chips + bulk-action button */}
      <div className="flex items-center gap-1.5 flex-wrap mb-2.5">
        <button
          onClick={() => setReasonFilter("all")}
          className={cn(
            "text-[10px] px-2 py-1 rounded-md border transition-colors",
            reasonFilter === "all"
              ? "bg-accent-blue/15 text-accent-blue border-accent-blue/30"
              : "bg-bg-card2 text-text-secondary border-bg-border hover:bg-bg-card",
          )}
        >
          all · {queue.length}
        </button>
        {buckets.map(([reason, count]) => (
          <button
            key={reason}
            onClick={() => setReasonFilter(reason)}
            className={cn(
              "text-[10px] px-2 py-1 rounded-md border transition-colors",
              reasonFilter === reason
                ? "bg-accent-blue/15 text-accent-blue border-accent-blue/30"
                : "bg-bg-card2 text-text-secondary border-bg-border hover:bg-bg-card",
            )}
          >
            {reason} · {count}
          </button>
        ))}

        {/* Bulk re-extract — acts on the filtered subset so users can scope first */}
        <div className="ml-auto flex items-center gap-2">
          {bulk.running ? (
            <>
              <span className="text-[10px] text-text-muted tabular-nums">
                {bulk.done}/{bulk.total}
                {bulk.errors > 0 && (
                  <span className="text-accent-redSoft ml-1">· {bulk.errors} err</span>
                )}
                {bulk.currentSymbol && (
                  <span className="text-text-secondary ml-1">· {bulk.currentSymbol}</span>
                )}
              </span>
              <button
                onClick={() => { cancelRef.current = true; }}
                className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded-md border border-accent-red/30 bg-accent-red/10 text-accent-redSoft hover:bg-accent-red/20"
              >
                <Square size={10} /> Cancel
              </button>
            </>
          ) : (
            <>
              {bulk.total > 0 && bulk.done === bulk.total && (
                <span className="text-[10px] text-text-muted">
                  done · {bulk.done - bulk.errors} ok
                  {bulk.errors > 0 && (
                    <span className="text-accent-redSoft ml-1">· {bulk.errors} err</span>
                  )}
                </span>
              )}
              <button
                onClick={runBulkReExtract}
                disabled={filtered.length === 0}
                className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded-md border border-accent-green/30 bg-accent-green/10 text-accent-greenSoft hover:bg-accent-green/20 disabled:opacity-50"
                title="Run the 10-K extractor on every stock matching the current filter"
              >
                <Zap size={10} /> Re-extract all ({filtered.length})
              </button>
            </>
          )}
        </div>
      </div>

      <div className="space-y-1.5">
        {visible.map((row) => (
          <QueueRow key={row.symbol} row={row} />
        ))}
      </div>

      {filtered.length > 25 && (
        <button
          onClick={() => setShowAll((v) => !v)}
          className="mt-2 text-[11px] text-accent-blue hover:underline"
        >
          {showAll
            ? `Show first 25`
            : `Show all ${filtered.length.toLocaleString()}`}
        </button>
      )}
    </div>
  );
}

// ── Discovery: trader-grade "what's impacted?" ───────────────────────

type DiscoverMode = "stock" | "commodity";

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.abs(score) * 100);
  const tone = score >= 0 ? "bg-accent-green" : "bg-accent-red";
  return (
    <div className="h-1 w-16 bg-bg-card2 rounded overflow-hidden shrink-0">
      <div className={cn("h-full transition-[width] duration-300", tone)} style={{ width: `${pct}%` }} />
    </div>
  );
}

function ResultRow({ row }: { row: RelevanceScoreItem }) {
  const pos = row.score >= 0;
  return (
    <div className="card p-2.5 flex items-center gap-3">
      <Link
        href={`/neighborhood/${encodeURIComponent(row.symbol)}`}
        className="font-mono text-[13px] font-semibold tabular-nums hover:text-accent-violet w-[64px] shrink-0"
      >
        {row.symbol}
      </Link>
      <span
        className={cn(
          "text-[11px] font-mono tabular-nums w-[52px] shrink-0",
          pos ? "text-accent-green" : "text-accent-red",
        )}
      >
        {pos ? "+" : ""}{row.score.toFixed(2)}
      </span>
      <ScoreBar score={row.score} />
      <div className="text-[11px] text-text-secondary flex-1 min-w-0 truncate" title={row.reasons.join(" · ")}>
        {row.reasons.length > 0 ? row.reasons.join(" · ") : "—"}
      </div>
    </div>
  );
}

function DiscoverImpact() {
  const [mode, setMode] = useState<DiscoverMode>("stock");
  const [stockInput, setStockInput] = useState("NVDA");
  const [commodity, setCommodity] = useState("crude_oil");
  const [direction, setDirection] = useState<"up" | "down">("down");
  const [intensity, setIntensity] = useState(1.0);
  const [result, setResult] = useState<DiscoverImpactResponse | null>(null);

  const discover = useMutation({
    mutationFn: () => {
      const theme: ActiveTheme =
        mode === "stock"
          ? { target_stock: stockInput.trim().toUpperCase(), direction, intensity }
          : { commodity_code: commodity, direction, intensity };
      // Default to today so historical-only edges (e.g. AAPL↔INTC, AXP↔COST)
      // don't pollute current-state queries. Backtest tools should pass an
      // older date explicitly.
      const today = new Date().toISOString().slice(0, 10);
      return graphApi.discoverImpact({
        active_themes: [theme],
        limit: 25,
        bullish_only: false,
        as_of: today,
      });
    },
    onSuccess: (r) => setResult(r),
  });

  const reflectedTheme = useMemo(() => {
    if (mode === "stock") {
      return `${stockInput.trim().toUpperCase() || "—"} ${direction === "up" ? "↑" : "↓"} · intensity ${intensity.toFixed(1)}`;
    }
    const label = COMMODITY_OPTIONS.find((c) => c.code === commodity)?.label ?? commodity;
    return `${label} ${direction === "up" ? "↑" : "↓"} · intensity ${intensity.toFixed(1)}`;
  }, [mode, stockInput, commodity, direction, intensity]);

  return (
    <section className="card p-4 mb-5">
      <div className="flex items-center gap-2 mb-3">
        <Compass size={16} className="text-accent-blue" strokeWidth={2.2} />
        <h2 className="text-[14px] font-semibold">Discover impact</h2>
        <span className="text-[11px] text-text-muted">
          — propose a shock, see who's hit (or helped) through the graph
        </span>
      </div>

      {/* Mode tabs */}
      <div className="inline-flex rounded-md border border-bg-border bg-bg-card2 p-0.5 mb-3">
        {(["stock", "commodity"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={cn(
              "px-3 py-1 text-[11px] font-medium rounded transition-colors",
              mode === m
                ? "bg-accent-blue/15 text-accent-blue"
                : "text-text-secondary hover:text-text-primary",
            )}
          >
            {m === "stock" ? "Stock shock" : "Commodity shock"}
          </button>
        ))}
      </div>

      {/* Input row */}
      <div className="flex items-end gap-2 flex-wrap mb-3">
        {mode === "stock" ? (
          <div>
            <label className="text-[10px] uppercase tracking-wider text-text-muted block mb-1">Symbol</label>
            <input
              value={stockInput}
              onChange={(e) => setStockInput(e.target.value.toUpperCase())}
              placeholder="NVDA"
              className="bg-bg-card2 border border-bg-border rounded-md px-2.5 py-1.5 text-[13px] font-mono w-[110px] focus:outline-none focus:border-accent-blue/50"
            />
          </div>
        ) : (
          <div>
            <label className="text-[10px] uppercase tracking-wider text-text-muted block mb-1">Commodity</label>
            <select
              value={commodity}
              onChange={(e) => setCommodity(e.target.value)}
              className="bg-bg-card2 border border-bg-border rounded-md px-2.5 py-1.5 text-[13px] w-[180px] focus:outline-none focus:border-accent-blue/50"
            >
              {COMMODITY_OPTIONS.map((c) => (
                <option key={c.code} value={c.code}>{c.label}</option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label className="text-[10px] uppercase tracking-wider text-text-muted block mb-1">Direction</label>
          <div className="inline-flex rounded-md border border-bg-border bg-bg-card2 p-0.5">
            <button
              onClick={() => setDirection("up")}
              className={cn(
                "px-2.5 py-1 text-[11px] font-medium rounded inline-flex items-center gap-1 transition-colors",
                direction === "up"
                  ? "bg-accent-green/15 text-accent-green"
                  : "text-text-secondary hover:text-text-primary",
              )}
            >
              <TrendingUp size={11} /> Up
            </button>
            <button
              onClick={() => setDirection("down")}
              className={cn(
                "px-2.5 py-1 text-[11px] font-medium rounded inline-flex items-center gap-1 transition-colors",
                direction === "down"
                  ? "bg-accent-red/15 text-accent-red"
                  : "text-text-secondary hover:text-text-primary",
              )}
            >
              <TrendingDown size={11} /> Down
            </button>
          </div>
        </div>

        <div>
          <label className="text-[10px] uppercase tracking-wider text-text-muted block mb-1">
            Intensity <span className="font-mono">{intensity.toFixed(1)}</span>
          </label>
          <input
            type="range"
            min={0.2} max={1.5} step={0.1}
            value={intensity}
            onChange={(e) => setIntensity(parseFloat(e.target.value))}
            className="w-[120px] h-[28px] accent-accent-blue"
          />
        </div>

        <button
          onClick={() => discover.mutate()}
          disabled={discover.isPending || (mode === "stock" && !stockInput.trim())}
          className="inline-flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-md border bg-accent-blue/10 hover:bg-accent-blue/20 text-accent-blue border-accent-blue/30 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Search size={11} className={discover.isPending ? "animate-spin" : ""} />
          {discover.isPending ? "Searching…" : "See impact"}
          {!discover.isPending && <ArrowRight size={11} />}
        </button>
      </div>

      {/* Results */}
      {result && (
        <div>
          <div className="text-[11px] text-text-muted mb-2">
            <span className="font-mono text-text-secondary">{reflectedTheme}</span>
            {" · "}
            {result.relevance.length === 0
              ? "no stocks reached above the relevance threshold"
              : `${result.relevance.length} of ${result.total.toLocaleString()} affected (ranked by |score|)`}
          </div>
          <div className="space-y-1.5">
            {result.relevance.slice(0, 25).map((row) => (
              <ResultRow key={row.symbol} row={row} />
            ))}
          </div>
        </div>
      )}

      {discover.isError && (
        <div className="text-[11px] text-accent-redSoft bg-accent-red/10 rounded p-2 mt-2">
          Failed to compute relevance. Make sure the API is running on :8000.
        </div>
      )}

      {!result && !discover.isPending && (
        <div className="text-[11px] text-text-muted italic">
          Pick a stock or commodity, set direction + intensity, then click <span className="text-text-secondary">See impact</span>.
        </div>
      )}
    </section>
  );
}

// ── Page ─────────────────────────────────────────────────────────────

export default function GraphPage() {
  // inject the indeterminate progress keyframe once
  useEffect(() => {
    const id = "graph-slide-keyframes";
    if (document.getElementById(id)) return;
    const style = document.createElement("style");
    style.id = id;
    style.textContent = `@keyframes slide { 0%{transform:translateX(-100%)} 100%{transform:translateX(400%)} }`;
    document.head.appendChild(style);
  }, []);

  return (
    <div>
      <PageHeader
        icon={Network}
        title="Graph"
        subtitle="Knowledge-graph health, manual refresh controls, and review queue — one page."
        accent="text-accent-blue"
        iconBg="bg-accent-blue/10"
      />

      {/* 0. discovery — trader-grade "what's impacted?" surface */}
      <DiscoverImpact />

      {/* 1. health strip */}
      <HealthStrip />

      {/* 2. refresh controls */}
      <section className="mb-6">
        <StrataMap />
      </section>

      {/* 3. review queue */}
      <section className="mb-6">
        <div className="flex items-baseline gap-2 mb-2.5">
          <h2 className="text-[12px] uppercase tracking-wider text-text-muted font-semibold">
            Review queue
          </h2>
          <span className="text-[10px] text-text-dim">
            stocks the freshness orchestrator wants you to re-extract — Re-extract now runs the 10-K extractor
          </span>
        </div>
        <ReviewQueue />
      </section>

      {/* footer: 5-layer doc */}
      <div className="card p-3 mt-4 text-[10px] text-text-muted leading-relaxed">
        <div className="font-semibold text-text-secondary mb-1">5-layer freshness system</div>
        <div className="grid sm:grid-cols-2 gap-1.5">
          <div><span className="font-mono text-accent-cyan">Layer 1 · decay</span> — edges fade over time (half-life 540 days)</div>
          <div><span className="font-mono text-accent-cyan">Layer 2 · hash diff</span> — yfinance business summary changed</div>
          <div><span className="font-mono text-accent-cyan">Layer 3 · filing trigger</span> — new 10-K or material 8-K (1.01 / 2.01 / 5.02)</div>
          <div><span className="font-mono text-accent-cyan">Layer 4 · correlation drift</span> — stock decoupled from tagged peers</div>
          <div><span className="font-mono text-accent-cyan">Layer 5 · news tag drift</span> — recent news skews to different domain</div>
        </div>
      </div>
    </div>
  );
}
