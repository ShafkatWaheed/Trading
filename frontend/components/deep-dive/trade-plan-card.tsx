"use client";

import type { TradePlan } from "@/lib/api/types";
import { Target, ArrowDown, ArrowUp } from "lucide-react";
import { formatCurrency } from "@/lib/utils";

export function TradePlanCard({ plan }: { plan?: TradePlan | null }) {
  if (!plan || (plan.entry == null && plan.target == null)) {
    return null;
  }
  const cells: { label: string; value: string; tone: string; icon?: any }[] = [];

  if (plan.entry != null) {
    cells.push({ label: "Entry", value: formatCurrency(plan.entry, 2), tone: "text-text-primary" });
  }
  if (plan.stop_loss != null) {
    cells.push({
      label: "Stop", value: formatCurrency(plan.stop_loss, 2),
      tone: "text-accent-redSoft", icon: ArrowDown,
    });
  }
  if (plan.target != null) {
    cells.push({
      label: "Target", value: formatCurrency(plan.target, 2),
      tone: "text-accent-greenSoft", icon: ArrowUp,
    });
  }
  if (plan.support != null) {
    cells.push({ label: "Support", value: formatCurrency(plan.support, 2), tone: "text-text-secondary" });
  }
  if (plan.resistance != null) {
    cells.push({ label: "Resistance", value: formatCurrency(plan.resistance, 2), tone: "text-text-secondary" });
  }
  if (plan.risk_reward != null) {
    cells.push({ label: "Risk/Reward", value: `${plan.risk_reward.toFixed(2)} : 1`, tone: "text-accent-blue" });
  }

  return (
    <div className="card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Target size={16} className="text-accent-blue" />
        <h3 className="text-base font-semibold">Trade Plan</h3>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {cells.map((c) => (
          <div key={c.label} className="bg-bg-base border border-bg-border rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-text-muted">{c.label}</div>
            <div className={`text-sm font-semibold mt-1 tabular-nums ${c.tone}`}>{c.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
