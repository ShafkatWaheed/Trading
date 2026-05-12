"use client";

import { useState } from "react";
import Link from "next/link";
import { Bot, ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
import type { AiAnalystResponse } from "@/lib/api/types";
import { AiDecisionRow } from "@/components/prove-it/ai-decision-row";
import { cn, formatPercent } from "@/lib/utils";

type Props = {
  rows: AiAnalystResponse[];
  mode: "single" | "multi";
};

type SortKey = "win_rate" | "avg_return" | "total_trades" | "cycles_run";

export function AiMultiStockTable({ rows, mode }: Props) {
  const [sort, setSort] = useState<SortKey>("avg_return");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const sorted = [...rows].sort((a, b) => {
    const get = (r: AiAnalystResponse): number => {
      if (sort === "win_rate")     return r.win_rate ?? 0;
      if (sort === "avg_return")   return r.avg_return ?? 0;
      if (sort === "total_trades") return r.total_trades ?? 0;
      return r.cycles_run ?? 0;
    };
    return get(b) - get(a);
  });

  const toggleExpand = (sym: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(sym)) next.delete(sym);
      else next.add(sym);
      return next;
    });
  };

  // Aggregate stats across all stocks
  const totalTrades = rows.reduce((s, r) => s + (r.total_trades || 0), 0);
  const totalWins = rows.reduce((s, r) => s + (r.win_count || 0), 0);
  const avgWinRate = rows.length > 0
    ? rows.reduce((s, r) => s + (r.win_rate || 0), 0) / rows.length
    : 0;
  const avgReturn = rows.length > 0
    ? rows.reduce((s, r) => s + (r.avg_return || 0), 0) / rows.length
    : 0;

  return (
    <div className="space-y-4">
      {/* Aggregate header */}
      <div className="card p-4 border-l-4 border-accent-pink/40">
        <div className="flex items-center gap-2 mb-3">
          <Bot size={14} className={mode === "multi" ? "text-accent-violet" : "text-accent-pink"} />
          <h3 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">
            AI Analyst — Comparison across {rows.length} stocks
          </h3>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Stocks" value={rows.length.toString()} />
          <Stat label="Total Trades"  value={totalTrades.toString()} />
          <Stat label="Avg Win Rate"
                value={`${(avgWinRate * 100).toFixed(0)}%`}
                tone={avgWinRate >= 0.6 ? "green" : avgWinRate >= 0.45 ? "amber" : "red"} />
          <Stat label="Avg Return / Trade"
                value={formatPercent(avgReturn)}
                tone={avgReturn >= 0 ? "green" : "red"} />
        </div>
      </div>

      {/* Sortable per-stock table */}
      <div className="card p-4">
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Sort by</span>
          <SortChip current={sort} value="avg_return"   label="Avg Return"  onClick={setSort} />
          <SortChip current={sort} value="win_rate"     label="Win Rate"    onClick={setSort} />
          <SortChip current={sort} value="total_trades" label="Trade Count" onClick={setSort} />
          <SortChip current={sort} value="cycles_run"   label="Cycles"      onClick={setSort} />
        </div>

        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-text-muted text-left uppercase tracking-wider border-b border-bg-border">
                <th className="px-3 py-2"></th>
                <th className="px-3 py-2">Symbol</th>
                <th className="px-3 py-2 text-right">Cycles</th>
                <th className="px-3 py-2 text-right">Trades</th>
                <th className="px-3 py-2 text-right">Win Rate</th>
                <th className="px-3 py-2 text-right">Avg Return</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((row) => {
                const isOpen = expanded.has(row.symbol);
                const winPct = (row.win_rate ?? 0) * 100;
                return (
                  <>
                    <tr
                      key={row.symbol}
                      className={cn(
                        "border-b border-bg-divider cursor-pointer hover:bg-bg-base transition-colors",
                        isOpen && "bg-bg-base"
                      )}
                      onClick={() => toggleExpand(row.symbol)}
                    >
                      <td className="px-3 py-2 w-6">
                        {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      </td>
                      <td className="px-3 py-2 font-mono font-bold">
                        {row.symbol}
                        {row.error && (
                          <span className="ml-2 text-[10px] text-accent-redSoft">error</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{row.cycles_run}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{row.total_trades}</td>
                      <td className={cn(
                        "px-3 py-2 text-right tabular-nums font-semibold",
                        winPct >= 65 ? "text-accent-greenSoft" :
                        winPct >= 45 ? "text-accent-amber" :
                        row.total_trades > 0 ? "text-accent-redSoft" : "text-text-muted"
                      )}>
                        {row.total_trades > 0 ? `${winPct.toFixed(0)}%` : "—"}
                      </td>
                      <td className={cn(
                        "px-3 py-2 text-right tabular-nums font-semibold",
                        (row.avg_return ?? 0) >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft"
                      )}>
                        {row.total_trades > 0 ? formatPercent(row.avg_return) : "—"}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Link
                          href={`/deep-dive/${encodeURIComponent(row.symbol)}`}
                          onClick={(e) => e.stopPropagation()}
                          className="text-text-muted hover:text-accent-cyan inline-flex items-center gap-1 text-[11px]"
                          title="Open in Deep Dive"
                        >
                          <ExternalLink size={11} />
                        </Link>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr key={`${row.symbol}-detail`}>
                        <td colSpan={7} className="px-3 py-3 bg-bg-base">
                          {row.error ? (
                            <p className="text-[11px] text-accent-redSoft">{row.error}</p>
                          ) : row.decisions.length === 0 ? (
                            <p className="text-[11px] text-text-muted">No decisions captured.</p>
                          ) : (
                            <div className="space-y-1.5">
                              <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold mb-1">
                                Decision Log ({row.decisions.length})
                              </div>
                              {row.decisions.slice(0, 16).map((d, i) => (
                                <AiDecisionRow key={i} d={d} idx={i} />
                              ))}
                              {row.decisions.length > 16 && (
                                <p className="text-[10px] text-text-muted italic">
                                  + {row.decisions.length - 16} more — open Deep Dive for full log
                                </p>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>

        <p className="text-[10px] text-text-muted mt-3 pt-3 border-t border-bg-border">
          Click any row to expand the per-stock decision log. {mode === "multi" ? "Multi-agent runs" : "Single-agent runs"} are cached for 6h per (stock, period, cycles, mode) — re-running a row returns instantly.
        </p>
      </div>
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: {
  label: string; value: string; tone?: "neutral" | "green" | "amber" | "red";
}) {
  const color =
    tone === "green" ? "text-accent-greenSoft" :
    tone === "amber" ? "text-accent-amber" :
    tone === "red"   ? "text-accent-redSoft" :
    "text-text-primary";
  return (
    <div className="bg-bg-base rounded-md p-2.5 border border-bg-border">
      <div className="text-[10px] uppercase tracking-wider text-text-muted">{label}</div>
      <div className={cn("text-base font-bold tabular-nums mt-0.5", color)}>{value}</div>
    </div>
  );
}

function SortChip({ current, value, label, onClick }: {
  current: SortKey; value: SortKey; label: string; onClick: (v: SortKey) => void;
}) {
  const active = current === value;
  return (
    <button
      onClick={() => onClick(value)}
      className={cn(
        "px-2.5 py-1 rounded-md text-[11px] font-medium border transition-all",
        active
          ? "bg-accent-pink/10 text-accent-pink border-accent-pink/40"
          : "bg-bg-base text-text-secondary border-bg-border hover:border-bg-borderHi"
      )}
    >
      {label}
    </button>
  );
}
