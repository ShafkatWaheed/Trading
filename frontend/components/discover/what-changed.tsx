"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Sparkles, ArrowUp, ArrowDown, Plus, Minus, RotateCw } from "lucide-react";
import type { OpportunityCard } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const KEY = "discover.snapshot.v1";

type Snapshot = {
  date: string;            // YYYY-MM-DD
  scores: Record<string, number>;  // symbol → score
};

type Diff = {
  added:    { symbol: string; score: number }[];
  removed:  { symbol: string; score: number }[];
  jumped:   { symbol: string; from: number; to: number; delta: number }[];
};

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function loadSnapshot(): Snapshot | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Snapshot;
  } catch {
    return null;
  }
}

function saveSnapshot(s: Snapshot): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {}
}

function computeDiff(prev: Snapshot, current: OpportunityCard[]): Diff {
  const currentScores: Record<string, number> = {};
  for (const op of current) currentScores[op.symbol] = op.score;

  const added: Diff["added"] = [];
  const removed: Diff["removed"] = [];
  const jumped: Diff["jumped"] = [];

  // Added: in current but not in prev
  for (const sym of Object.keys(currentScores)) {
    if (!(sym in prev.scores)) {
      added.push({ symbol: sym, score: currentScores[sym] });
    } else {
      const delta = currentScores[sym] - prev.scores[sym];
      if (Math.abs(delta) >= 5) {
        jumped.push({ symbol: sym, from: prev.scores[sym], to: currentScores[sym], delta });
      }
    }
  }
  // Removed: in prev but not in current
  for (const sym of Object.keys(prev.scores)) {
    if (!(sym in currentScores)) {
      removed.push({ symbol: sym, score: prev.scores[sym] });
    }
  }

  added.sort((a, b) => b.score - a.score);
  removed.sort((a, b) => b.score - a.score);
  jumped.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

  return {
    added:   added.slice(0, 5),
    removed: removed.slice(0, 5),
    jumped:  jumped.slice(0, 5),
  };
}

type Props = { ops: OpportunityCard[] };

export function WhatChanged({ ops }: Props) {
  const [diff, setDiff] = useState<Diff | null>(null);
  const [prevDate, setPrevDate] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!ops.length) return;
    const prev = loadSnapshot();
    const today = todayISO();

    if (prev && prev.date !== today) {
      const d = computeDiff(prev, ops);
      setDiff(d);
      setPrevDate(prev.date);
    } else if (prev && prev.date === today) {
      // Already snapshotted today — don't update, but show no diff
      setDiff(null);
      setPrevDate(null);
    } else {
      // First-ever snapshot, nothing to compare to
      setDiff(null);
      setPrevDate(null);
    }

    // Only save snapshot once per day (so deltas reflect day-over-day, not query-over-query)
    if (!prev || prev.date !== today) {
      saveSnapshot({
        date: today,
        scores: Object.fromEntries(ops.map((o) => [o.symbol, o.score])),
      });
    }
  }, [ops]);

  if (!diff || (diff.added.length === 0 && diff.removed.length === 0 && diff.jumped.length === 0)) {
    return null;
  }

  return (
    <section className="card p-4 border-l-4 border-accent-amber/50">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 text-left"
      >
        <Sparkles size={14} className="text-accent-amber" />
        <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
          What changed since {prevDate}
        </span>
        <span className="text-text-secondary text-xs">
          {diff.added.length} new · {diff.removed.length} dropped · {diff.jumped.length} jumped
        </span>
        <span className="ml-auto text-[10px] text-text-muted">{open ? "hide" : "show"}</span>
      </button>

      {open && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-3 pt-3 border-t border-bg-border">
          <Column title="New entries" tone="green" Icon={Plus}
                  rows={diff.added.map((r) => ({ symbol: r.symbol, primary: r.score.toFixed(0), secondary: "score" }))} />
          <Column title="Dropped off" tone="red" Icon={Minus}
                  rows={diff.removed.map((r) => ({ symbol: r.symbol, primary: r.score.toFixed(0), secondary: "was" }))} />
          <Column title="Biggest moves" tone="amber" Icon={RotateCw}
                  rows={diff.jumped.map((r) => ({
                    symbol: r.symbol,
                    primary: `${r.delta >= 0 ? "+" : ""}${r.delta.toFixed(0)}`,
                    secondary: `${r.from.toFixed(0)}→${r.to.toFixed(0)}`,
                    deltaTone: r.delta >= 0 ? "green" : "red" as const,
                  }))} />
        </div>
      )}
    </section>
  );
}

function Column({
  title, tone, Icon, rows,
}: {
  title: string; tone: "green" | "red" | "amber"; Icon: typeof Sparkles;
  rows: { symbol: string; primary: string; secondary: string; deltaTone?: "green" | "red" }[];
}) {
  const toneColor = tone === "green" ? "text-accent-greenSoft" : tone === "red" ? "text-accent-redSoft" : "text-accent-amber";
  return (
    <div>
      <div className={cn("flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-semibold mb-1.5", toneColor)}>
        <Icon size={10} strokeWidth={2.4} />
        {title}
      </div>
      {rows.length === 0 ? (
        <p className="text-[11px] text-text-muted">—</p>
      ) : (
        <ul className="space-y-1">
          {rows.map((r, i) => (
            <li key={i}>
              <Link
                href={`/deep-dive/${encodeURIComponent(r.symbol)}`}
                className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-bg-base transition-colors"
              >
                <span className="font-mono font-bold text-[12px] text-text-primary flex-1">{r.symbol}</span>
                <span className={cn(
                  "tabular-nums font-semibold text-[11px]",
                  r.deltaTone === "green" ? "text-accent-greenSoft" :
                  r.deltaTone === "red"   ? "text-accent-redSoft"   :
                  toneColor
                )}>
                  {r.primary}
                </span>
                <span className="text-[10px] text-text-muted tabular-nums w-12 text-right">{r.secondary}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
