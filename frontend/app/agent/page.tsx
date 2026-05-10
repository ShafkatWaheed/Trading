"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, CheckCircle2, Pause, Clock } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { PersonalitiesGrid } from "@/components/agent/personalities-grid";
import { ConfigPanel } from "@/components/agent/config-panel";
import { TradingRules } from "@/components/agent/trading-rules";
import { RunButtons } from "@/components/agent/run-buttons";
import { PositionsTable } from "@/components/agent/positions-table";
import { EquityPanel } from "@/components/agent/equity-panel";
import { MultiAgentTree } from "@/components/agent/multi-agent-tree";
import { ChainOfThought } from "@/components/agent/chain-of-thought";
import { PortfolioStrategyReference } from "@/components/agent/portfolio-strategy-reference";
import { PortfolioPickPanel } from "@/components/agent/portfolio-pick-panel";
import { PortfolioSimRunner } from "@/components/agent/portfolio-sim-runner";
import { agentApi } from "@/lib/api/endpoints";
import type { MultiAgentResult } from "@/lib/api/types";
import { cn, formatCurrency } from "@/lib/utils";

export default function AgentPage() {
  const [lastMulti, setLastMulti] = useState<MultiAgentResult | null>(null);

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["agent", "status"],
    queryFn: () => agentApi.status(),
    staleTime: 30_000,
  });
  const { data: config } = useQuery({
    queryKey: ["agent", "config"],
    queryFn: () => agentApi.config(),
    staleTime: 60_000,
  });
  const { data: personalities } = useQuery({
    queryKey: ["agent", "personalities"],
    queryFn: () => agentApi.personalities(),
    staleTime: Infinity,
  });
  const { data: positions = [] } = useQuery({
    queryKey: ["agent", "positions"],
    queryFn: () => agentApi.positions(),
    staleTime: 30_000,
  });
  const { data: equity } = useQuery({
    queryKey: ["agent", "equity"],
    queryFn: () => agentApi.equity(),
    staleTime: 60_000,
  });
  const { data: decisions = [] } = useQuery({
    queryKey: ["agent", "decisions", 20],
    queryFn: () => agentApi.decisions(20),
    staleTime: 30_000,
  });

  return (
    <div>
      <PageHeader
        icon={Bot}
        title="AI Agent"
        subtitle="8 personality agents compete — Risk Manager builds the final portfolio."
        accent="text-accent-pink"
        iconBg="bg-accent-pink/10"
      />

      <div className="space-y-6">
        {/* Status banner */}
        {statusLoading ? (
          <Skeleton className="h-32" />
        ) : status ? (
          <div className={cn(
            "card p-6",
            status.enabled ? "card-glow-green" : "",
          )}>
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="flex items-start gap-3.5 min-w-0">
                <div className={cn(
                  "w-11 h-11 rounded-xl grid place-items-center shrink-0 ring-1 ring-inset ring-white/5",
                  status.enabled ? "bg-accent-green/10" : "bg-bg-card2",
                )}>
                  {status.enabled ? (
                    <CheckCircle2 size={20} className="text-accent-greenSoft" strokeWidth={2.2} />
                  ) : (
                    <Pause size={20} className="text-text-muted" strokeWidth={2.2} />
                  )}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h2 className="text-lg font-semibold tracking-tight">{status.enabled ? "Running" : "Idle"}</h2>
                    <span className="badge-zinc capitalize">{status.rebalance_frequency}</span>
                    {status.overdue && (
                      <span className="badge badge-amber animate-pulse">
                        OVERDUE
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-2 text-[11px] text-text-muted">
                    {status.last_run && (
                      <span>Last run · <span className="tabular-nums text-text-secondary">{status.last_run}</span></span>
                    )}
                    {status.next_run && (
                      <span className="inline-flex items-center gap-1">
                        <Clock size={10} strokeWidth={2.4} />
                        Next · <span className="tabular-nums text-text-secondary">{status.next_run}</span>
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Portfolio</div>
                <div className="text-2xl font-semibold mt-1 tabular-nums tracking-tight">
                  {formatCurrency(status.portfolio_value)}
                </div>
                <div className="text-[11px] text-text-muted mt-1">
                  {status.open_positions} open position{status.open_positions === 1 ? "" : "s"}
                </div>
              </div>
            </div>
          </div>
        ) : null}

        {/* Strategy reference — explains the portfolio AI pipeline */}
        <PortfolioStrategyReference />

        {/* Portfolio AI pick — screen universe + 7 agents vote */}
        <PortfolioPickPanel />

        {/* Walk-forward simulation */}
        <PortfolioSimRunner />

        {/* Run buttons */}
        <RunButtons
          rmPicks={5}
          minScore={config?.min_opportunity_score ?? 60}
          overdue={status?.overdue}
          isRunning={status?.enabled}
          onMultiResult={(r) => setLastMulti(r)}
        />

        {/* Multi-agent pipeline (last result) */}
        {lastMulti && <MultiAgentTree result={lastMulti} />}

        {/* Chain of Thought from recent runs */}
        <ChainOfThought />

        {/* Config */}
        <ConfigPanel />

        {/* Trading rules */}
        <TradingRules />

        {/* Personalities */}
        {personalities && (
          <section>
            <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wider mb-3">
              Meet the 8 Trading Agents
            </h2>
            <PersonalitiesGrid agents={personalities.agents} riskManager={personalities.risk_manager} />
          </section>
        )}

        {/* Performance + Equity Curve */}
        {equity && <EquityPanel data={equity} />}

        {/* Positions */}
        <PositionsTable positions={positions} />

        {/* Recent decisions */}
        <section>
          <h2 className="text-sm font-medium text-text-secondary uppercase tracking-wider mb-3">
            Recent Decisions
          </h2>
          {decisions.length === 0 ? (
            <div className="card p-6 text-text-muted text-sm">
              No decisions yet. Click <span className="text-accent-pink">Single Agent Cycle</span> or
              <span className="text-accent-pink"> Multi-Agent Cycle</span> to start.
            </div>
          ) : (
            <div className="card divide-y divide-bg-border">
              {decisions.map((d, i) => (
                <div key={i} className="p-4 flex items-start gap-3">
                  <span className={cn(
                    "badge font-bold",
                    d.action.toLowerCase().includes("buy") ? "bg-accent-green/10 text-accent-greenSoft border-accent-green/40"
                      : d.action.toLowerCase().includes("sell") ? "bg-accent-red/10 text-accent-redSoft border-accent-red/40"
                      : "bg-bg-base text-text-secondary border-bg-border"
                  )}>
                    {d.action.split(" ")[0] || "—"}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-sm font-medium">{d.symbol || "—"}</span>
                      <span className="text-xs text-text-muted">{d.timestamp}</span>
                    </div>
                    {d.reason && (
                      <p className="text-text-secondary text-xs mt-1 line-clamp-2">{d.reason}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
