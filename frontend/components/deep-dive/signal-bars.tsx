"use client";

import type { SignalRow } from "@/lib/api/types";
import { cn } from "@/lib/utils";

function directionTone(d: SignalRow["direction"]) {
  switch (d) {
    case "bullish":
      return { bar: "bg-accent-green/60 border-accent-green/80", text: "text-accent-greenSoft", label: "Bullish" };
    case "bearish":
      return { bar: "bg-accent-red/60 border-accent-red/80", text: "text-accent-redSoft", label: "Bearish" };
    default:
      return { bar: "bg-zinc-700 border-zinc-600", text: "text-text-secondary", label: "Neutral" };
  }
}

export function SignalBars({ signals }: { signals: SignalRow[] }) {
  if (signals.length === 0) {
    return (
      <div className="card p-6 text-text-muted text-sm">No signals available for this stock.</div>
    );
  }
  return (
    <div className="card p-6">
      <h3 className="text-base font-semibold mb-4">Signals</h3>
      <div className="space-y-3">
        {signals.map((s, idx) => {
          const tone = directionTone(s.direction);
          return (
            <div key={idx} className="border-b border-bg-border pb-3 last:border-0 last:pb-0">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-sm font-medium">{s.name}</span>
                <span className={cn("text-xs uppercase tracking-wider", tone.text)}>
                  {tone.label}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex-1 h-2 bg-bg-card border border-bg-border rounded-full overflow-hidden">
                  <div
                    className={cn("h-full border-r", tone.bar)}
                    style={{ width: `${Math.round(s.strength * 100)}%` }}
                  />
                </div>
                <span className="text-xs text-text-muted tabular-nums w-10 text-right">
                  {Math.round(s.strength * 100)}%
                </span>
              </div>
              {s.explanation && (
                <p className="text-xs text-text-secondary mt-2 leading-relaxed">{s.explanation}</p>
              )}
              {s.why && (
                <p className="text-xs text-text-muted mt-1 italic">Why: {s.why}</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
