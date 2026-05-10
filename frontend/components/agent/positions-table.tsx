"use client";

import Link from "next/link";
import type { AgentPosition } from "@/lib/api/types";
import { ArrowUpRight, Inbox } from "lucide-react";
import { cn, formatCurrency, formatPercent } from "@/lib/utils";

export function PositionsTable({ positions }: { positions: AgentPosition[] }) {
  if (positions.length === 0) {
    return (
      <div className="card p-8 text-center">
        <Inbox className="mx-auto text-text-muted mb-2" size={24} />
        <p className="text-text-muted text-sm">No open positions.</p>
        <p className="text-text-muted text-xs mt-1">Run a cycle to let the agent pick stocks.</p>
      </div>
    );
  }
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold">Open Positions</h3>
        <span className="text-[10px] uppercase tracking-wider text-text-muted">
          {positions.length} active
        </span>
      </div>
      <div className="overflow-x-auto -mx-2">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text-muted text-left uppercase tracking-wider">
              <th className="px-2 py-2">Symbol</th>
              <th className="px-2 py-2 text-right">Shares</th>
              <th className="px-2 py-2 text-right">Entry</th>
              <th className="px-2 py-2 text-right">Current</th>
              <th className="px-2 py-2 text-right">Stop</th>
              <th className="px-2 py-2 text-right">Target</th>
              <th className="px-2 py-2 text-right">P&amp;L</th>
              <th className="px-2 py-2 text-right">P&amp;L %</th>
              <th className="px-2 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => {
              const pos = p.pnl >= 0;
              return (
                <tr key={p.symbol} className="border-t border-bg-border">
                  <td className="px-2 py-3 font-mono font-bold">{p.symbol}</td>
                  <td className="px-2 py-3 text-right tabular-nums">{p.shares}</td>
                  <td className="px-2 py-3 text-right tabular-nums">{formatCurrency(p.entry_price, 2)}</td>
                  <td className="px-2 py-3 text-right tabular-nums">{formatCurrency(p.current_price, 2)}</td>
                  <td className="px-2 py-3 text-right tabular-nums text-text-muted">
                    {p.stop_loss != null ? formatCurrency(p.stop_loss, 2) : "—"}
                  </td>
                  <td className="px-2 py-3 text-right tabular-nums text-text-muted">
                    {p.target != null ? formatCurrency(p.target, 2) : "—"}
                  </td>
                  <td className={cn(
                    "px-2 py-3 text-right tabular-nums font-medium",
                    pos ? "text-accent-greenSoft" : "text-accent-redSoft"
                  )}>
                    {formatCurrency(p.pnl, 2)}
                  </td>
                  <td className={cn(
                    "px-2 py-3 text-right tabular-nums font-medium",
                    pos ? "text-accent-greenSoft" : "text-accent-redSoft"
                  )}>
                    {formatPercent(p.pnl_pct)}
                  </td>
                  <td className="px-2 py-3 text-right">
                    <Link
                      href={`/deep-dive/${p.symbol}`}
                      className="text-text-muted hover:text-accent-blue inline-flex"
                    >
                      <ArrowUpRight size={12} />
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
