"use client";

import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  History,
  Loader2,
  TrendingUp,
  Activity,
  CalendarDays,
} from "lucide-react";
import { simulationApi } from "@/lib/api/endpoints";
import type { WalkForwardSimResponse, SimEquityPoint, SimTrade } from "@/lib/api/types";
import { cn, formatCurrency, formatPercent } from "@/lib/utils";

const DEFAULT_START = "2026-02-01";
const DEFAULT_END = "2026-04-30";

export function PortfolioSimRunner() {
  const [startDate, setStartDate] = useState(DEFAULT_START);
  const [endDate, setEndDate] = useState(DEFAULT_END);
  const [cycleDays, setCycleDays] = useState(14);
  const [initialCap, setInitialCap] = useState(100_000);
  const [maxPositions, setMaxPositions] = useState(5);
  const [minAgents, setMinAgents] = useState(3);
  const [topN, setTopN] = useState(12);

  const mutation = useMutation({
    mutationFn: (body: {
      start_date: string;
      end_date: string;
      cycle_days: number;
      initial_capital: number;
      max_positions: number;
      min_agents: number;
      top_n: number;
    }) => simulationApi.portfolioAgent(body),
  });

  const result = mutation.data;

  // Estimate runtime: 1 universe fetch (~30-60s if not cached) +
  // (cycles × 7 agents) Claude calls (parallel-batched 4 at a time, ~3.5s/batch)
  const cycleCount = useMemo(() => {
    try {
      const s = new Date(startDate).getTime();
      const e = new Date(endDate).getTime();
      const days = Math.max(0, (e - s) / 86400_000);
      return Math.max(1, Math.floor(days / cycleDays));
    } catch {
      return 0;
    }
  }, [startDate, endDate, cycleDays]);

  const claudeCalls = cycleCount * 7;
  const eta = Math.round(60 + (claudeCalls / 4) * 3.5);

  return (
    <section className="space-y-3">
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <History size={14} className="text-accent-cyan" strokeWidth={2.4} />
          <h3 className="text-sm font-semibold tracking-tight">
            Walk-forward AI simulation
          </h3>
          <span className="text-[10px] uppercase tracking-wider text-text-muted">
            Past data · no future-data leak
          </span>
          <span className="ml-auto badge-zinc text-[10px] uppercase tracking-wider">
            {cycleCount} cycle{cycleCount === 1 ? "" : "s"} · ~{claudeCalls} Claude calls · ~{eta}s
          </span>
        </div>

        <p className="text-[11px] text-text-muted leading-snug mb-3">
          Replay the same screen → 7-agent vote → consensus pipeline at each cycle date in the
          past. Every fetch is sliced to that date — no closing prices, fundamentals, news, or
          filings after t enter the prompt. Output: equity curve, trade journal, per-cycle log.
        </p>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
          <Field label="Start date">
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-cyan/60"
            />
          </Field>
          <Field label="End date">
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs focus:outline-none focus:border-accent-cyan/60"
            />
          </Field>
          <Field label="Cycle days">
            <input
              type="number"
              min={5}
              max={60}
              value={cycleDays}
              onChange={(e) => setCycleDays(Math.max(5, Math.min(60, Number(e.target.value) || 14)))}
              className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs tabular-nums focus:outline-none focus:border-accent-cyan/60"
            />
          </Field>
          <Field label="Initial capital">
            <input
              type="number"
              min={1000}
              step={1000}
              value={initialCap}
              onChange={(e) => setInitialCap(Math.max(1000, Number(e.target.value) || 100000))}
              className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs tabular-nums focus:outline-none focus:border-accent-cyan/60"
            />
          </Field>
        </div>

        <div className="grid grid-cols-3 gap-3 mb-3">
          <Field label="Max positions">
            <input
              type="number"
              min={1}
              max={10}
              value={maxPositions}
              onChange={(e) => setMaxPositions(Math.max(1, Math.min(10, Number(e.target.value) || 5)))}
              className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs tabular-nums focus:outline-none focus:border-accent-cyan/60"
            />
          </Field>
          <Field label="Min agents">
            <input
              type="number"
              min={2}
              max={7}
              value={minAgents}
              onChange={(e) => setMinAgents(Math.max(2, Math.min(7, Number(e.target.value) || 3)))}
              className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs tabular-nums focus:outline-none focus:border-accent-cyan/60"
            />
          </Field>
          <Field label="Top N candidates">
            <input
              type="number"
              min={5}
              max={30}
              value={topN}
              onChange={(e) => setTopN(Math.max(5, Math.min(30, Number(e.target.value) || 12)))}
              className="w-full bg-bg-base border border-bg-border rounded-md px-2 py-1.5 text-xs tabular-nums focus:outline-none focus:border-accent-cyan/60"
            />
          </Field>
        </div>

        <button
          onClick={() =>
            mutation.mutate({
              start_date: startDate,
              end_date: endDate,
              cycle_days: cycleDays,
              initial_capital: initialCap,
              max_positions: maxPositions,
              min_agents: minAgents,
              top_n: topN,
            })
          }
          disabled={mutation.isPending}
          className={cn(
            "w-full px-4 py-2.5 rounded-md text-sm font-semibold flex items-center justify-center gap-2 transition-all",
            "bg-accent-cyan/10 border border-accent-cyan/40 hover:bg-accent-cyan/20 text-accent-cyan",
            "disabled:opacity-50",
          )}
        >
          {mutation.isPending ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              Running {cycleCount} cycles… stay on this tab
            </>
          ) : (
            <>
              <CalendarDays size={14} />
              Run walk-forward simulation
            </>
          )}
        </button>

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

      {result && !result.error && result.summary && (
        <SimResultView result={result} />
      )}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
        {label}
      </label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function SimResultView({ result }: { result: WalkForwardSimResponse }) {
  const s = result.summary!;
  return (
    <>
      {/* Headline metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Metric label="Final equity" value={formatCurrency(s.final_equity)} tone="cyan" />
        <Metric
          label="Total return"
          value={`${s.total_return_pct >= 0 ? "+" : ""}${s.total_return_pct.toFixed(2)}%`}
          tone={s.total_return_pct >= 0 ? "green" : "red"}
        />
        <Metric
          label="Win rate"
          value={`${(s.win_rate * 100).toFixed(0)}%`}
          tone={s.win_rate >= 0.5 ? "green" : s.win_rate < 0.4 ? "red" : "amber"}
        />
        <Metric label="Trades" value={`${s.winners}/${s.total_trades}`} />
      </div>

      {/* Equity curve */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp size={14} className="text-accent-cyan" strokeWidth={2.4} />
          <h4 className="text-sm font-semibold tracking-tight">Equity curve</h4>
          <span className="text-[10px] uppercase tracking-wider text-text-muted ml-auto">
            ${s.initial_capital.toLocaleString()} → ${s.final_equity.toLocaleString()}
          </span>
        </div>
        <EquitySparkline points={result.equity_curve} initial={s.initial_capital} />
      </div>

      {/* Trades */}
      {result.trades.length > 0 && (
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <Activity size={14} className="text-accent-pink" strokeWidth={2.4} />
            <h4 className="text-sm font-semibold tracking-tight">Trade journal</h4>
            <span className="text-[10px] uppercase tracking-wider text-text-muted ml-auto">
              {result.trades.length} closed
            </span>
          </div>
          <TradesTable trades={result.trades} />
        </div>
      )}

      {/* Per-cycle log */}
      {result.cycles.length > 0 && (
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <CalendarDays size={14} className="text-accent-violet" strokeWidth={2.4} />
            <h4 className="text-sm font-semibold tracking-tight">
              Per-cycle decisions
            </h4>
          </div>
          <div className="space-y-2">
            {result.cycles.map((c) => (
              <CycleRow key={c.cycle_index} cycle={c} />
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "cyan" | "green" | "red" | "amber";
}) {
  return (
    <div className="card p-4 text-center">
      <div className="text-[10px] uppercase tracking-wider text-text-muted">{label}</div>
      <div
        className={cn(
          "text-xl font-bold tabular-nums mt-1",
          tone === "cyan" && "text-accent-cyan",
          tone === "green" && "text-accent-greenSoft",
          tone === "red" && "text-accent-redSoft",
          tone === "amber" && "text-accent-amber",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function EquitySparkline({
  points,
  initial,
}: {
  points: SimEquityPoint[];
  initial: number;
}) {
  if (points.length < 2) {
    return (
      <p className="text-[11px] text-text-muted">
        Not enough cycles to render a curve.
      </p>
    );
  }
  const values = points.map((p) => p.equity);
  const min = Math.min(initial, ...values);
  const max = Math.max(initial, ...values);
  const range = max - min || 1;
  const w = 100;
  const h = 28;

  const path = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((p.equity - min) / range) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const initialY = h - ((initial - min) / range) * h;

  return (
    <div className="bg-bg-base border border-bg-divider rounded-md p-3">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-24" preserveAspectRatio="none">
        <line
          x1="0"
          y1={initialY}
          x2={w}
          y2={initialY}
          stroke="rgba(161,161,170,0.25)"
          strokeWidth="0.3"
          strokeDasharray="1 1"
        />
        <path
          d={path}
          fill="none"
          stroke="#06b6d4"
          strokeWidth="0.6"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div className="flex justify-between text-[10px] text-text-muted mt-2 tabular-nums">
        <span>{points[0].date} · ${initial.toLocaleString()}</span>
        <span>
          {points[points.length - 1].date} · ${points[points.length - 1].equity.toLocaleString()}
        </span>
      </div>
    </div>
  );
}

function TradesTable({ trades }: { trades: SimTrade[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px] tabular-nums">
        <thead>
          <tr className="text-text-muted text-[10px] uppercase tracking-wider">
            <th className="text-left py-1.5 pr-3">Symbol</th>
            <th className="text-left py-1.5 pr-3">Entry</th>
            <th className="text-left py-1.5 pr-3">Exit</th>
            <th className="text-right py-1.5 pr-3">In/Out</th>
            <th className="text-right py-1.5 pr-3">Sh</th>
            <th className="text-right py-1.5 pr-3">P&L</th>
            <th className="text-right py-1.5 pr-3">%</th>
            <th className="text-right py-1.5 pl-3">Vote</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i} className="border-t border-bg-divider">
              <td className="py-1.5 pr-3 font-mono font-semibold">{t.symbol}</td>
              <td className="py-1.5 pr-3 text-text-secondary">{t.entry_date}</td>
              <td className="py-1.5 pr-3 text-text-secondary">{t.exit_date}</td>
              <td className="py-1.5 pr-3 text-right text-text-secondary">
                ${t.entry_price.toFixed(2)} → ${t.exit_price.toFixed(2)}
              </td>
              <td className="py-1.5 pr-3 text-right text-text-secondary">{t.shares}</td>
              <td
                className={cn(
                  "py-1.5 pr-3 text-right font-semibold",
                  t.pnl >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft",
                )}
              >
                ${t.pnl.toFixed(0)}
              </td>
              <td
                className={cn(
                  "py-1.5 pr-3 text-right",
                  t.pnl_pct >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft",
                )}
              >
                {t.pnl_pct >= 0 ? "+" : ""}
                {t.pnl_pct.toFixed(1)}%
              </td>
              <td className="py-1.5 pl-3 text-right text-text-muted">
                {t.consensus_count}/7
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CycleRow({
  cycle,
}: {
  cycle: WalkForwardSimResponse["cycles"][number];
}) {
  const [open, setOpen] = useState(false);
  const opened = cycle.opened?.length ?? 0;
  const consensus = cycle.consensus_picks?.length ?? 0;
  return (
    <div className="rounded-md border border-bg-divider bg-bg-card2/40">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full px-3 py-2 flex items-center gap-3 hover:bg-bg-card2/60 transition-colors text-left"
      >
        <span className="text-[10px] font-mono text-text-dim w-6">
          #{cycle.cycle_index + 1}
        </span>
        <span className="font-mono text-xs tabular-nums text-text-secondary w-24">
          {cycle.date}
        </span>
        <span className="text-[10px] text-text-muted">
          {cycle.candidates_screened?.length ?? 0} screened · {consensus} consensus · {opened} opened
        </span>
        <span className="ml-auto text-[10px] text-text-dim">
          {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div className="border-t border-bg-divider p-3 space-y-2 text-[11px]">
          {cycle.skipped && (
            <div className="text-text-muted italic">Skipped — {cycle.skipped}</div>
          )}
          {cycle.opened && cycle.opened.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-accent-greenSoft font-semibold mb-1">
                Opened this cycle
              </div>
              <ul className="space-y-0.5">
                {cycle.opened.map((o) => (
                  <li key={o.symbol} className="tabular-nums">
                    <span className="font-mono font-bold w-12 inline-block">{o.symbol}</span>
                    <span className="text-text-secondary ml-2">
                      {o.shares} sh @ ${o.entry_price.toFixed(2)} on {o.entry_date}
                    </span>
                    <span className="text-text-muted ml-2">
                      ({o.consensus_count}/7 agents)
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {cycle.agent_votes && cycle.agent_votes.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold mb-1">
                Agent picks
              </div>
              <ul className="space-y-0.5">
                {cycle.agent_votes.map((v) => (
                  <li key={v.agent} className="text-text-secondary">
                    <span className="text-text-primary font-semibold capitalize w-20 inline-block">
                      {v.agent}:
                    </span>
                    {v.picks.length === 0 ? (
                      <span className="text-text-muted italic">none</span>
                    ) : (
                      v.picks.map((p, i) => (
                        <span key={p.symbol} className="ml-1">
                          {i > 0 && ", "}
                          <span className="font-mono">{p.symbol}</span>
                        </span>
                      ))
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
