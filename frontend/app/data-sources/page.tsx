"use client";

import { useQuery } from "@tanstack/react-query";
import { Radio, CheckCircle2, AlertTriangle, XCircle, Infinity as InfinityIcon, Info } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { dataSourcesApi } from "@/lib/api/endpoints";
import type { DataSourceStatus, DataSourceStatusKind } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const TONE: Record<
  DataSourceStatusKind,
  {
    badge: string;
    label: string;
    icon: typeof CheckCircle2;
    iconColor: string;
    border: string;
  }
> = {
  ok: {
    badge: "badge-green",
    label: "OK",
    icon: CheckCircle2,
    iconColor: "text-accent-green",
    border: "border-l-accent-green/50",
  },
  warning: {
    badge: "badge-amber",
    label: "Near limit",
    icon: AlertTriangle,
    iconColor: "text-accent-amber",
    border: "border-l-accent-amber/60",
  },
  limited: {
    badge: "badge-red",
    label: "RATE LIMITED",
    icon: XCircle,
    iconColor: "text-accent-red",
    border: "border-l-accent-red/70",
  },
  untracked: {
    badge: "badge-zinc",
    label: "No Quota",
    icon: InfinityIcon,
    iconColor: "text-text-secondary",
    border: "border-l-bg-borderHi",
  },
};

// Per-source explanation of *why* it shows "No Quota"
const NO_QUOTA_REASON: Record<string, string> = {
  yahoo:    "Scraped — no published rate limit.",
  tavily:   "Plan-dependent — your tier determines the limit.",
  exa:      "Plan-dependent — your tier determines the limit.",
  congress: "Free MCP — no rate limit applies.",
};

function usageText(s: DataSourceStatus): string {
  if (s.capacity == null) return `${s.used} call${s.used === 1 ? "" : "s"}`;
  return `${s.used} / ${s.capacity}`;
}

function SourceRow({ s }: { s: DataSourceStatus }) {
  const tone = TONE[s.status];
  const Icon = tone.icon;
  const noQuotaReason = s.status === "untracked" ? NO_QUOTA_REASON[s.key] : undefined;
  return (
    <div className={cn("card p-4 border-l-[3px]", tone.border)}>
      <div className="flex items-center gap-4 flex-wrap">
        <div className="w-9 h-9 rounded-lg grid place-items-center shrink-0 ring-1 ring-inset ring-white/5 bg-bg-card2">
          <Icon size={16} className={tone.iconColor} strokeWidth={2.4} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-[14px]">{s.source}</span>
            <span className="text-[10px] text-text-muted font-mono">
              {s.key}
            </span>
          </div>
          <div className="text-[11px] text-text-muted mt-0.5">
            window: last {s.window_seconds}s
            {noQuotaReason && (
              <span className="ml-2 text-text-dim">· {noQuotaReason}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right tabular-nums">
            <div className="text-[13px] font-mono font-semibold">
              {usageText(s)}
            </div>
            <div className="text-[10px] text-text-muted">calls in window</div>
          </div>
          <span
            className={cn("badge text-[10px] whitespace-nowrap", tone.badge)}
            title={noQuotaReason || undefined}
          >
            {tone.label}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function DataSourcesPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["data-sources", "rate-limits"],
    queryFn: () => dataSourcesApi.rateLimits(),
    refetchInterval: 5_000,
    staleTime: 4_000,
  });

  return (
    <div>
      <PageHeader
        icon={Radio}
        title="Data Sources"
        subtitle="Live API rate-limit status across every provider."
        accent="text-accent-violet"
        iconBg="bg-accent-violet/10"
      />

      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 7 }).map((_, i) => (
            <Skeleton key={i} className="h-[68px] w-full" />
          ))}
        </div>
      )}

      {isError && (
        <div className="card p-4 border-l-[3px] border-l-accent-red/70">
          <div className="text-[13px] text-accent-redSoft">
            Failed to fetch rate-limit status. Is the API running on :8000?
          </div>
        </div>
      )}

      {data && (
        <>
          <div
            className={cn(
              "card p-4 mb-4 border-l-[3px]",
              data.any_limited
                ? "border-l-accent-red/70 card-glow-amber"
                : "border-l-accent-green/50"
            )}
          >
            <div className="flex items-center gap-3">
              {data.any_limited ? (
                <XCircle size={18} className="text-accent-red" strokeWidth={2.4} />
              ) : (
                <CheckCircle2 size={18} className="text-accent-green" strokeWidth={2.4} />
              )}
              <div className="text-[13px] font-medium">
                {data.any_limited
                  ? "One or more providers have hit their rate limit. Calls to those will fail or block until the window passes."
                  : "No provider is currently rate-limited."}
              </div>
            </div>
          </div>

          <div className="space-y-2">
            {data.sources.map((s) => (
              <SourceRow key={s.key} s={s} />
            ))}
          </div>

          <div className="card p-4 mt-4 flex items-start gap-3">
            <Info size={14} className="text-text-muted mt-0.5 shrink-0" strokeWidth={2} />
            <div className="text-[11px] text-text-secondary leading-relaxed">
              <div className="font-medium text-text-primary mb-1">All providers are tracked.</div>
              Calls are logged to the persistent <code className="font-mono text-text-muted">api_log</code> table by
              every process that talks to the data layer (api, dashboard, scripts).
              The <span className="font-medium text-text-secondary">“No Quota”</span> badge
              just means there's no published rate-limit number we can gauge against —
              the call count is still counted and shown for visibility.
              <div className="text-text-dim mt-1.5">Auto-refreshes every 5s.</div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
