"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  /** Whether the backtest is currently running (mutation.isPending) */
  active: boolean;
  cycles: number;
  mode: "single" | "multi";
};

// Empirically measured wall times. Multi-mode is slow because running 7
// concurrent `claude` subprocesses slows each one down vs running alone
// (CPU + IO contention), so per-cycle is closer to ~60s on this box.
const SECONDS_PER_CYCLE = {
  single: 12,   // ~12s/cycle (one Claude call per cycle, 4-parallel batches)
  multi:  60,   // ~60s/cycle (7 personalities in parallel, contention slows each)
};

function fmtSec(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${r}s`;
}

/**
 * Honest time-based progress indicator. We can't know the exact server-side
 * state without streaming, so this is an estimate of how many cycles SHOULD be
 * done by now based on the typical per-cycle time. Resets on `active` rising
 * edge.
 */
export function AiProgressEstimator({ active, cycles, mode }: Props) {
  const [elapsedSec, setElapsedSec] = useState(0);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    if (!active) {
      startRef.current = null;
      setElapsedSec(0);
      return;
    }
    startRef.current = Date.now();
    setElapsedSec(0);
    const t = setInterval(() => {
      if (startRef.current) {
        setElapsedSec(Math.floor((Date.now() - startRef.current) / 1000));
      }
    }, 1000);
    return () => clearInterval(t);
  }, [active]);

  if (!active) return null;

  const perCycle = SECONDS_PER_CYCLE[mode];
  const expectedTotal = cycles * perCycle;
  // The first cycle takes ~Claude cold-start time; after that they overlap because
  // of parallelism. Use a slightly softer ramp:
  const estCyclesDone = Math.min(
    cycles - 1,
    Math.floor((elapsedSec / expectedTotal) * cycles)
  );
  const pct = Math.min(99, (elapsedSec / expectedTotal) * 100);
  const overrun = elapsedSec > expectedTotal * 1.2;

  // Stage messages — change every few seconds to feel alive
  let stage = "Pulling historical price + context";
  if (elapsedSec > 4)  stage = "Building per-cycle prompts (macro · indicators · fundamentals · news)";
  if (elapsedSec > 10) stage = mode === "multi"
    ? `Cycle ~${estCyclesDone + 1}/${cycles} — 7 personality agents deciding in parallel`
    : `Cycle ~${estCyclesDone + 1}/${cycles} — Claude reading context + deciding`;
  if (elapsedSec > expectedTotal * 0.7) stage = "Replaying decisions to track open/close trades";
  if (overrun) stage = "Taking longer than usual — Claude may be slow or rate-limited";

  return (
    <div className={cn(
      "mt-3 p-3 rounded-md border",
      overrun
        ? "bg-accent-amber/5 border-accent-amber/40"
        : mode === "multi"
          ? "bg-accent-violet/5 border-accent-violet/30"
          : "bg-accent-pink/5 border-accent-pink/30",
    )}>
      <div className="flex items-center gap-2 mb-2">
        <Bot size={13} className={mode === "multi" ? "text-accent-violet" : "text-accent-pink"} />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-text-secondary">
          AI Backtest in Progress
        </span>
        <span className="ml-auto text-[11px] text-text-muted flex items-center gap-1 tabular-nums">
          <Clock size={10} /> {fmtSec(elapsedSec)} / ~{fmtSec(expectedTotal)}
        </span>
      </div>

      {/* Indeterminate-feel progress bar */}
      <div className="h-1.5 rounded-full bg-bg-base overflow-hidden mb-2">
        <div
          className={cn(
            "h-full transition-all",
            overrun
              ? "bg-accent-amber"
              : mode === "multi"
                ? "bg-accent-violet"
                : "bg-accent-pink"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap text-[11px]">
        <span className="text-text-secondary">{stage}</span>
        <span className="text-text-muted tabular-nums">
          ~{estCyclesDone}/{cycles} cycles
        </span>
      </div>

      <p className="text-[10px] text-text-muted leading-snug mt-2 pt-2 border-t border-bg-border">
        Estimate based on typical per-cycle time ({perCycle}s {mode === "multi" ? "for 7-agent vote" : "per Claude call"}).
        Don't refresh — the run continues server-side and the result will pop in when complete.
      </p>
    </div>
  );
}
