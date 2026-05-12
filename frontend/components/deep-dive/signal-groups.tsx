"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUp, ArrowDown, Minus } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import type { SignalRow, SignalEvidenceItem } from "@/lib/api/types";
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
  if (d === "bullish") return {
    label: "Bullish", text: "text-accent-greenSoft",
    bg: "bg-accent-green/10 border-accent-green/30",
    Icon: ArrowUp, iconBg: "bg-accent-green/15 ring-accent-green/40 text-accent-greenSoft",
    whyLabel: "Why bullish",
  };
  if (d === "bearish") return {
    label: "Bearish", text: "text-accent-redSoft",
    bg: "bg-accent-red/10 border-accent-red/30",
    Icon: ArrowDown, iconBg: "bg-accent-red/15 ring-accent-red/40 text-accent-redSoft",
    whyLabel: "Why bearish",
  };
  return {
    label: "Neutral", text: "text-text-secondary",
    bg: "bg-bg-card border-bg-border",
    Icon: Minus, iconBg: "bg-bg-card2 ring-bg-borderHi text-text-secondary",
    whyLabel: "Why neutral",
  };
}

function gradeColor(g?: string | null): string {
  if (g === "A") return "text-accent-greenSoft border-accent-green/40 bg-accent-green/10";
  if (g === "B") return "text-accent-blue border-accent-blue/40 bg-accent-blue/10";
  if (g === "C") return "text-accent-amber border-accent-amber/40 bg-accent-amber/10";
  if (g === "D") return "text-accent-amberSoft border-accent-amber/40 bg-accent-amber/5";
  if (g === "F") return "text-accent-redSoft border-accent-red/40 bg-accent-red/10";
  return "text-text-muted border-bg-border bg-bg-base";
}

function EvidenceChip({ ev }: { ev: SignalEvidenceItem | undefined }) {
  if (!ev || ev.error || !ev.win_rate || !ev.total_trades || ev.total_trades < 3) return null;
  const wr = Math.round((ev.win_rate ?? 0) * 100);
  const ar = ev.avg_return_pct ?? 0;
  const arSign = ar >= 0 ? "+" : "";
  return (
    <div
      className="mt-1.5 flex items-center gap-2 text-[10px] tabular-nums"
      title={`Backtested on this stock: ${ev.total_trades} historical occurrences over ${ev.hold_days}d hold period.`}
    >
      <span className={cn("inline-block px-1.5 py-0.5 rounded border font-bold uppercase tracking-wider", gradeColor(ev.grade))}>
        {ev.grade}
      </span>
      <span className="text-text-muted">
        Historically:
        <span className="text-text-secondary font-semibold"> {wr}% win</span>
        <span className="text-text-dim"> · </span>
        <span className={cn("font-semibold", ar >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft")}>
          {arSign}{ar.toFixed(1)}% avg
        </span>
        <span className="text-text-dim"> · </span>
        <span>{ev.total_trades} occurrences over {ev.hold_days}d</span>
      </span>
    </div>
  );
}

function CategoryBlock({ category, signals, evidence }: { category: string; signals: SignalRow[]; evidence: Record<string, SignalEvidenceItem> }) {
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
          const Icon = tone.Icon;
          return (
            <div key={i}>
              <div className="flex items-center gap-2 mb-1.5">
                <span
                  className={cn(
                    "shrink-0 w-6 h-6 rounded-full grid place-items-center ring-1 ring-inset",
                    tone.iconBg
                  )}
                  aria-label={tone.label}
                  title={tone.label}
                >
                  <Icon size={12} strokeWidth={2.6} />
                </span>
                <span className="text-sm font-medium truncate flex-1">{s.name}</span>
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
              {(s.explanation || s.why) && (
                <div className="mt-1.5">
                  <span className={cn("text-[10px] uppercase tracking-wider font-semibold", tone.text)}>
                    {tone.whyLabel}
                  </span>
                  {s.explanation && (
                    <p className="text-xs text-text-secondary mt-0.5 leading-relaxed line-clamp-3">
                      {s.explanation}
                    </p>
                  )}
                  {s.why && (
                    <p className="text-[11px] text-text-muted mt-1 italic">{s.why}</p>
                  )}
                </div>
              )}
              <EvidenceChip ev={evidence[s.name]} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function SignalGroups({ groups, symbol }: { groups: Record<string, SignalRow[]>; symbol?: string }) {
  const entries = Object.entries(groups);

  // Lazy-load empirical backtest evidence for each currently-active signal.
  const ev = useQuery({
    queryKey: ["signal-evidence", symbol],
    queryFn: () => stocksApi.signalEvidence(symbol!),
    enabled: Boolean(symbol),
    staleTime: 24 * 60 * 60 * 1000,
  });
  const evidence = ev.data?.evidence || {};

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
        <CategoryBlock key={category} category={category} signals={signals} evidence={evidence} />
      ))}
    </div>
  );
}
