"use client";

import Link from "next/link";
import type { OpportunityCard as Op } from "@/lib/api/types";
import { ArrowRight, Calendar, Rocket } from "lucide-react";
import { cn, formatPercent } from "@/lib/utils";
import { Sparkline } from "./sparkline";

function scoreColor(score: number) {
  if (score >= 80) return "text-accent-greenSoft";
  if (score >= 65) return "text-accent-amber";
  if (score >= 50) return "text-text-primary";
  return "text-text-secondary";
}

function labelTone(label: string) {
  const l = label.toLowerCase();
  if (l.includes("excellent") || l.includes("strong")) return "badge-green";
  if (l.includes("good")) return "badge-blue";
  if (l.includes("fair")) return "badge-amber";
  return "badge-zinc";
}

function subBarColor(value: number) {
  if (value >= 18) return "bg-accent-greenSoft";
  if (value <= 8) return "bg-accent-redSoft";
  return "bg-accent-amber";
}

function SubScoreBar({ name, value, max = 25, hint }: { name: string; value: number; max?: number; hint?: string }) {
  const pct = Math.max(3, Math.min(100, (value / max) * 100));
  const color = subBarColor(value);
  return (
    <div title={hint}>
      <div className="flex items-center justify-between text-[10px] mb-1">
        <span className="text-text-muted uppercase tracking-wider">{name}</span>
        <span className={cn(
          "tabular-nums font-semibold",
          value >= 18 ? "text-accent-greenSoft" : value <= 8 ? "text-accent-redSoft" : "text-accent-amber"
        )}>
          {value.toFixed(0)}/{max}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-bg-base border border-bg-border overflow-hidden">
        <div className={cn("h-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function ConfirmationFlags({ op }: { op: Op }) {
  const c = op.confirmations;
  const flags = [
    { key: "TP",  on: c.trend_pullback, hint: "Trend Pullback — pullback in an uptrend" },
    { key: "RS",  on: c.relative_strength, hint: "Relative Strength — outperforming peers" },
    { key: "VOL", on: c.volume_confirmed, hint: "Volume Confirmed — buying volume verified" },
  ];
  const status = c.momentum_override
    ? "Momentum rocket — bypasses confirmations"
    : op.confirmation_count >= 2
    ? "Trade-ready"
    : op.confirmation_count === 1
    ? "Needs more confirmation"
    : "Not confirmed";

  const borderTone = c.momentum_override
    ? "border-accent-amber/40"
    : op.confirmation_count >= 2
    ? "border-accent-green/40"
    : op.confirmation_count === 1
    ? "border-accent-amber/40"
    : "border-accent-red/40";

  return (
    <div className={cn("flex items-center gap-2 px-3 py-2 rounded-lg border bg-bg-base", borderTone)}>
      <span className="text-[10px] uppercase tracking-wider text-text-muted">Confirms</span>
      <span className={cn(
        "text-xs font-bold tabular-nums",
        op.confirmation_count >= 2 ? "text-accent-greenSoft"
          : op.confirmation_count === 1 ? "text-accent-amber" : "text-accent-redSoft"
      )}>
        {op.confirmation_count}/3
      </span>
      <div className="flex items-center gap-1.5 text-xs">
        {flags.map((f) => (
          <span
            key={f.key}
            title={f.hint}
            className={cn(
              "font-mono font-semibold",
              f.on ? "text-accent-greenSoft" : "text-text-muted/40"
            )}
          >
            {f.on ? "✓" : "✗"} {f.key}
          </span>
        ))}
        {c.momentum_override && (
          <span className="ml-2 inline-flex items-center gap-1 text-accent-amber font-bold text-xs">
            <Rocket size={10} /> MOMENTUM OVERRIDE
          </span>
        )}
      </div>
      <span className="ml-auto text-[10px] text-text-muted">{status}</span>
    </div>
  );
}

function Week52Bar({ op }: { op: Op }) {
  if (!op.week52) return null;
  const { high, low, position_pct } = op.week52;
  const dotColor =
    position_pct < 40 ? "bg-accent-greenSoft"
    : position_pct > 80 ? "bg-accent-redSoft"
    : "bg-accent-amber";
  return (
    <div>
      <div className="flex items-center justify-between text-[10px] text-text-muted">
        <span className="tabular-nums">${low.toFixed(0)}</span>
        <span className="uppercase tracking-wider">52W Range</span>
        <span className="tabular-nums">${high.toFixed(0)}</span>
      </div>
      <div className="h-1.5 mt-1 rounded-full bg-bg-base border border-bg-border relative overflow-visible">
        <div
          className="h-full rounded-full"
          style={{
            width: `${position_pct}%`,
            background: "linear-gradient(to right, #4ade80, #f59e0b, #f87171)",
          }}
        />
        <div
          className={cn("absolute -top-1 w-2.5 h-2.5 rounded-full border-2 border-text-primary", dotColor)}
          style={{ left: `calc(${position_pct}% - 5px)` }}
        />
      </div>
    </div>
  );
}

export function RichOpportunityCard({
  op, rank, selected = false, onToggleSelect, adjustedScore,
}: {
  op: Op;
  rank: number;
  selected?: boolean;
  onToggleSelect?: (symbol: string) => void;
  /** When set, shows the regime-adjusted score alongside the original. */
  adjustedScore?: number | null;
}) {
  const change = op.change_pct ?? 0;
  const positive = change > 0;
  const negative = change < 0;

  return (
    <div className={cn(
      "card p-5 transition-all hover:border-bg-borderHi",
      rank === 0 && "card-glow-amber",
      selected && "ring-1 ring-accent-violet/60",
    )}>
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            {onToggleSelect && (
              <button
                onClick={(e) => { e.stopPropagation(); onToggleSelect(op.symbol); }}
                className={cn(
                  "w-4 h-4 rounded border-[1.5px] grid place-items-center transition-colors shrink-0",
                  selected
                    ? "bg-accent-violet border-accent-violet text-white"
                    : "bg-bg-base border-bg-borderHi hover:border-accent-violet/60"
                )}
                aria-label={selected ? `Unselect ${op.symbol}` : `Select ${op.symbol}`}
                title={selected ? "Unselect" : "Select for compare"}
              >
                {selected && (
                  <svg width="9" height="9" viewBox="0 0 12 12" fill="none">
                    <path d="M2 6.5l2.5 2.5L10 3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                )}
              </button>
            )}
            <span className="text-text-dim text-[11px] font-bold tabular-nums">#{rank + 1}</span>
            <span className="text-xl font-semibold tracking-tight">{op.symbol}</span>
            <span className={labelTone(op.label)}>
              <span className="tabular-nums font-bold mr-1">{op.score.toFixed(0)}</span>
              {op.label}
            </span>
            {adjustedScore != null && adjustedScore !== Math.round(op.score) && (
              <span
                className="badge bg-accent-violet/10 text-accent-violet border-accent-violet/40"
                title="Score re-weighted for current market regime"
              >
                <span className="tabular-nums font-bold mr-1">{adjustedScore}</span>
                regime-adj
              </span>
            )}
          </div>
          {op.sector_label && (
            <p className="text-[11px] text-text-muted mt-1 truncate flex items-center gap-1.5">
              <span>{op.sector_label}</span>
              {op.market_cap && (
                <>
                  <span className="text-text-dim">·</span>
                  <span className="font-mono">{op.market_cap}</span>
                </>
              )}
              {op.next_earnings && (
                <>
                  <span className="text-text-dim">·</span>
                  <span className="inline-flex items-center gap-1 text-accent-amber font-medium">
                    <Calendar size={9} strokeWidth={2.4} />
                    {op.next_earnings}
                  </span>
                </>
              )}
            </p>
          )}
        </div>

        {op.price != null && (
          <div className="text-right shrink-0">
            <div className="text-xl font-semibold tabular-nums tracking-tight">${op.price.toFixed(2)}</div>
            <div className={cn(
              "text-xs tabular-nums font-semibold mt-0.5",
              positive ? "text-accent-greenSoft" : negative ? "text-accent-redSoft" : "text-text-muted",
            )}>
              {positive ? "↑" : negative ? "↓" : ""} {formatPercent(change)}
            </div>
          </div>
        )}
      </div>

      {op.spark && op.spark.length > 1 && (
        <div className="mb-3 -mx-2">
          <Sparkline points={op.spark} height={60} />
        </div>
      )}

      {op.week52 && <div className="mb-4"><Week52Bar op={op} /></div>}

      {/* Primary strategy block */}
      <div className="bg-bg-base/60 border border-accent-blue/25 rounded-lg p-3.5 mb-3">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-base">{op.strategy_icon}</span>
          <span className="text-[13px] font-semibold text-accent-blue tracking-tight">{op.strategy}</span>
          <span className="text-[10px] uppercase tracking-wider text-text-muted">Primary</span>
          {op.risk_reward_ratio != null && op.risk_reward_ratio > 0 && (
            <span className="ml-auto text-[11px] text-text-muted tabular-nums font-mono">
              R/R {op.risk_reward_ratio.toFixed(1)}:1
            </span>
          )}
        </div>
        {op.strategy_description && (
          <p className="text-[12px] text-text-secondary leading-relaxed">{op.strategy_description}</p>
        )}
      </div>

      {/* Secondary strategies */}
      {op.secondary_strategies.length > 0 && (
        <div className="mb-3">
          <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1.5">
            Also detected ({op.secondary_strategies.length})
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {op.secondary_strategies.map((s) => (
              <div
                key={s.name}
                title={s.description}
                className="shrink-0 w-44 bg-bg-base border border-bg-border rounded-lg p-2.5"
              >
                <div className="flex items-center gap-1.5 mb-1">
                  <span>{s.icon}</span>
                  <span className="text-xs font-semibold truncate">{s.name}</span>
                </div>
                {s.description && (
                  <p className="text-[10px] text-text-muted line-clamp-2 leading-snug">
                    {s.description}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sub-scores */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
        <SubScoreBar name="Volume"      value={op.sub_scores.volume}       hint="Recent volume vs 20-day average" />
        <SubScoreBar name="Price"       value={op.sub_scores.price}        hint="RSI + trend + MACD momentum" />
        <SubScoreBar name="Flow"        value={op.sub_scores.flow}         hint="Options P/C ratio + insider buying" />
        <SubScoreBar name="Risk/Reward" value={op.sub_scores.risk_reward}  hint="Upside vs downside distance" />
      </div>

      {/* Confirmation flags */}
      <ConfirmationFlags op={op} />

      <div className="mt-4">
        <Link
          href={`/deep-dive/${op.symbol}`}
          className="btn btn-accent w-full bg-accent-blue/10 border-accent-blue/40 hover:bg-accent-blue/20 hover:border-accent-blue/60 text-accent-blue h-9 group"
        >
          Deep Dive
          <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>
    </div>
  );
}
