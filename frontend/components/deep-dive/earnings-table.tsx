"use client";

import type { EarningsRow } from "@/lib/api/types";
import { Calendar } from "lucide-react";
import { cn } from "@/lib/utils";

export function EarningsTable({ rows }: { rows: EarningsRow[] }) {
  if (!rows || rows.length === 0) return null;

  const today = new Date().toISOString().slice(0, 10);
  const future = rows.filter((r) => r.date && r.date >= today);
  const past = rows.filter((r) => r.date && r.date < today);

  return (
    <div className="card-muted p-5">
      <div className="flex items-center gap-2 mb-3">
        <Calendar size={14} className="text-accent-amber" />
        <h3 className="text-sm font-semibold">Earnings History &amp; Upcoming</h3>
      </div>

      {future.length > 0 && (
        <div className="mb-4 p-3 bg-accent-amber/5 border border-accent-amber/30 rounded-lg">
          <div className="text-xs uppercase tracking-wider text-accent-amber font-semibold">
            Next: {future[0].date}
          </div>
          {future[0].eps_estimate != null && (
            <div className="text-xs text-text-secondary mt-1">
              EPS Estimate: <span className="font-mono tabular-nums">${future[0].eps_estimate.toFixed(2)}</span>
            </div>
          )}
        </div>
      )}

      {past.length > 0 && (
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-text-muted uppercase tracking-wider">
                <th className="px-2 py-2">Date</th>
                <th className="px-2 py-2 text-right">EPS Est</th>
                <th className="px-2 py-2 text-right">EPS Actual</th>
                <th className="px-2 py-2 text-right">Surprise</th>
              </tr>
            </thead>
            <tbody>
              {past.slice(0, 6).map((r, i) => (
                <tr key={i} className="border-t border-bg-border">
                  <td className="px-2 py-2 tabular-nums">{r.date}</td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {r.eps_estimate != null ? `$${r.eps_estimate.toFixed(2)}` : "—"}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {r.eps_actual != null ? `$${r.eps_actual.toFixed(2)}` : "—"}
                  </td>
                  <td className={cn(
                    "px-2 py-2 text-right tabular-nums",
                    r.surprise_pct == null ? "text-text-muted"
                      : r.surprise_pct >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft"
                  )}>
                    {r.surprise_pct != null
                      ? `${r.surprise_pct >= 0 ? "+" : ""}${r.surprise_pct.toFixed(1)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
