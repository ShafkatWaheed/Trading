"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Brain, ChevronDown, RefreshCw } from "lucide-react";
import { agentApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import type { CotStep } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STEP_TONE: Record<string, { bg: string; text: string; icon: string }> = {
  market_analysis:    { bg: "bg-accent-blue/10",   text: "text-accent-blue",       icon: "🌍" },
  discovery:          { bg: "bg-accent-amber/10",  text: "text-accent-amber",      icon: "🔍" },
  deep_dive:          { bg: "bg-accent-violet/10", text: "text-accent-violet",     icon: "📊" },
  ai_decision:        { bg: "bg-accent-pink/10",   text: "text-accent-pink",       icon: "🧠" },
  execute:            { bg: "bg-accent-green/10",  text: "text-accent-greenSoft",  icon: "💸" },
  monitor:            { bg: "bg-accent-cyan/10",   text: "text-accent-cyan",       icon: "📡" },
  exit:               { bg: "bg-accent-red/10",    text: "text-accent-redSoft",    icon: "🚪" },
};

function tone(step: string) {
  const key = (step || "").toLowerCase().replace(/[^a-z_]/g, "_");
  return STEP_TONE[key] || { bg: "bg-bg-base", text: "text-text-secondary", icon: "•" };
}

function StepRow({ s }: { s: CotStep }) {
  const t = tone(s.step);
  const decisionTone =
    /buy/i.test(s.decision) ? "text-accent-greenSoft"
    : /sell|reject|fail/i.test(s.decision) ? "text-accent-redSoft"
    : "text-text-secondary";
  return (
    <div className="flex items-start gap-3 px-3 py-2.5 rounded-md hover:bg-bg-card2 transition-colors">
      <div className={cn("w-7 h-7 rounded-md grid place-items-center shrink-0", t.bg)}>
        <span>{t.icon}</span>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={cn("text-xs font-bold uppercase tracking-wider", t.text)}>
            {s.step.replace(/_/g, " ")}
          </span>
          {s.symbol && (
            <span className="font-mono text-xs font-semibold">{s.symbol}</span>
          )}
          {s.decision && (
            <span className={cn("text-xs font-medium", decisionTone)}>
              → {s.decision}
            </span>
          )}
        </div>
        {s.reasoning && (
          <p className="text-xs text-text-secondary mt-1 leading-relaxed whitespace-pre-line">
            {s.reasoning}
          </p>
        )}
      </div>
    </div>
  );
}

export function ChainOfThought() {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["agent", "cot"],
    queryFn: () => agentApi.chainOfThought(5),
    staleTime: 30_000,
  });

  const toggleRun = (key: string) => {
    setExpanded((s) => {
      const ns = new Set(s);
      if (ns.has(key)) ns.delete(key); else ns.add(key);
      return ns;
    });
  };

  if (isLoading) return <Skeleton className="h-48" />;

  const runs = data?.runs ?? [];
  if (runs.length === 0) {
    return (
      <div className="card p-5 flex items-center gap-3">
        <Brain className="text-text-muted" size={20} />
        <div>
          <p className="text-sm text-text-secondary">No reasoning logged yet.</p>
          <p className="text-xs text-text-muted mt-0.5">Run a cycle to see the AI's step-by-step thinking.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Brain size={14} className="text-accent-pink" />
          <h3 className="text-sm font-semibold">Chain of Thought</h3>
          <span className="text-[10px] text-text-muted uppercase tracking-wider">
            Last {runs.length} cycle{runs.length === 1 ? "" : "s"}
          </span>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="text-xs text-text-secondary hover:text-text-primary inline-flex items-center gap-1.5 px-2 py-1 rounded transition-colors"
        >
          <RefreshCw size={11} className={isFetching ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      <div className="space-y-2">
        {runs.map((run) => {
          const open = expanded.has(run.run_date);
          return (
            <div key={run.run_date} className="border border-bg-border rounded-lg overflow-hidden">
              <button
                onClick={() => toggleRun(run.run_date)}
                className="w-full px-3 py-2.5 flex items-center justify-between hover:bg-bg-card2 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono text-text-muted">{run.run_date}</span>
                  <span className="text-xs text-text-secondary">
                    {run.steps.length} step{run.steps.length === 1 ? "" : "s"}
                  </span>
                </div>
                <ChevronDown size={14} className={cn("text-text-muted transition-transform", open && "rotate-180")} />
              </button>
              {open && (
                <div className="border-t border-bg-border p-2 space-y-1 bg-bg-base">
                  {run.steps.map((s, i) => <StepRow key={i} s={s} />)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
