"use client";

import type { GeopoliticalEvent } from "@/lib/api/types";
import { Globe, ExternalLink, ChevronDown, ShieldCheck } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useState } from "react";
import { cn } from "@/lib/utils";

const TYPE_LABELS: Record<string, string> = {
  tariff: "Tariffs & Trade Policy",
  war: "Conflicts & Sanctions",
  natural_disaster: "Natural Disasters",
  supply_chain: "Supply Chain Disruptions",
};

function severityTone(s: GeopoliticalEvent["severity"]) {
  return s === "high"
    ? { border: "border-l-accent-red/60", chip: "bg-accent-red/10 text-accent-redSoft border-accent-red/30" }
    : { border: "border-l-accent-amber/60", chip: "bg-accent-amber/10 text-accent-amber border-accent-amber/30" };
}

function EventCard({ e }: { e: GeopoliticalEvent }) {
  const [open, setOpen] = useState(false);
  const tone = severityTone(e.severity);
  return (
    <div className={cn("card p-4 border-l-4", tone.border)}>
      <div className="flex items-start gap-3">
        <div className="text-2xl shrink-0">{e.icon}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={cn("badge", tone.chip)}>
              {e.severity === "high" ? "HIGH SEVERITY" : "MODERATE"}
            </span>
            <span className="text-xs text-text-muted uppercase tracking-wider">{e.type.replace("_", " ")}</span>
          </div>
          <h4 className="text-sm font-semibold text-text-primary mt-1.5">{e.title}</h4>
          {e.snippet && (
            <p className="text-xs text-text-secondary mt-1 line-clamp-2">{e.snippet}</p>
          )}

          <button
            onClick={() => setOpen((v) => !v)}
            className="mt-3 text-xs text-text-muted hover:text-text-primary inline-flex items-center gap-1"
          >
            <ChevronDown size={12} className={cn("transition-transform", open && "rotate-180")} />
            {open ? "Hide" : "Show"} sector impact
          </button>

          {open && (
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              {e.negative_sectors.length > 0 && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-accent-redSoft mb-1">
                    Negative impact
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {e.negative_sectors.map((s) => (
                      <span key={s} className="badge bg-accent-red/10 text-accent-redSoft border-accent-red/30">{s}</span>
                    ))}
                  </div>
                </div>
              )}
              {e.positive_sectors.length > 0 && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-accent-greenSoft mb-1">
                    Positive impact
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {e.positive_sectors.map((s) => (
                      <span key={s} className="badge bg-accent-green/10 text-accent-greenSoft border-accent-green/30">{s}</span>
                    ))}
                  </div>
                </div>
              )}
              {e.explanation && (
                <p className="md:col-span-2 text-text-secondary leading-relaxed">{e.explanation}</p>
              )}
              {e.url && (
                <a
                  href={e.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="md:col-span-2 inline-flex items-center gap-1 text-text-muted hover:text-accent-blue"
                >
                  <ExternalLink size={11} /> Source
                </a>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function GeopoliticalRisks({ events, loading }: { events?: GeopoliticalEvent[]; loading?: boolean }) {
  if (loading) return <Skeleton className="h-72" />;

  if (!events || events.length === 0) {
    return (
      <div className="card p-6 border-l-4 border-accent-green/40 flex items-center gap-3">
        <ShieldCheck size={20} className="text-accent-greenSoft" />
        <div>
          <div className="text-sm font-semibold text-accent-greenSoft">All Clear</div>
          <p className="text-text-muted text-xs mt-0.5">
            No major geopolitical risks detected. Markets operating in a low-threat environment.
          </p>
        </div>
      </div>
    );
  }

  // Threat-level summary
  const highCount = events.filter((e) => e.severity === "high").length;
  const threat =
    highCount >= 3
      ? { level: "ELEVATED", color: "text-accent-redSoft", border: "border-accent-red/40", bg: "bg-accent-red/5", label: "Multiple high-impact events active" }
      : highCount >= 1
      ? { level: "HEIGHTENED", color: "text-accent-amber", border: "border-accent-amber/40", bg: "bg-accent-amber/5", label: "Some high-impact events detected" }
      : { level: "NORMAL", color: "text-accent-greenSoft", border: "border-accent-green/40", bg: "bg-accent-green/5", label: "No critical events — monitoring ongoing" };

  // Group by category
  const grouped: Record<string, GeopoliticalEvent[]> = {};
  for (const e of events) {
    (grouped[e.type] ||= []).push(e);
  }

  return (
    <div className="space-y-4">
      <div className={cn("card p-4 border", threat.border, threat.bg, "flex items-center justify-between")}>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Threat Level</div>
          <div className={cn("text-xl font-bold mt-0.5", threat.color)}>{threat.level}</div>
        </div>
        <div className="text-right">
          <div className="text-sm text-text-secondary">{threat.label}</div>
          <div className="text-xs text-text-muted mt-0.5">
            {events.length} event{events.length === 1 ? "" : "s"} across {Object.keys(grouped).length} categor{Object.keys(grouped).length === 1 ? "y" : "ies"}
          </div>
        </div>
      </div>

      {Object.entries(grouped).map(([type, items]) => (
        <div key={type}>
          <h3 className="text-xs uppercase tracking-wider text-text-muted mb-2">
            {TYPE_LABELS[type] || type}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {items.map((e, i) => <EventCard key={i} e={e} />)}
          </div>
        </div>
      ))}
    </div>
  );
}
