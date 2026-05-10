"use client";

import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, History } from "lucide-react";
import { simulationApi } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";

type Step = "market_pulse" | "discover" | "deep_dive" | "trades" | "ai_decision";

const TONE: Record<Step, { color: string }> = {
  market_pulse: { color: "text-accent-blue" },
  discover:     { color: "text-accent-amber" },
  deep_dive:    { color: "text-accent-violet" },
  trades:       { color: "text-accent-cyan" },
  ai_decision:  { color: "text-accent-pink" },
};

function StepView({ step, data }: { step: Step; data: Record<string, unknown> }) {
  if (!data || Object.keys(data).length === 0) {
    return <p className="text-xs text-text-muted">No data for this step in the selected cycle.</p>;
  }

  if (step === "market_pulse") {
    const regime = String(data.regime ?? "unknown");
    const vix = data.vix ? Number(data.vix).toFixed(1) : null;
    const summary = String(data.macro_summary ?? "");
    const sectors = Array.isArray(data.sector_perf) ? (data.sector_perf as any[]) : [];
    const gain = sectors.filter((s: any) => Number(s?.change ?? 0) > 0).slice(0, 4);
    const lose = sectors.filter((s: any) => Number(s?.change ?? 0) < 0).slice(0, 4);
    return (
      <div className="space-y-2">
        <div className="text-xs">
          <span className="text-text-muted uppercase tracking-wider">Regime: </span>
          <span className="font-semibold">{regime.replace(/_/g, " ")}</span>
          {vix && (
            <>
              <span className="text-text-muted ml-3"> · VIX </span>
              <span className="font-semibold tabular-nums">{vix}</span>
            </>
          )}
        </div>
        {summary && <p className="text-xs text-text-secondary">{summary}</p>}
        {gain.length > 0 && (
          <p className="text-[11px] text-accent-greenSoft">
            Gaining: {gain.map((s: any) => `${s.sector} ${Number(s.change).toFixed(1)}%`).join(", ")}
          </p>
        )}
        {lose.length > 0 && (
          <p className="text-[11px] text-accent-redSoft">
            Losing: {lose.map((s: any) => `${s.sector} ${Number(s.change).toFixed(1)}%`).join(", ")}
          </p>
        )}
      </div>
    );
  }

  if (step === "discover") {
    const favor = (data.favor_sectors as string[]) || [];
    const tickers = (data.ai_tickers as string[]) || [];
    const candidates = (data.candidates as any[]) || [];
    return (
      <div className="space-y-2">
        {favor.length > 0 && <p className="text-xs"><span className="text-text-muted">Focus: </span><span className="text-accent-amber">{favor.join(", ")}</span></p>}
        {tickers.length > 0 && <p className="text-xs"><span className="text-text-muted">AI tickers: </span><span className="text-accent-blue font-mono">{tickers.join(", ")}</span></p>}
        {candidates.length > 0 && (
          <div className="text-[11px] text-text-secondary">
            {candidates.length} candidate{candidates.length === 1 ? "" : "s"} ranked
          </div>
        )}
      </div>
    );
  }

  if (step === "deep_dive" || step === "ai_decision") {
    return (
      <pre className="text-[11px] text-text-secondary leading-relaxed whitespace-pre-wrap max-h-60 overflow-y-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    );
  }

  if (step === "trades") {
    const trades = (data.trades as any[]) || [];
    if (trades.length === 0) return <p className="text-xs text-text-muted">No trades recorded.</p>;
    return (
      <ul className="space-y-1 text-xs">
        {trades.map((t: any, i: number) => (
          <li key={i} className="flex items-center gap-2">
            <span className={cn("font-bold", String(t.action).toLowerCase().includes("buy") ? "text-accent-greenSoft" : "text-accent-redSoft")}>
              {t.action}
            </span>
            <span className="font-mono">{t.symbol}</span>
            {t.shares && <span className="text-text-muted">{t.shares} sh</span>}
            {t.price && <span className="tabular-nums">${Number(t.price).toFixed(2)}</span>}
          </li>
        ))}
      </ul>
    );
  }

  return null;
}

export function SimulationReplay({ step, accent = "violet" }: { step: Step; accent?: string }) {
  const [open, setOpen] = useState(false);
  const [selectedRun, setSelectedRun] = useState<string>("");
  const [selectedCycle, setSelectedCycle] = useState<string>("");

  const { data: runsData } = useQuery({
    queryKey: ["simulation", "runs"],
    queryFn: () => simulationApi.runs(),
    staleTime: 60_000,
  });
  const runs = runsData?.runs || [];

  useEffect(() => {
    if (!selectedRun && runs.length > 0) setSelectedRun(runs[0]);
  }, [runs, selectedRun]);

  const { data: cyclesData } = useQuery({
    queryKey: ["simulation", "cycles", selectedRun],
    queryFn: () => simulationApi.cycles(selectedRun),
    staleTime: 60_000,
    enabled: !!selectedRun,
  });
  const cycles = cyclesData?.cycles || [];

  useEffect(() => {
    if (cycles.length > 0 && !cycles.includes(selectedCycle)) {
      setSelectedCycle(cycles[cycles.length - 1]);
    }
  }, [cycles, selectedCycle]);

  const { data: stepData } = useQuery({
    queryKey: ["simulation", "step", selectedRun, selectedCycle, step],
    queryFn: () => simulationApi.step(selectedRun, selectedCycle, step),
    staleTime: 60_000,
    enabled: !!selectedRun && !!selectedCycle,
  });

  // Don't render if no sim runs exist
  if (runs.length === 0) return null;

  const stepLabel = step.replace(/_/g, " ");
  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full px-5 py-3 flex items-center justify-between text-sm hover:bg-bg-card2 transition-colors"
      >
        <span className="flex items-center gap-2">
          <History size={14} className={`text-accent-${accent}`} />
          Simulation Replay
          <span className="text-[10px] text-text-muted uppercase tracking-wider">
            What AI saw on {stepLabel}
          </span>
        </span>
        <ChevronDown size={14} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="px-5 pb-4 border-t border-bg-border pt-3 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="text-xs">
              <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">Run</div>
              <select
                value={selectedRun}
                onChange={(e) => setSelectedRun(e.target.value)}
                className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none"
              >
                {runs.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </label>
            <label className="text-xs">
              <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">
                Cycle ({cycles.length})
              </div>
              <select
                value={selectedCycle}
                onChange={(e) => setSelectedCycle(e.target.value)}
                disabled={cycles.length === 0}
                className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none disabled:opacity-50"
              >
                {cycles.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          </div>

          <div className="bg-bg-base border border-bg-border rounded-lg p-3 min-h-16">
            <StepView step={step} data={(stepData?.data ?? {}) as Record<string, unknown>} />
          </div>
        </div>
      )}
    </div>
  );
}
