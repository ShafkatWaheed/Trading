"use client";

import type { TradePlan } from "@/lib/api/types";
import { Target, Shield, TrendingUp, TrendingDown, AlertTriangle, CheckCircle2 } from "lucide-react";
import { cn, formatCurrency, formatPercent } from "@/lib/utils";

function alignmentTone(pct: number) {
  if (pct >= 75) return "text-accent-greenSoft";
  if (pct >= 50) return "text-accent-amber";
  return "text-accent-redSoft";
}

export function TradePlanRich({ plan }: { plan: TradePlan }) {
  return (
    <div className="card p-6">
      <div className="flex items-center gap-2 mb-4 pb-3 border-b border-bg-border">
        <Target size={18} className="text-accent-blue" />
        <h3 className="text-base font-semibold">Trade Plan</h3>
        <span className={cn(
          "ml-auto badge text-xs",
          plan.alignment_pct >= 75
            ? "bg-accent-green/10 text-accent-greenSoft border-accent-green/30"
            : plan.alignment_pct >= 50
            ? "bg-accent-amber/10 text-accent-amber border-accent-amber/30"
            : "bg-accent-red/10 text-accent-redSoft border-accent-red/30"
        )}>
          {plan.alignment_pct}% {plan.alignment_dominant}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
        <div className="bg-bg-base border border-bg-border rounded-lg p-3">
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Entry</div>
          <div className="text-base font-bold tabular-nums mt-1">{formatCurrency(plan.entry, 2)}</div>
        </div>
        <div className="bg-bg-base border border-accent-red/30 rounded-lg p-3">
          <div className="text-[10px] uppercase tracking-wider text-text-muted flex items-center gap-1">
            <Shield size={9} /> Stop
          </div>
          <div className="text-base font-bold tabular-nums mt-1 text-accent-redSoft">
            {formatCurrency(plan.stop_loss, 2)}
          </div>
          <div className="text-[10px] text-text-muted tabular-nums">
            -{plan.stop_pct.toFixed(1)}%
          </div>
        </div>
        <div className="bg-bg-base border border-accent-green/30 rounded-lg p-3">
          <div className="text-[10px] uppercase tracking-wider text-text-muted flex items-center gap-1">
            <TrendingUp size={9} /> Target 1
          </div>
          <div className="text-base font-bold tabular-nums mt-1 text-accent-greenSoft">
            {formatCurrency(plan.target1, 2)}
          </div>
          <div className="text-[10px] text-text-muted tabular-nums">
            +{plan.target1_pct.toFixed(1)}%
          </div>
        </div>
        <div className="bg-bg-base border border-accent-green/30 rounded-lg p-3">
          <div className="text-[10px] uppercase tracking-wider text-text-muted flex items-center gap-1">
            <TrendingUp size={9} /> Target 2
          </div>
          <div className="text-base font-bold tabular-nums mt-1 text-accent-greenSoft">
            {formatCurrency(plan.target2, 2)}
          </div>
          <div className="text-[10px] text-text-muted tabular-nums">
            +{plan.target2_pct.toFixed(1)}%
          </div>
        </div>
      </div>

      {/* R/R + Position sizing */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
        <div className="bg-bg-base border border-bg-border rounded-lg p-4">
          <h4 className="text-xs uppercase tracking-wider text-text-muted mb-2">Risk / Reward</h4>
          <div className="text-2xl font-bold text-accent-blue tabular-nums">
            {plan.risk_reward.toFixed(2)} : 1
          </div>
          <p className="text-xs text-text-muted mt-1">
            Risking ${plan.risk_per_share.toFixed(2)}/share to make ${(plan.target1 - plan.entry).toFixed(2)} (T1)
          </p>
        </div>

        <div className="bg-bg-base border border-bg-border rounded-lg p-4">
          <h4 className="text-xs uppercase tracking-wider text-text-muted mb-2 flex items-center justify-between">
            <span>Position Sizing</span>
            <span className="text-text-muted">
              ${plan.account_size.toLocaleString()} · {plan.risk_pct}% risk
            </span>
          </h4>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <div className="text-text-muted">Shares</div>
              <div className="text-sm font-bold tabular-nums">{plan.shares.toLocaleString()}</div>
            </div>
            <div>
              <div className="text-text-muted">Position $</div>
              <div className="text-sm font-bold tabular-nums">{formatCurrency(plan.position_value)}</div>
            </div>
            <div>
              <div className="text-text-muted">Max Loss</div>
              <div className="text-sm font-bold tabular-nums text-accent-redSoft">
                -{formatCurrency(plan.loss_at_stop)}
              </div>
            </div>
            <div>
              <div className="text-text-muted">Profit @ T1</div>
              <div className="text-sm font-bold tabular-nums text-accent-greenSoft">
                +{formatCurrency(plan.profit_t1)}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Signal alignment bar */}
      <div className="mb-5">
        <h4 className="text-xs uppercase tracking-wider text-text-muted mb-2">
          Signal Alignment
          <span className={cn("ml-2 font-bold text-sm", alignmentTone(plan.alignment_pct))}>
            {plan.alignment_pct}%
          </span>
        </h4>
        <div className="h-2 rounded-full bg-bg-base border border-bg-border overflow-hidden flex">
          <div
            className="bg-accent-greenSoft"
            style={{ width: `${(plan.alignment_bull / Math.max(plan.alignment_total, 1)) * 100}%` }}
          />
          <div
            className="bg-zinc-600"
            style={{ width: `${(plan.alignment_neutral / Math.max(plan.alignment_total, 1)) * 100}%` }}
          />
          <div
            className="bg-accent-redSoft"
            style={{ width: `${(plan.alignment_bear / Math.max(plan.alignment_total, 1)) * 100}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-text-muted mt-1.5 tabular-nums">
          <span className="text-accent-greenSoft">{plan.alignment_bull} bullish</span>
          <span>{plan.alignment_neutral} neutral</span>
          <span className="text-accent-redSoft">{plan.alignment_bear} bearish</span>
        </div>
      </div>

      {/* Timing notes */}
      {(plan.timing_good.length > 0 || plan.timing_warn.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
          {plan.timing_good.length > 0 && (
            <div className="bg-accent-green/5 border border-accent-green/30 rounded-lg p-3">
              <h4 className="text-xs font-semibold text-accent-greenSoft mb-2 flex items-center gap-1.5">
                <CheckCircle2 size={12} /> Timing — Favorable
              </h4>
              <ul className="space-y-1">
                {plan.timing_good.map((t, i) => (
                  <li key={i} className="text-xs text-text-secondary flex items-start gap-1.5">
                    <span className="text-accent-greenSoft mt-0.5">✓</span>
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {plan.timing_warn.length > 0 && (
            <div className="bg-accent-amber/5 border border-accent-amber/30 rounded-lg p-3">
              <h4 className="text-xs font-semibold text-accent-amber mb-2 flex items-center gap-1.5">
                <AlertTriangle size={12} /> Timing — Caution
              </h4>
              <ul className="space-y-1">
                {plan.timing_warn.map((t, i) => (
                  <li key={i} className="text-xs text-text-secondary flex items-start gap-1.5">
                    <span className="text-accent-amber mt-0.5">!</span>
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Risks */}
      {plan.risks.length > 0 && (
        <div className="bg-bg-base border border-bg-border rounded-lg p-3">
          <h4 className="text-xs font-semibold text-accent-redSoft mb-2 flex items-center gap-1.5">
            <TrendingDown size={12} /> Risks to Monitor
          </h4>
          <ul className="space-y-1">
            {plan.risks.map((r, i) => (
              <li key={i} className="text-xs text-text-secondary flex items-start gap-1.5">
                <span className="text-accent-redSoft mt-0.5">•</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
