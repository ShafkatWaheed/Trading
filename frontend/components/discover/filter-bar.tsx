"use client";

import { useMemo } from "react";
import { Filter, Calendar, Activity, Building2, TrendingUp, Zap, RotateCw } from "lucide-react";
import { cn } from "@/lib/utils";
import type { OpportunityCard } from "@/lib/api/types";

export type DiscoverFilters = {
  sectors:        string[];   // selected sector names; empty = all
  earnings_14d:   boolean;
  volume_conf:    boolean;
  smart_money:    boolean;
  trend_pullback: boolean;
  rel_strength:   boolean;
};

export const EMPTY_FILTERS: DiscoverFilters = {
  sectors: [],
  earnings_14d: false,
  volume_conf: false,
  smart_money: false,
  trend_pullback: false,
  rel_strength: false,
};

type Props = {
  ops: OpportunityCard[];
  filters: DiscoverFilters;
  onChange: (f: DiscoverFilters) => void;
};

export function applyFilters(ops: OpportunityCard[], f: DiscoverFilters): OpportunityCard[] {
  const now = new Date();
  const cutoff = new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000);

  return ops.filter((op) => {
    if (f.sectors.length > 0 && op.sector && !f.sectors.includes(op.sector)) return false;
    if (f.earnings_14d) {
      if (!op.next_earnings) return false;
      const e = new Date(op.next_earnings);
      if (Number.isNaN(e.getTime()) || e < now || e > cutoff) return false;
    }
    if (f.volume_conf  && !op.confirmations?.volume_confirmed) return false;
    if (f.smart_money  && (op.sub_scores?.flow ?? 0) < 0.5)    return false;
    if (f.trend_pullback && !op.confirmations?.trend_pullback) return false;
    if (f.rel_strength && !op.confirmations?.relative_strength) return false;
    return true;
  });
}

export function DiscoverFilterBar({ ops, filters, onChange }: Props) {
  // Distinct sectors from current dataset
  const sectors = useMemo(() => {
    const set = new Set<string>();
    for (const o of ops) if (o.sector) set.add(o.sector);
    return Array.from(set).sort();
  }, [ops]);

  const activeCount =
    filters.sectors.length +
    (filters.earnings_14d ? 1 : 0) +
    (filters.volume_conf ? 1 : 0) +
    (filters.smart_money ? 1 : 0) +
    (filters.trend_pullback ? 1 : 0) +
    (filters.rel_strength ? 1 : 0);

  const toggleSector = (s: string) => {
    const next = filters.sectors.includes(s)
      ? filters.sectors.filter((x) => x !== s)
      : [...filters.sectors, s];
    onChange({ ...filters, sectors: next });
  };

  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Filter size={13} className="text-text-muted" strokeWidth={2.4} />
          <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
            Filters {activeCount > 0 && <span className="text-accent-amber">· {activeCount} active</span>}
          </span>
        </div>
        {activeCount > 0 && (
          <button
            onClick={() => onChange(EMPTY_FILTERS)}
            className="text-[11px] text-text-muted hover:text-text-primary flex items-center gap-1"
          >
            <RotateCw size={11} /> Clear all
          </button>
        )}
      </div>

      {/* Setup quality toggles */}
      <div className="flex flex-wrap gap-2">
        <Toggle label="Volume confirmed" Icon={Activity}
                active={filters.volume_conf}
                onClick={() => onChange({ ...filters, volume_conf: !filters.volume_conf })}
                hint="Volume spike validating the price move" />
        <Toggle label="Smart-money flow" Icon={Zap}
                active={filters.smart_money}
                onClick={() => onChange({ ...filters, smart_money: !filters.smart_money })}
                hint="P/C ratio + insider buying score ≥ 0.5" />
        <Toggle label="Trend pullback" Icon={TrendingUp}
                active={filters.trend_pullback}
                onClick={() => onChange({ ...filters, trend_pullback: !filters.trend_pullback })}
                hint="Pulled back into an established uptrend" />
        <Toggle label="Relative strength" Icon={TrendingUp}
                active={filters.rel_strength}
                onClick={() => onChange({ ...filters, rel_strength: !filters.rel_strength })}
                hint="Outperforming SPY recently" />
        <Toggle label="Earnings ≤ 14d" Icon={Calendar}
                active={filters.earnings_14d}
                onClick={() => onChange({ ...filters, earnings_14d: !filters.earnings_14d })}
                hint="Has earnings report within next 14 days" />
      </div>

      {/* Sector chips */}
      {sectors.length > 0 && (
        <div className="flex items-start gap-2 pt-2 border-t border-bg-border">
          <Building2 size={13} className="text-text-muted shrink-0 mt-1.5" strokeWidth={2.4} />
          <div className="flex flex-wrap gap-1.5">
            {sectors.map((s) => {
              const active = filters.sectors.includes(s);
              return (
                <button
                  key={s}
                  onClick={() => toggleSector(s)}
                  className={cn(
                    "px-2.5 py-1 rounded-md text-[11px] font-medium border transition-all",
                    active
                      ? "bg-accent-violet/15 text-accent-violet border-accent-violet/40"
                      : "bg-bg-base text-text-secondary border-bg-border hover:border-bg-borderHi hover:text-text-primary"
                  )}
                >
                  {s}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function Toggle({ label, Icon, active, onClick, hint }: {
  label: string; Icon: typeof Filter; active: boolean; onClick: () => void; hint?: string;
}) {
  return (
    <button
      onClick={onClick}
      title={hint}
      className={cn(
        "px-2.5 py-1 rounded-md text-[11px] font-medium border flex items-center gap-1.5 transition-all",
        active
          ? "bg-accent-amber/10 text-accent-amber border-accent-amber/40"
          : "bg-bg-base text-text-secondary border-bg-border hover:border-bg-borderHi hover:text-text-primary"
      )}
    >
      <Icon size={11} strokeWidth={2.2} />
      {label}
    </button>
  );
}
