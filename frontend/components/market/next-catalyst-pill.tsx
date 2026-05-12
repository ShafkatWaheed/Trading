"use client";

import type { CalendarEvent } from "@/lib/api/types";
import { Clock, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  nextEvent?: CalendarEvent | null;
  nextHighImpact?: CalendarEvent | null;
};

function impactTone(impact: string): { color: string; bg: string; border: string } {
  if (impact === "high") return {
    color: "text-accent-amber", bg: "bg-accent-amber/5", border: "border-accent-amber/40",
  };
  if (impact === "medium") return {
    color: "text-accent-blue", bg: "bg-accent-blue/5", border: "border-accent-blue/30",
  };
  return { color: "text-text-secondary", bg: "bg-bg-base", border: "border-bg-borderHi" };
}

function daysLabel(days: number): string {
  if (days <= 0) return "today";
  if (days === 1) return "tomorrow";
  if (days <= 6) return `in ${days} days`;
  if (days <= 13) return "this week";
  if (days <= 20) return "in ~2 weeks";
  return `in ${days} days`;
}

export function NextCatalystPill({ nextEvent, nextHighImpact }: Props) {
  // Prefer high-impact if it's within a week; otherwise use the most-imminent event
  const pick =
    nextHighImpact && (nextHighImpact.days_away ?? 99) <= 7
      ? nextHighImpact
      : nextEvent;

  if (!pick) return null;

  const tone = impactTone(pick.impact);

  return (
    <div className={cn("card p-3 mb-3 border-l-4 flex items-center gap-3 flex-wrap", tone.border)}>
      <div className={cn("shrink-0 w-9 h-9 rounded-lg grid place-items-center text-lg", tone.bg)}>
        {pick.icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold flex items-center gap-1">
            <Clock size={10} /> Next catalyst
          </span>
          <span className={cn("text-[10px] uppercase tracking-wider font-semibold", tone.color)}>
            {pick.impact} impact
          </span>
        </div>
        <div className="text-sm font-semibold text-text-primary mt-0.5 flex items-center gap-2 flex-wrap">
          <span>{pick.name}</span>
          <span className={cn("text-xs font-normal", tone.color)}>
            {daysLabel(pick.days_away)}
          </span>
          <span className="text-[11px] text-text-muted tabular-nums">· {pick.date}</span>
        </div>
        {pick.warning && (
          <p className={cn("text-[11px] leading-snug mt-0.5 flex items-start gap-1", tone.color)}>
            <AlertCircle size={11} className="mt-0.5 shrink-0" />
            {pick.warning}
          </p>
        )}
      </div>
    </div>
  );
}
