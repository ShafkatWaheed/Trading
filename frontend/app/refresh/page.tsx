"use client";

import { useEffect, useMemo, useState } from "react";
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
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { refreshApi } from "@/lib/api/endpoints";
import type { RefreshJob, RefreshKindMeta } from "@/lib/api/types";
import { cn, formatRelativeTime } from "@/lib/utils";

const KIND_META: Record<
  string,
  { title: string; icon: typeof RefreshCw; accent: string; eta: string }
> = {
  universe:     { title: "Universe membership",  icon: Database,   accent: "text-accent-violet", eta: "~30s" },
  industries:   { title: "Industry tags",        icon: Tag,        accent: "text-accent-amber",  eta: "~3 hr" },
  conglomerate: { title: "Conglomerate tags",    icon: Layers,     accent: "text-accent-cyan",   eta: "<1s" },
  peers:        { title: "Peer ranking (B/C)",   icon: Users,      accent: "text-accent-blue",   eta: "hours" },
  causal:       { title: "Commodity exposures",  icon: Flame,      accent: "text-accent-pink",   eta: "hours" },
  tenk_mining:  { title: "10-K supply chain",    icon: FileText,   accent: "text-accent-green",  eta: "1-2 hr" },
  "13f_overlap":{ title: "13F overlap edges",    icon: Building2,  accent: "text-accent-violet", eta: "<1s" },
  freshness:    { title: "Freshness scan",       icon: Eye,        accent: "text-accent-cyan",   eta: "minutes" },
};

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

function JobCard({ kind, description }: { kind: string; description: string }) {
  const meta = KIND_META[kind] ?? { title: kind, icon: RefreshCw, accent: "text-text-secondary", eta: "" };
  const Icon = meta.icon;
  const qc = useQueryClient();

  // Pull latest job for this kind (set on mount, refreshed by trigger)
  const { data: latestMap } = useQuery({
    queryKey: ["refresh", "latest"],
    queryFn: () => refreshApi.latest(),
    refetchInterval: 4_000,
  });

  // The job we should be polling — either the active one we started, or the
  // latest one from the server-side index.
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
  // Conglomerate and 13F_overlap are instant — no meaningful progress
  const isIndeterminate = active && total === 0;

  return (
    <div className="card p-4 flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <div className={cn("w-9 h-9 rounded-lg grid place-items-center shrink-0", meta.accent, "bg-current/10")}>
          <Icon size={16} className={meta.accent} strokeWidth={2.2} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="text-[14px] font-semibold">{meta.title}</div>
            {badge && (
              <span className={cn("badge text-[10px] flex items-center gap-1", badge.cls)}>
                <badge.Icon size={10} className={active ? "animate-spin" : ""} />
                {badge.label}
              </span>
            )}
            {meta.eta && (
              <span className="text-[10px] text-text-muted font-mono">{meta.eta}</span>
            )}
          </div>
          <div className="text-[11px] text-text-secondary mt-0.5 leading-relaxed">{description}</div>
        </div>
        <button
          onClick={() => start.mutate()}
          disabled={active || start.isPending}
          className={cn(
            "inline-flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-md border transition-colors whitespace-nowrap shrink-0",
            active || start.isPending
              ? "bg-bg-card2 text-text-muted border-bg-border cursor-not-allowed"
              : "bg-accent-blue/10 hover:bg-accent-blue/20 text-accent-blue border-accent-blue/30",
          )}
        >
          <RefreshCw size={11} className={active ? "animate-spin" : ""} />
          {active ? "Running…" : "Run"}
        </button>
      </div>

      {/* Progress bar */}
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

      {/* Result line */}
      {job?.status === "done" && job.result_json && (
        <pre className="text-[10px] text-text-secondary bg-bg-card2 rounded p-2 overflow-x-auto font-mono leading-relaxed max-h-24">
          {(() => {
            try {
              const r = JSON.parse(job.result_json);
              return JSON.stringify(r, null, 2);
            } catch {
              return job.result_json;
            }
          })()}
        </pre>
      )}

      {/* Error line */}
      {job?.status === "failed" && job.error && (
        <div className="text-[10px] text-accent-redSoft bg-accent-red/10 rounded p-2 font-mono leading-relaxed max-h-24 overflow-y-auto">
          {job.error.split("\n").slice(0, 6).join("\n")}
        </div>
      )}
    </div>
  );
}

function QualityPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ["refresh", "quality"],
    queryFn: () => refreshApi.quality(),
    refetchInterval: 6_000,
  });

  if (isLoading || !data) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[60px] w-full" />
        ))}
      </div>
    );
  }

  const peerTotal = Object.values(data.peers.by_source).reduce((a, b) => a + b, 0);
  const relTotal = Object.values(data.relations.by_type).reduce((a, b) => a + b, 0);
  const expTotal = Object.values(data.commodity_exposures.by_source).reduce((a, b) => a + b, 0);
  const taggedPct = data.universe.total > 0
    ? Math.round((data.industries.tagged_symbols / data.universe.total) * 100)
    : 0;

  return (
    <div className="space-y-3">
      <div className="card p-3">
        <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Universe</div>
        <div className="text-[20px] tabular-nums font-semibold mt-0.5">
          {data.universe.total.toLocaleString()}
        </div>
        <div className="text-[10px] text-text-secondary mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {Object.entries(data.universe.by_tier)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([tier, n]) => (
              <span key={tier}>
                <span className="text-text-muted">Tier {tier}:</span> <span className="font-mono">{n.toLocaleString()}</span>
              </span>
            ))}
        </div>
      </div>

      <div className="card p-3">
        <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Industry coverage</div>
        <div className="text-[20px] tabular-nums font-semibold mt-0.5">{taggedPct}%</div>
        <div className="text-[10px] text-text-secondary mt-1">
          {data.industries.tagged_symbols.toLocaleString()} of {data.universe.total.toLocaleString()} symbols tagged · {data.industries.distinct_industries} industries
        </div>
      </div>

      <div className="card p-3">
        <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Peer edges</div>
        <div className="text-[20px] tabular-nums font-semibold mt-0.5">{peerTotal.toLocaleString()}</div>
        <div className="text-[10px] text-text-secondary mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {Object.entries(data.peers.by_source).map(([src, n]) => (
            <span key={src}>
              <span className="text-text-muted">{src}:</span> <span className="font-mono">{n.toLocaleString()}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="card p-3">
        <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Stock relations</div>
        <div className="text-[20px] tabular-nums font-semibold mt-0.5">{relTotal.toLocaleString()}</div>
        <div className="text-[10px] text-text-secondary mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {Object.entries(data.relations.by_type).map(([t, n]) => (
            <span key={t}>
              <span className="text-text-muted">{t}:</span> <span className="font-mono">{n.toLocaleString()}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="card p-3">
        <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Commodity exposures</div>
        <div className="text-[20px] tabular-nums font-semibold mt-0.5">{expTotal.toLocaleString()}</div>
        <div className="text-[10px] text-text-secondary mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {Object.entries(data.commodity_exposures.by_source).map(([src, n]) => (
            <span key={src}>
              <span className="text-text-muted">{src}:</span> <span className="font-mono">{n.toLocaleString()}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="card p-3">
        <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Institutional holdings</div>
        <div className="text-[20px] tabular-nums font-semibold mt-0.5">{data.institutional.holdings_total.toLocaleString()}</div>
        <div className="text-[10px] text-text-secondary mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {Object.entries(data.institutional.by_source).map(([src, n]) => (
            <span key={src}>
              <span className="text-text-muted">{src}:</span> <span className="font-mono">{n.toLocaleString()}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="card p-3">
        <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Freshness status</div>
        <div className="text-[10px] text-text-secondary mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {Object.keys(data.freshness.by_status).length === 0 ? (
            <span className="text-text-muted">no freshness checks yet — run the Freshness scan</span>
          ) : (
            Object.entries(data.freshness.by_status).map(([s, n]) => (
              <span key={s}>
                <span className="text-text-muted">{s}:</span> <span className="font-mono">{n.toLocaleString()}</span>
              </span>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default function RefreshPage() {
  const { data: kindsResp, isLoading } = useQuery({
    queryKey: ["refresh", "kinds"],
    queryFn: () => refreshApi.kinds(),
    staleTime: 60 * 60_000,
  });

  const kinds = useMemo(() => kindsResp?.kinds ?? [], [kindsResp]);

  // tailwind keyframe for indeterminate progress (one-time inject so we don't
  // need to touch globals.css)
  useEffect(() => {
    const id = "refresh-slide-keyframes";
    if (document.getElementById(id)) return;
    const style = document.createElement("style");
    style.id = id;
    style.textContent = `@keyframes slide { 0%{transform:translateX(-100%)} 100%{transform:translateX(400%)} }`;
    document.head.appendChild(style);
  }, []);

  return (
    <div>
      <PageHeader
        icon={RefreshCw}
        title="Refresh Graph"
        subtitle="Manually trigger each stage of the knowledge-graph pipeline. Watch progress, inspect results, check coverage on the right."
        accent="text-accent-blue"
        iconBg="bg-accent-blue/10"
      />

      <div className="grid lg:grid-cols-[1fr_320px] gap-4">
        {/* Left: refresh cards */}
        <div className="space-y-3">
          {isLoading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-[100px] w-full" />
            ))
          ) : (
            kinds.map((k: RefreshKindMeta) => (
              <JobCard key={k.kind} kind={k.kind} description={k.description} />
            ))
          )}
        </div>

        {/* Right: quality panel */}
        <div className="lg:sticky lg:top-20 lg:self-start">
          <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold mb-2">
            Quality snapshot
          </div>
          <QualityPanel />
        </div>
      </div>
    </div>
  );
}
