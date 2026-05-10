"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Compass,
  Loader2,
  Crown,
  TrendingUp,
  Filter,
  Users,
  Zap,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { agentApi } from "@/lib/api/endpoints";
import type {
  CandidateScreen,
  ConsensusPick,
  AgentVotePicks,
  PortfolioExecuteResponse,
} from "@/lib/api/types";
import { cn, formatPercent, formatCurrency } from "@/lib/utils";

const AGENT_ICON: Record<string, string> = {
  momentum: "🚀",
  value: "📊",
  contrarian: "🔄",
  macro: "🌍",
  disruption: "🔗",
  insider: "🕵️",
  flow: "💧",
};
const AGENT_LABEL: Record<string, string> = {
  momentum: "Momentum",
  value: "Value",
  contrarian: "Contrarian",
  macro: "Macro",
  disruption: "Disruption",
  insider: "Insider Shadow",
  flow: "Flow Tracker",
};

export function PortfolioPickPanel() {
  const [topN, setTopN] = useState(15);
  const [minAgents, setMinAgents] = useState(3);
  const [confirming, setConfirming] = useState(false);

  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (body: { top_n: number; min_agents: number }) =>
      agentApi.portfolioPick(body),
  });

  const executeMutation = useMutation({
    mutationFn: (payload: { symbols: string[]; reasons: Record<string, string> }) =>
      agentApi.portfolioExecute(payload.symbols, payload.reasons),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent", "positions"] });
      queryClient.invalidateQueries({ queryKey: ["agent", "status"] });
      queryClient.invalidateQueries({ queryKey: ["agent", "equity"] });
      queryClient.invalidateQueries({ queryKey: ["agent", "decisions", 20] });
      setConfirming(false);
    },
  });

  const result = mutation.data;
  const exec = executeMutation.data;

  const buildExecutePayload = (
    picks: ConsensusPick[],
  ): { symbols: string[]; reasons: Record<string, string> } => {
    const symbols = picks.map((p) => p.symbol);
    const reasons: Record<string, string> = {};
    for (const p of picks) {
      const top = p.votes.slice(0, 2).map((v) => `${v.agent}: ${v.reason}`).join(" | ");
      reasons[p.symbol] = `Consensus ${p.agent_count}/7 — ${top}`;
    }
    return { symbols, reasons };
  };

  return (
    <section className="space-y-3">
      <div className="card p-5">
        <div className="flex items-start justify-between gap-3 flex-wrap mb-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Compass size={14} className="text-accent-violet" strokeWidth={2.4} />
              <h3 className="text-sm font-semibold tracking-tight">
                Portfolio AI — pick stocks now
              </h3>
            </div>
            <p className="text-[11px] text-text-muted leading-snug">
              Screen all 69 stocks → 7 personality agents each pick up to 3 →
              consensus ≥{minAgents} agents. Live data, no execution.
            </p>
          </div>
          <span className="badge-violet text-[10px] uppercase tracking-wider">
            7 agents · ~70-90s
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
              Top N candidates
            </label>
            <input
              type="number"
              min={5}
              max={30}
              value={topN}
              onChange={(e) =>
                setTopN(Math.max(5, Math.min(30, Number(e.target.value) || 15)))
              }
              className="mt-1 w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs tabular-nums focus:outline-none focus:border-accent-violet/60"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
              Min agents for consensus
            </label>
            <input
              type="number"
              min={2}
              max={7}
              value={minAgents}
              onChange={(e) =>
                setMinAgents(Math.max(2, Math.min(7, Number(e.target.value) || 3)))
              }
              className="mt-1 w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs tabular-nums focus:outline-none focus:border-accent-violet/60"
            />
          </div>
          <div className="sm:col-span-1 flex items-end">
            <button
              onClick={() => mutation.mutate({ top_n: topN, min_agents: minAgents })}
              disabled={mutation.isPending}
              className={cn(
                "w-full px-4 py-2 rounded-md text-sm font-semibold flex items-center justify-center gap-2 transition-all",
                "bg-accent-violet/10 border border-accent-violet/40 hover:bg-accent-violet/20 text-accent-violet",
                "disabled:opacity-50",
              )}
            >
              {mutation.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Running pipeline…
                </>
              ) : (
                <>
                  <Compass size={14} />
                  Run Portfolio Pick
                </>
              )}
            </button>
          </div>
        </div>

        {mutation.isError && (
          <div className="mt-2 text-[11px] text-accent-redSoft">
            Failed: {(mutation.error as Error)?.message ?? "Unknown error"}
          </div>
        )}
      </div>

      {result?.error && (
        <div className="card p-4 border-l-4 border-accent-red/40">
          <p className="text-accent-redSoft text-sm">{result.error}</p>
        </div>
      )}

      {result && !result.error && (
        <>
          {/* Top stat strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="Universe" value={`${result.universe_size}`} />
            <Stat label="Screened" value={`${result.candidates_screened.length}`} />
            <Stat
              label="Consensus picks"
              value={`${result.consensus_picks.length}`}
              tone="violet"
            />
            <Stat
              label="Suggested portfolio"
              value={`${result.final_portfolio.length}`}
              tone="green"
            />
          </div>

          {/* Final portfolio */}
          {result.final_portfolio.length > 0 && (
            <div className="card p-5">
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                <Crown size={14} className="text-accent-amber" strokeWidth={2.4} />
                <h4 className="text-sm font-semibold tracking-tight">
                  Suggested portfolio
                </h4>
                <span className="text-[10px] uppercase tracking-wider text-text-muted">
                  Top {result.final_portfolio.length} by agent consensus
                </span>
                <div className="ml-auto">
                  {!confirming ? (
                    <button
                      onClick={() => setConfirming(true)}
                      disabled={executeMutation.isPending}
                      className={cn(
                        "px-3 py-1.5 rounded-md text-xs font-semibold flex items-center gap-1.5 transition-all",
                        "bg-accent-green/10 border border-accent-green/40 hover:bg-accent-green/20 text-accent-greenSoft",
                        "disabled:opacity-50",
                      )}
                    >
                      <Zap size={12} strokeWidth={2.4} />
                      Execute as paper trades
                    </button>
                  ) : (
                    <div className="flex items-center gap-2 bg-accent-green/5 border border-accent-green/40 rounded-md px-2 py-1">
                      <span className="text-[11px] text-accent-greenSoft">
                        Open {result.final_portfolio.length} long position{result.final_portfolio.length === 1 ? "" : "s"}?
                      </span>
                      <button
                        onClick={() =>
                          executeMutation.mutate(buildExecutePayload(result.final_portfolio))
                        }
                        disabled={executeMutation.isPending}
                        className="text-[11px] font-bold text-accent-greenSoft hover:underline disabled:opacity-50"
                      >
                        {executeMutation.isPending ? "Executing…" : "Confirm"}
                      </button>
                      <span className="text-text-muted">·</span>
                      <button
                        onClick={() => setConfirming(false)}
                        disabled={executeMutation.isPending}
                        className="text-[11px] text-text-muted hover:text-text-primary disabled:opacity-50"
                      >
                        Cancel
                      </button>
                    </div>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {result.final_portfolio.map((p) => (
                  <ConsensusCard key={p.symbol} p={p} candidates={result.candidates_screened} />
                ))}
              </div>

              {/* Execution result */}
              {executeMutation.isError && (
                <div className="mt-3 text-[11px] text-accent-redSoft">
                  Execution failed: {(executeMutation.error as Error)?.message ?? "Unknown error"}
                </div>
              )}
              {exec && <ExecutionResult exec={exec} />}
            </div>
          )}

          {/* Agent vote matrix */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-3">
              <Users size={14} className="text-accent-blue" strokeWidth={2.4} />
              <h4 className="text-sm font-semibold tracking-tight">
                Agent vote matrix
              </h4>
              <span className="text-[10px] uppercase tracking-wider text-text-muted ml-auto">
                Who picked what
              </span>
            </div>
            <VoteMatrix
              candidates={result.candidates_screened}
              votes={result.agent_votes}
            />
          </div>

          {/* Per-agent picks expanded */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-3">
              <TrendingUp size={14} className="text-accent-pink" strokeWidth={2.4} />
              <h4 className="text-sm font-semibold tracking-tight">
                Each agent's reasoning
              </h4>
            </div>
            <div className="space-y-2">
              {result.agent_votes.map((v) => (
                <AgentVoteRow key={v.agent} v={v} />
              ))}
            </div>
          </div>

          {/* Candidate ladder (collapsed by default would be nicer, keep visible for transparency) */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-3">
              <Filter size={14} className="text-accent-cyan" strokeWidth={2.4} />
              <h4 className="text-sm font-semibold tracking-tight">
                Candidate ladder — what every agent saw
              </h4>
              <span className="text-[10px] uppercase tracking-wider text-text-muted ml-auto">
                Ranked by opportunity score
              </span>
            </div>
            <CandidateLadder candidates={result.candidates_screened} consensus={result.consensus_picks} />
          </div>
        </>
      )}
    </section>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "violet" | "green";
}) {
  return (
    <div className="card p-4 text-center">
      <div className="text-[10px] uppercase tracking-wider text-text-muted">{label}</div>
      <div
        className={cn(
          "text-xl font-bold tabular-nums mt-1",
          tone === "violet" && "text-accent-violet",
          tone === "green" && "text-accent-greenSoft",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function ConsensusCard({
  p,
  candidates,
}: {
  p: ConsensusPick;
  candidates: CandidateScreen[];
}) {
  const c = candidates.find((x) => x.symbol === p.symbol);
  return (
    <div className="rounded-md border border-accent-amber/30 bg-accent-amber/5 p-3">
      <div className="flex items-center gap-2 mb-1">
        <span className="font-mono text-sm font-bold">{p.symbol}</span>
        <span className="text-[10px] text-text-muted">{c?.sector ?? "—"}</span>
        <span className="ml-auto badge bg-accent-amber/15 text-accent-amber border-accent-amber/40 text-[10px] font-bold">
          {p.agent_count}/7 agents
        </span>
      </div>
      {c && (
        <div className="text-[11px] text-text-secondary tabular-nums mb-1.5">
          ${c.price?.toFixed(2)} · opp {c.opportunity_score} · RSI{" "}
          {c.rsi !== null ? c.rsi.toFixed(0) : "—"}
        </div>
      )}
      <div className="flex flex-wrap gap-1 mb-1.5">
        {p.votes.map((v) => (
          <span
            key={v.agent}
            className="text-[10px] bg-bg-card2 border border-bg-divider rounded px-1.5 py-0.5 inline-flex items-center gap-1"
            title={v.reason}
          >
            <span>{AGENT_ICON[v.agent] ?? "🤖"}</span>
            <span className="text-text-secondary">{AGENT_LABEL[v.agent] ?? v.agent}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function VoteMatrix({
  candidates,
  votes,
}: {
  candidates: CandidateScreen[];
  votes: AgentVotePicks[];
}) {
  // Build a Set per agent of picked symbols
  const pickMap: Record<string, Set<string>> = {};
  for (const v of votes) {
    pickMap[v.agent] = new Set(v.picks.map((p) => p.symbol));
  }
  const agents = votes.map((v) => v.agent);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px] tabular-nums">
        <thead>
          <tr className="text-text-muted text-[10px] uppercase tracking-wider">
            <th className="text-left py-1.5 pr-3">Symbol</th>
            <th className="text-right py-1.5 pr-3">Opp</th>
            <th className="text-right py-1.5 pr-3">Price</th>
            {agents.map((a) => (
              <th key={a} className="text-center py-1.5 px-1.5" title={AGENT_LABEL[a]}>
                <span className="text-base">{AGENT_ICON[a] ?? "🤖"}</span>
              </th>
            ))}
            <th className="text-right py-1.5 pl-3 w-10">Σ</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((c) => {
            const total = agents.reduce(
              (acc, a) => acc + (pickMap[a]?.has(c.symbol) ? 1 : 0),
              0,
            );
            return (
              <tr
                key={c.symbol}
                className={cn(
                  "border-t border-bg-divider",
                  total >= 3 && "bg-accent-amber/5",
                  total === 0 && "opacity-60",
                )}
              >
                <td className="py-1.5 pr-3">
                  <span className="font-mono font-semibold text-text-primary">
                    {c.symbol}
                  </span>
                  <span className="text-text-muted ml-2 text-[10px]">
                    {c.sector?.slice(0, 14) ?? ""}
                  </span>
                </td>
                <td className="py-1.5 pr-3 text-right text-text-secondary">
                  {c.opportunity_score}
                </td>
                <td className="py-1.5 pr-3 text-right text-text-secondary">
                  ${c.price?.toFixed(2)}
                </td>
                {agents.map((a) => {
                  const picked = pickMap[a]?.has(c.symbol);
                  return (
                    <td key={a} className="py-1.5 px-1.5 text-center">
                      {picked ? (
                        <span className="text-accent-greenSoft font-bold">●</span>
                      ) : (
                        <span className="text-text-dim">·</span>
                      )}
                    </td>
                  );
                })}
                <td
                  className={cn(
                    "py-1.5 pl-3 text-right font-semibold",
                    total >= 3 ? "text-accent-amber" : "text-text-secondary",
                  )}
                >
                  {total}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function AgentVoteRow({ v }: { v: AgentVotePicks }) {
  return (
    <div className="rounded-md border border-bg-divider bg-bg-card2/40 px-3 py-2">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-base">{AGENT_ICON[v.agent] ?? "🤖"}</span>
        <span className="text-xs font-bold text-text-primary">
          {AGENT_LABEL[v.agent] ?? v.agent}
        </span>
        <span className="ml-auto text-[10px] text-text-muted">
          {v.picks.length === 0 ? "NONE" : `${v.picks.length} pick${v.picks.length > 1 ? "s" : ""}`}
        </span>
      </div>
      {v.picks.length === 0 ? (
        <p className="text-[11px] text-text-muted italic pl-7 leading-snug">
          {v.raw.slice(0, 200) || "Passed — no candidates fit."}
        </p>
      ) : (
        <ul className="pl-7 space-y-1">
          {v.picks.map((p) => (
            <li key={p.symbol} className="text-[11px]">
              <span className="font-mono font-bold text-accent-greenSoft mr-2">
                {p.symbol}
              </span>
              <span className="text-text-secondary leading-snug">{p.reason}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ExecutionResult({ exec }: { exec: PortfolioExecuteResponse }) {
  const total = exec.executed.length + exec.skipped.length;
  return (
    <div className="mt-4 rounded-md border border-bg-divider bg-bg-base/60 p-3">
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <Zap size={12} className="text-accent-greenSoft" strokeWidth={2.4} />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
          Execution result
        </span>
        <span className="text-[10px] text-text-dim">{exec.run_date}</span>
        <span className="ml-auto text-[10px] text-text-muted">
          {exec.executed.length}/{total} opened ·{" "}
          <span className="tabular-nums text-text-secondary">
            {formatCurrency(exec.cash_remaining)}
          </span>{" "}
          cash · {exec.open_positions}/{exec.max_positions} positions
        </span>
      </div>

      {exec.executed.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] uppercase tracking-wider text-accent-greenSoft font-semibold mb-1">
            Opened
          </div>
          <ul className="space-y-0.5">
            {exec.executed.map((t) => (
              <li
                key={t.symbol}
                className="text-[11px] flex items-center gap-2 tabular-nums"
              >
                <CheckCircle2
                  size={11}
                  className="text-accent-greenSoft"
                  strokeWidth={2.4}
                />
                <span className="font-mono font-bold text-text-primary w-14">
                  {t.symbol}
                </span>
                <span className="text-text-secondary">
                  {t.shares} sh @ ${t.price.toFixed(2)}
                </span>
                <span className="text-text-muted ml-auto">
                  ${(t.shares * t.price).toFixed(0)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {exec.skipped.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-accent-redSoft font-semibold mb-1">
            Skipped
          </div>
          <ul className="space-y-0.5">
            {exec.skipped.map((s) => (
              <li
                key={s.symbol}
                className="text-[11px] flex items-start gap-2"
              >
                <XCircle
                  size={11}
                  className="text-accent-redSoft mt-0.5 shrink-0"
                  strokeWidth={2.4}
                />
                <span className="font-mono font-bold text-text-primary w-14 shrink-0">
                  {s.symbol}
                </span>
                <span className="text-text-secondary leading-snug">{s.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function CandidateLadder({
  candidates,
  consensus,
}: {
  candidates: CandidateScreen[];
  consensus: ConsensusPick[];
}) {
  const consensusSet = new Set(consensus.map((c) => c.symbol));
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px] tabular-nums">
        <thead>
          <tr className="text-text-muted text-[10px] uppercase tracking-wider">
            <th className="text-left py-1.5 pr-3">#</th>
            <th className="text-left py-1.5 pr-3">Symbol</th>
            <th className="text-left py-1.5 pr-3">Sector</th>
            <th className="text-right py-1.5 pr-3">Opp</th>
            <th className="text-left py-1.5 pr-3">Strategy</th>
            <th className="text-right py-1.5 pr-3">Price</th>
            <th className="text-right py-1.5 pr-3">20d</th>
            <th className="text-right py-1.5 pr-3">RSI</th>
            <th className="text-right py-1.5 pr-3">Vol</th>
            <th className="text-right py-1.5 pl-3">Sig</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((c, i) => (
            <tr
              key={c.symbol}
              className={cn(
                "border-t border-bg-divider",
                consensusSet.has(c.symbol) && "bg-accent-violet/5",
              )}
            >
              <td className="py-1.5 pr-3 text-text-dim">{i + 1}</td>
              <td className="py-1.5 pr-3 font-mono font-semibold text-text-primary">
                {c.symbol}
              </td>
              <td className="py-1.5 pr-3 text-text-secondary">{c.sector ?? "—"}</td>
              <td className="py-1.5 pr-3 text-right text-accent-violet font-semibold">
                {c.opportunity_score}
              </td>
              <td className="py-1.5 pr-3 text-text-secondary">{c.strategy}</td>
              <td className="py-1.5 pr-3 text-right text-text-secondary">
                ${c.price?.toFixed(2)}
              </td>
              <td
                className={cn(
                  "py-1.5 pr-3 text-right",
                  (c.change_20d ?? 0) >= 0
                    ? "text-accent-greenSoft"
                    : "text-accent-redSoft",
                )}
              >
                {c.change_20d !== null ? formatPercent(c.change_20d / 100) : "—"}
              </td>
              <td className="py-1.5 pr-3 text-right text-text-secondary">
                {c.rsi !== null ? c.rsi.toFixed(0) : "—"}
              </td>
              <td className="py-1.5 pr-3 text-right text-text-secondary">
                {c.vol_ratio !== null ? `${c.vol_ratio.toFixed(1)}×` : "—"}
              </td>
              <td className="py-1.5 pl-3 text-right">
                <span className="text-accent-greenSoft">{c.bull_signals}↑</span>
                {" / "}
                <span className="text-accent-redSoft">{c.bear_signals}↓</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
