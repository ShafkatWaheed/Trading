"use client";

import { Calculator, Info } from "lucide-react";
import type { TradePlan } from "@/lib/api/types";
import { cn, formatCurrency } from "@/lib/utils";

type Props = { plan: TradePlan };

export function PositionSizing({ plan }: Props) {
  if (!plan || !plan.shares || plan.shares <= 0) {
    return null;
  }

  const accountSize    = plan.account_size;
  const riskPct        = plan.risk_pct;
  const shares         = plan.shares;
  const entry          = plan.entry;
  const stop           = plan.stop_loss;
  const target1        = plan.target1;
  const target2        = plan.target2;
  const exposure       = plan.position_value;
  const exposurePctAcct = accountSize > 0 ? (exposure / accountSize) * 100 : 0;
  const maxLoss        = plan.loss_at_stop;
  const profitT1       = plan.profit_t1;
  const profitT2       = plan.profit_t2;
  const rr             = plan.risk_reward;

  return (
    <section className="card-subtle p-6">
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <Calculator size={16} className="text-accent-cyan" />
        <h3 className="text-base font-semibold">Position Sizing</h3>
        <span className="text-[10px] uppercase tracking-wider text-text-muted">
          for ${accountSize.toLocaleString()} account · {riskPct.toFixed(1)}% risk
        </span>
      </div>

      {/* Headline action */}
      <div className="bg-accent-cyan/5 border border-accent-cyan/30 rounded-md p-4 mb-4">
        <div className="text-[11px] uppercase tracking-wider text-text-muted mb-1">If you take this trade</div>
        <p className="text-base text-text-primary leading-snug">
          Buy <span className="font-bold text-accent-cyan tabular-nums">{shares.toLocaleString()}</span> shares
          at <span className="font-bold tabular-nums">${entry.toFixed(2)}</span>
          {" "}= <span className="font-bold tabular-nums">{formatCurrency(exposure)}</span>
          {" "}exposure
          (<span className="tabular-nums">{exposurePctAcct.toFixed(1)}%</span> of your account).
          {" "}Max loss if stop hits: <span className="font-bold text-accent-redSoft tabular-nums">{formatCurrency(maxLoss)}</span>.
        </p>
      </div>

      {/* Numbers grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-4">
        <Stat label="Shares to buy"        value={shares.toLocaleString()} />
        <Stat label="Position value"       value={formatCurrency(exposure)} />
        <Stat label="% of account"         value={`${exposurePctAcct.toFixed(1)}%`}
              hint={exposurePctAcct > 25 ? "concentrated — beware" : undefined}
              tone={exposurePctAcct > 25 ? "amber" : "neutral"} />
        <Stat label="Risk-reward"          value={`${rr.toFixed(1)}:1`}
              hint={rr < 1.5 ? "thin — consider tighter stop" : rr >= 3 ? "excellent" : undefined}
              tone={rr >= 3 ? "green" : rr < 1.5 ? "amber" : "neutral"} />
        <Stat label="Max loss (stop hit)"  value={formatCurrency(maxLoss)} tone="red" />
        <Stat label="Profit at Target 1"   value={`+${formatCurrency(profitT1)}`} tone="green" />
        <Stat label="Profit at Target 2"   value={`+${formatCurrency(profitT2)}`} tone="green" />
        <Stat label="Risk per share"       value={`$${plan.risk_per_share.toFixed(2)}`}
              hint={`(entry − stop)`} />
      </div>

      {/* Sanity checks */}
      <div className="space-y-1.5 text-[11px] text-text-secondary">
        {exposurePctAcct > 25 && (
          <Note tone="amber">
            Position would be {exposurePctAcct.toFixed(0)}% of your account — concentrated. Consider scaling in or reducing share count.
          </Note>
        )}
        {rr < 1.5 && (
          <Note tone="amber">
            Risk-reward {rr.toFixed(1)}:1 is thin. Wait for a tighter entry, or set a closer target.
          </Note>
        )}
        {rr >= 3 && (
          <Note tone="green">
            Risk-reward {rr.toFixed(1)}:1 is favorable — you risk $1 to make ${rr.toFixed(1)}.
          </Note>
        )}
        {maxLoss > accountSize * (riskPct / 100) * 1.05 && (
          <Note tone="amber">
            Max loss {formatCurrency(maxLoss)} slightly exceeds your declared risk budget — verify share count.
          </Note>
        )}
      </div>

      <p className="text-[10px] text-text-muted mt-4 pt-3 border-t border-bg-border">
        Sizing computed from account size and risk % you provided in the URL parameters.
        Risk amount = account × risk %; shares = risk amount ÷ risk-per-share.
      </p>
    </section>
  );
}

function Stat({ label, value, hint, tone = "neutral" }: {
  label: string; value: string; hint?: string; tone?: "neutral" | "green" | "amber" | "red";
}) {
  const valueColor =
    tone === "green" ? "text-accent-greenSoft"
    : tone === "amber" ? "text-accent-amber"
    : tone === "red" ? "text-accent-redSoft"
    : "text-text-primary";
  return (
    <div className="bg-bg-base rounded-md p-2.5 border border-bg-border">
      <div className="text-[10px] uppercase tracking-wider text-text-muted">{label}</div>
      <div className={cn("text-base font-bold tabular-nums mt-0.5", valueColor)}>{value}</div>
      {hint && <div className="text-[10px] text-text-muted mt-0.5">{hint}</div>}
    </div>
  );
}

function Note({ tone, children }: { tone: "amber" | "green"; children: React.ReactNode }) {
  const color = tone === "green" ? "text-accent-greenSoft" : "text-accent-amber";
  return (
    <div className={cn("flex items-start gap-2 leading-relaxed", color)}>
      <Info size={12} className="mt-0.5 shrink-0" />
      <span className="text-text-secondary">{children}</span>
    </div>
  );
}
