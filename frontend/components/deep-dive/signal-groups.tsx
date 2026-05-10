"use client";

import type { SignalRow } from "@/lib/api/types";
import { cn } from "@/lib/utils";

function colorClasses(color: string) {
  const map: Record<string, { ring: string; text: string; bar: string }> = {
    blue:    { ring: "ring-accent-blue/30",     text: "text-accent-blue",       bar: "bg-accent-blue" },
    violet:  { ring: "ring-accent-violet/30",   text: "text-accent-violet",     bar: "bg-accent-violet" },
    cyan:    { ring: "ring-accent-cyan/30",     text: "text-accent-cyan",       bar: "bg-accent-cyan" },
    amber:   { ring: "ring-accent-amber/30",    text: "text-accent-amber",      bar: "bg-accent-amber" },
    pink:    { ring: "ring-accent-pink/30",     text: "text-accent-pink",       bar: "bg-accent-pink" },
    green:   { ring: "ring-accent-green/30",    text: "text-accent-greenSoft",  bar: "bg-accent-greenSoft" },
    red:     { ring: "ring-accent-red/30",      text: "text-accent-redSoft",    bar: "bg-accent-redSoft" },
    neutral: { ring: "ring-bg-border",          text: "text-text-secondary",   bar: "bg-zinc-600" },
  };
  return map[color] || map.neutral;
}

function directionTone(d: SignalRow["direction"]) {
  if (d === "bullish") return { label: "Bullish", text: "text-accent-greenSoft", bg: "bg-accent-green/10 border-accent-green/30" };
  if (d === "bearish") return { label: "Bearish", text: "text-accent-redSoft",   bg: "bg-accent-red/10 border-accent-red/30" };
  return { label: "Neutral", text: "text-text-secondary", bg: "bg-bg-card border-bg-border" };
}

function CategoryBlock({ category, signals }: { category: string; signals: SignalRow[] }) {
  if (signals.length === 0) return null;
  const head = signals[0];
  const colors = colorClasses(head.color);
  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-3 pb-3 border-b border-bg-border">
        <span className="text-xl">{head.icon}</span>
        <h3 className={cn("text-sm font-semibold", colors.text)}>{category}</h3>
        <span className="text-[10px] uppercase tracking-wider text-text-muted ml-auto">
          {signals.length} signal{signals.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="space-y-3">
        {signals.map((s, i) => {
          const tone = directionTone(s.direction);
          return (
            <div key={i}>
              <div className="flex items-center justify-between mb-1.5 gap-2">
                <span className="text-sm font-medium truncate">{s.name}</span>
                <span className={cn("badge shrink-0", tone.bg, tone.text)}>
                  {tone.label}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-bg-base border border-bg-border rounded-full overflow-hidden">
                  <div
                    className={cn("h-full", colors.bar)}
                    style={{ width: `${Math.round(s.strength * 100)}%` }}
                  />
                </div>
                <span className="text-[10px] tabular-nums text-text-muted w-8 text-right">
                  {Math.round(s.strength * 100)}%
                </span>
              </div>
              {s.explanation && (
                <p className="text-xs text-text-secondary mt-1.5 leading-relaxed line-clamp-3">
                  {s.explanation}
                </p>
              )}
              {s.why && (
                <p className="text-[11px] text-text-muted mt-1 italic">Why: {s.why}</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function SignalGroups({ groups }: { groups: Record<string, SignalRow[]> }) {
  const entries = Object.entries(groups);
  if (entries.length === 0) {
    return (
      <div className="card p-6 text-text-muted text-sm">
        No signals match the current filter.
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {entries.map(([category, signals]) => (
        <CategoryBlock key={category} category={category} signals={signals} />
      ))}
    </div>
  );
}
