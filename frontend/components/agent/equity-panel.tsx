"use client";

import type { AgentEquityResponse } from "@/lib/api/types";
import { cn, formatPercent, formatCurrency } from "@/lib/utils";

export function EquityPanel({ data }: { data: AgentEquityResponse }) {
  const points = data.points || [];
  const m = data.metrics;

  if (points.length < 2) {
    return (
      <div className="card p-5">
        <h3 className="text-sm font-semibold mb-2">Performance</h3>
        <p className="text-text-muted text-sm">
          Need at least 2 equity snapshots. Run a few cycles and come back.
        </p>
      </div>
    );
  }

  // Build sparkline-style equity curve
  const W = 1000, H = 220, PADL = 50, PADR = 10, PADT = 12, PADB = 24;
  const values = points.map((p) => p.total_value);
  const yMin = Math.min(...values);
  const yMax = Math.max(...values);
  const yRange = (yMax - yMin) || 1;
  const xStep = (W - PADL - PADR) / Math.max(values.length - 1, 1);
  const xOf = (i: number) => PADL + i * xStep;
  const yOf = (v: number) => H - PADB - ((v - yMin) / yRange) * (H - PADT - PADB);

  const path = values.map((v, i) => `${i === 0 ? "M" : "L"} ${xOf(i)} ${yOf(v)}`).join(" ");
  const positive = values[values.length - 1] >= values[0];
  const stroke = positive ? "#4ade80" : "#f87171";
  const last = [xOf(values.length - 1), yOf(values[values.length - 1])] as const;
  const area = `${path} L ${last[0]} ${H - PADB} L ${xOf(0)} ${H - PADB} Z`;

  const ticks = [yMin, (yMin + yMax) / 2, yMax];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <Metric
          label="Total Return"
          value={formatPercent(m.total_return)}
          tone={m.total_return >= 0 ? "green" : "red"}
        />
        <Metric
          label="Annualized"
          value={formatPercent(m.annualized_return)}
          tone={m.annualized_return >= 0 ? "green" : "red"}
        />
        <Metric
          label="Sharpe"
          value={m.sharpe_ratio.toFixed(2)}
          tone={m.sharpe_ratio >= 1 ? "green" : m.sharpe_ratio <= 0 ? "red" : "amber"}
        />
        <Metric
          label="Max Drawdown"
          value={formatPercent(m.max_drawdown)}
          tone="red"
        />
        <Metric
          label="Alpha vs SPY"
          value={formatPercent(m.alpha)}
          tone={m.alpha >= 0 ? "green" : "red"}
        />
      </div>

      <div className="card p-5">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h3 className="text-sm font-semibold">Equity Curve</h3>
          <div className="text-xs text-text-muted">
            {points.length} day{points.length === 1 ? "" : "s"} ·{" "}
            <span className={cn(positive ? "text-accent-greenSoft" : "text-accent-redSoft", "font-semibold")}>
              {formatCurrency(values[values.length - 1])}
            </span>
          </div>
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-56">
          <defs>
            <linearGradient id="agentEquityFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity="0.25" />
              <stop offset="100%" stopColor={stroke} stopOpacity="0" />
            </linearGradient>
          </defs>
          {ticks.map((v, i) => (
            <g key={i}>
              <line x1={PADL} x2={W - PADR} y1={yOf(v)} y2={yOf(v)} stroke="#27272a" strokeWidth={1} />
              <text x={PADL - 6} y={yOf(v)} fill="#71717a" fontSize="10" textAnchor="end" alignmentBaseline="middle">
                ${(v / 1000).toFixed(0)}k
              </text>
            </g>
          ))}
          <path d={area} fill="url(#agentEquityFill)" />
          <path d={path} fill="none" stroke={stroke} strokeWidth={2} strokeLinejoin="round" />
          <circle cx={last[0]} cy={last[1]} r={3} fill={stroke} stroke="#09090b" strokeWidth={1.5} />
        </svg>
      </div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone: "green" | "red" | "amber" | "neutral" }) {
  const cls = tone === "green" ? "text-accent-greenSoft"
    : tone === "red" ? "text-accent-redSoft"
    : tone === "amber" ? "text-accent-amber"
    : "text-text-primary";
  return (
    <div className="card p-4 text-center">
      <div className="text-[10px] uppercase tracking-wider text-text-muted">{label}</div>
      <div className={cn("text-base font-bold tabular-nums mt-1", cls)}>{value}</div>
    </div>
  );
}
