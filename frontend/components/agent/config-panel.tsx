"use client";

import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Settings, RotateCcw, Save, AlertTriangle } from "lucide-react";
import { agentApi } from "@/lib/api/endpoints";
import type { AgentConfig } from "@/lib/api/types";
import { cn, formatCurrency } from "@/lib/utils";

const RISK_OPTIONS = [0.01, 0.02, 0.03, 0.05];
const POS_OPTIONS = [3, 5, 8, 10];
const BUYS_OPTIONS = [1, 2, 3, 5];
const SCORE_OPTIONS = [45, 50, 55, 60, 65, 70, 75];
const STOP_OPTIONS = [8, 10, 12, 15, 20];
const FREQS = [
  { value: "manual", label: "Manual Only" },
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
];

export function ConfigPanel() {
  const qc = useQueryClient();
  const { data: config } = useQuery({
    queryKey: ["agent", "config"],
    queryFn: () => agentApi.config(),
    staleTime: 60_000,
  });

  const [draft, setDraft] = useState<Partial<AgentConfig>>({});
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  useEffect(() => {
    if (config) setDraft(config);
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: (patch: Partial<AgentConfig>) => agentApi.updateConfig(patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent"] });
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => agentApi.reset({
      starting_capital: draft.starting_capital ?? 100_000,
      risk_per_trade: draft.risk_per_trade ?? 0.02,
      max_positions: draft.max_positions ?? 8,
      max_buys_per_cycle: draft.max_buys_per_cycle ?? 3,
      min_opportunity_score: draft.min_opportunity_score ?? 60,
      stop_loss_pct: draft.stop_loss_pct ?? 12,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent"] });
      qc.invalidateQueries({ queryKey: ["portfolio"] });
      setShowResetConfirm(false);
    },
  });

  const isDirty = config && JSON.stringify(draft) !== JSON.stringify(config);

  if (!config) return null;

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4 gap-2">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Settings size={14} className="text-accent-blue" />
          Agent Configuration
        </h3>
        <div className="flex items-center gap-2">
          {isDirty && (
            <button
              onClick={() => saveMutation.mutate(draft)}
              disabled={saveMutation.isPending}
              className="text-xs bg-accent-blue/10 border border-accent-blue/40 hover:bg-accent-blue/20 text-accent-blue px-3 py-1.5 rounded-md font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              <Save size={12} />
              Save Changes
            </button>
          )}
          <button
            onClick={() => setShowResetConfirm(true)}
            className="text-xs bg-bg-base border border-bg-border hover:border-accent-red/40 hover:text-accent-redSoft text-text-secondary px-3 py-1.5 rounded-md font-medium flex items-center gap-1.5 transition-colors"
          >
            <RotateCcw size={12} />
            Reset Agent
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
        <Field label="Starting Capital">
          <input
            type="number"
            min={1000}
            value={draft.starting_capital ?? 100000}
            onChange={(e) =>
              setDraft({ ...draft, starting_capital: Math.max(1000, Number(e.target.value) || 100000) })
            }
            className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs tabular-nums focus:outline-none focus:border-accent-blue/60"
          />
          <span className="text-[10px] text-text-muted">{formatCurrency(draft.starting_capital ?? 100000)}</span>
        </Field>

        <Field label="Risk per Trade">
          <select
            value={draft.risk_per_trade ?? 0.02}
            onChange={(e) => setDraft({ ...draft, risk_per_trade: Number(e.target.value) })}
            className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-blue/60"
          >
            {RISK_OPTIONS.map((v) => (
              <option key={v} value={v}>{(v * 100).toFixed(0)}%</option>
            ))}
          </select>
        </Field>

        <Field label="Max Positions">
          <select
            value={draft.max_positions ?? 8}
            onChange={(e) => setDraft({ ...draft, max_positions: Number(e.target.value) })}
            className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-blue/60"
          >
            {POS_OPTIONS.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </Field>

        <Field label="Max Buys / Cycle">
          <select
            value={draft.max_buys_per_cycle ?? 3}
            onChange={(e) => setDraft({ ...draft, max_buys_per_cycle: Number(e.target.value) })}
            className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-blue/60"
          >
            {BUYS_OPTIONS.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </Field>

        <Field label="Min Score">
          <select
            value={draft.min_opportunity_score ?? 60}
            onChange={(e) => setDraft({ ...draft, min_opportunity_score: Number(e.target.value) })}
            className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-blue/60"
          >
            {SCORE_OPTIONS.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </Field>

        <Field label="Stop Loss %">
          <select
            value={draft.stop_loss_pct ?? 12}
            onChange={(e) => setDraft({ ...draft, stop_loss_pct: Number(e.target.value) })}
            className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-blue/60"
          >
            {STOP_OPTIONS.map((v) => <option key={v} value={v}>{v}%</option>)}
          </select>
        </Field>

        <Field label="Run Frequency">
          <select
            value={draft.rebalance_frequency ?? "weekly"}
            onChange={(e) => setDraft({ ...draft, rebalance_frequency: e.target.value })}
            className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-blue/60"
          >
            {FREQS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
        </Field>

        <Field label="Cash Available">
          <div className="text-sm font-bold tabular-nums px-2 py-1.5 text-text-secondary">
            {formatCurrency(config.current_cash, 0)}
          </div>
        </Field>
      </div>

      {showResetConfirm && (
        <div className="mt-4 p-4 bg-accent-red/5 border border-accent-red/40 rounded-md">
          <div className="flex items-start gap-2 text-sm">
            <AlertTriangle size={14} className="text-accent-redSoft shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-medium text-accent-redSoft">Reset agent?</p>
              <p className="text-xs text-text-secondary mt-1">
                This deletes all positions, decisions, and equity history. The portfolio resets to{" "}
                {formatCurrency(draft.starting_capital ?? 100000)}.
              </p>
              <div className="flex items-center gap-2 mt-3">
                <button
                  onClick={() => resetMutation.mutate()}
                  disabled={resetMutation.isPending}
                  className="text-xs bg-accent-red/10 border border-accent-red/40 hover:bg-accent-red/20 text-accent-redSoft px-3 py-1.5 rounded-md font-medium disabled:opacity-50"
                >
                  {resetMutation.isPending ? "Resetting…" : "Yes, reset"}
                </button>
                <button
                  onClick={() => setShowResetConfirm(false)}
                  className="text-xs text-text-secondary hover:text-text-primary px-3 py-1.5"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">{label}</div>
      {children}
    </label>
  );
}
