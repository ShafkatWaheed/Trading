"use client";

import type { CalendarEvent } from "@/lib/api/types";
import { AlertTriangle, Calendar as CalendarIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/utils";

function urgencyTone(daysAway: number) {
  if (daysAway <= 2) {
    return {
      bg: "bg-accent-red/5",
      border: "border-accent-red/30",
      chip: "text-accent-redSoft",
      ring: "ring-accent-red/20",
    };
  }
  if (daysAway <= 7) {
    return {
      bg: "bg-accent-amber/5",
      border: "border-accent-amber/30",
      chip: "text-accent-amber",
      ring: "ring-accent-amber/20",
    };
  }
  return {
    bg: "bg-bg-card",
    border: "border-bg-divider",
    chip: "text-text-muted",
    ring: "ring-bg-border",
  };
}

function daysLabel(d: number) {
  if (d === 0) return "TODAY";
  if (d === 1) return "TOMORROW";
  return `${d}D`;
}

export function EconomicCalendar({ events, loading }: { events?: CalendarEvent[]; loading?: boolean }) {
  if (loading) return <Skeleton className="h-72" />;

  if (!events || events.length === 0) {
    return (
      <EmptyState
        icon={CalendarIcon}
        title="Calendar clear"
        description="No major economic events in the next 60 days."
        tone="blue"
      />
    );
  }

  return (
    <div className="space-y-2">
      {events.map((e, i) => {
        const tone = urgencyTone(e.days_away);
        return (
          <div
            key={i}
            className={cn(
              "rounded-xl p-4 border flex items-center gap-4 transition-all",
              tone.bg, tone.border,
              "hover:bg-opacity-80 hover:border-opacity-80",
            )}
          >
            <div className={cn(
              "w-10 h-10 rounded-lg grid place-items-center text-xl shrink-0 ring-1 ring-inset",
              tone.ring,
              "bg-bg-base/40",
            )}>
              {e.icon}
            </div>

            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-text-primary">{e.name}</div>
              <div className="text-[11px] text-text-muted mt-0.5 tabular-nums">{e.date}</div>
              {e.warning && (
                <div className="text-[11px] text-accent-amber mt-1.5 flex items-start gap-1.5">
                  <AlertTriangle size={11} className="mt-0.5 shrink-0" strokeWidth={2.4} />
                  <span className="leading-relaxed">{e.warning}</span>
                </div>
              )}
            </div>

            <div className="text-right shrink-0">
              <div className={cn("text-xs font-bold tracking-wider tabular-nums", tone.chip)}>
                {daysLabel(e.days_away)}
              </div>
              <div className={cn(
                "text-[10px] uppercase tracking-wider mt-0.5 font-medium",
                e.impact === "high" ? "text-accent-redSoft" : "text-accent-amber",
              )}>
                {e.impact} impact
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
