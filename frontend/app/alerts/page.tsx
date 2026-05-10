"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Trash2, AlertTriangle, AlertCircle, Info, ArrowUpRight } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { alertsApi } from "@/lib/api/endpoints";
import type { AlertItem } from "@/lib/api/types";
import { cn, formatRelativeTime } from "@/lib/utils";

function severityIcon(s: string) {
  if (s === "critical") return AlertTriangle;
  if (s === "warning") return AlertCircle;
  return Info;
}

function severityTone(s: string) {
  if (s === "critical") return {
    text: "text-accent-redSoft", bg: "bg-accent-red/10",
    border: "border-l-accent-red/60", chip: "badge-red",
    glow: "card-glow-amber",
  };
  if (s === "warning") return {
    text: "text-accent-amber", bg: "bg-accent-amber/10",
    border: "border-l-accent-amber/60", chip: "badge-amber",
    glow: "",
  };
  return {
    text: "text-accent-blue", bg: "bg-accent-blue/10",
    border: "border-l-accent-blue/40", chip: "badge-blue",
    glow: "",
  };
}

function AlertCard({ a }: { a: AlertItem }) {
  const tone = severityTone(a.severity);
  const Icon = severityIcon(a.severity);
  return (
    <div className={cn("card p-4 border-l-[3px]", tone.border, tone.glow)}>
      <div className="flex items-start gap-3">
        <div className={cn(
          "w-8 h-8 rounded-lg grid place-items-center shrink-0 ring-1 ring-inset ring-white/5",
          tone.bg,
        )}>
          <Icon size={14} className={tone.text} strokeWidth={2.4} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {a.symbol && (
              <Link
                href={`/deep-dive/${a.symbol}`}
                className="font-mono font-semibold text-sm hover:text-accent-violet transition-colors"
              >
                {a.symbol}
              </Link>
            )}
            <span className={cn("badge text-[10px]", tone.chip)}>
              {a.severity.toUpperCase()}
            </span>
            <span className="text-[10px] text-text-muted uppercase tracking-wider font-medium">
              {a.alert_type.replace(/_/g, " ")}
            </span>
            <span className="text-[11px] text-text-muted ml-auto tabular-nums">
              {a.created_at ? formatRelativeTime(a.created_at) : "—"}
            </span>
          </div>
          <p className="text-[13px] text-text-secondary mt-1.5 leading-relaxed">{a.message}</p>
          {(a.old_value || a.new_value) && (
            <p className="text-[11px] text-text-muted mt-2 font-mono inline-flex items-center gap-1.5">
              {a.old_value ? <span className="line-through opacity-70">{a.old_value}</span> : null}
              {a.old_value && a.new_value ? <span className="text-text-dim">→</span> : ""}
              {a.new_value ? <span className="text-text-secondary">{a.new_value}</span> : null}
            </p>
          )}
        </div>
        {a.symbol && (
          <Link href={`/deep-dive/${a.symbol}`} className="text-text-muted hover:text-accent-blue self-center">
            <ArrowUpRight size={14} />
          </Link>
        )}
      </div>
    </div>
  );
}

export default function AlertsPage() {
  const qc = useQueryClient();

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ["alerts"],
    queryFn: () => alertsApi.list(100),
    staleTime: 30_000,
  });

  const clearMutation = useMutation({
    mutationFn: () => alertsApi.clearAll(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["alerts", "summary"] });
    },
  });

  return (
    <div>
      <PageHeader
        icon={Bell}
        title="Alerts"
        subtitle="Verdict changes, risk shifts, and notable events from the scheduler."
        accent="text-accent-amber"
        iconBg="bg-accent-amber/10"
      />

      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="text-[11px] uppercase tracking-wider text-text-muted font-semibold">
          {alerts.length} alert{alerts.length === 1 ? "" : "s"}
        </div>
        {alerts.length > 0 && (
          <Button
            tone="red"
            variant="outline"
            size="sm"
            leftIcon={<Trash2 size={12} />}
            onClick={() => clearMutation.mutate()}
            loading={clearMutation.isPending}
          >
            Clear all
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)}
        </div>
      ) : alerts.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="No alerts"
          description="The scheduler raises alerts when verdicts change, risk shifts, or earnings approach."
          tone="amber"
        />
      ) : (
        <div className="space-y-2">
          {alerts.map((a, i) => <AlertCard key={a.id ?? i} a={a} />)}
        </div>
      )}
    </div>
  );
}
