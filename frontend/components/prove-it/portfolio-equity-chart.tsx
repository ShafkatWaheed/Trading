"use client";

import type { PortfolioEquityPoint } from "@/lib/api/types";
import { cn, formatPercent } from "@/lib/utils";

export function PortfolioEquityChart({ points }: { points: PortfolioEquityPoint[] }) {
  if (!points || points.length < 2) {
    return (
      <div className="card p-6 text-text-muted text-sm">
        Not enough data points for an equity curve.
      </div>
    );
  }

  const W = 1000, H = 320, PADL = 50, PADR = 60, PADT = 16, PADB = 28;

  const stratValues = points.map((p) => p.cumulative_return);
  const benchValues = points.map((p) => p.benchmark_return);
  const yMin = Math.min(...stratValues, ...benchValues);
  const yMax = Math.max(...stratValues, ...benchValues);
  const yRange = (yMax - yMin) || 1;

  const xStep = (W - PADL - PADR) / Math.max(points.length - 1, 1);
  const xOf = (i: number) => PADL + i * xStep;
  const yOf = (v: number) => H - PADB - ((v - yMin) / yRange) * (H - PADT - PADB);

  const stratPath = points.map((p, i) =>
    `${i === 0 ? "M" : "L"} ${xOf(i)} ${yOf(p.cumulative_return)}`
  ).join(" ");
  const benchPath = points.map((p, i) =>
    `${i === 0 ? "M" : "L"} ${xOf(i)} ${yOf(p.benchmark_return)}`
  ).join(" ");

  const stratEnd = stratValues[stratValues.length - 1];
  const benchEnd = benchValues[benchValues.length - 1];
  const stratPositive = stratEnd >= 0;
  const stratColor = stratPositive ? "#4ade80" : "#f87171";

  // Y ticks at sensible intervals
  const ticks: number[] = [];
  const tickCount = 4;
  for (let i = 0; i <= tickCount; i++) {
    ticks.push(yMin + (yRange / tickCount) * i);
  }

  const xLabels = [
    points[0]?.date,
    points[Math.floor(points.length / 2)]?.date,
    points[points.length - 1]?.date,
  ];

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
        <h3 className="text-base font-semibold">Equity Curve · vs SPY</h3>
        <div className="flex items-center gap-4 text-xs">
          <span className="inline-flex items-center gap-1.5">
            <span className="w-3 h-0.5" style={{ background: stratColor }} />
            <span className="text-text-secondary">Strategy</span>
            <span className={cn("font-bold tabular-nums", stratPositive ? "text-accent-greenSoft" : "text-accent-redSoft")}>
              {formatPercent(stratEnd)}
            </span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-3 h-0.5 bg-text-muted" />
            <span className="text-text-secondary">SPY</span>
            <span className={cn("font-bold tabular-nums", benchEnd >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft")}>
              {formatPercent(benchEnd)}
            </span>
          </span>
        </div>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-72">
        {/* Y gridlines */}
        {ticks.map((v, i) => (
          <g key={i}>
            <line x1={PADL} x2={W - PADR} y1={yOf(v)} y2={yOf(v)} stroke="#27272a" strokeWidth={1} />
            <text x={PADL - 6} y={yOf(v)} fill="#71717a" fontSize="10" textAnchor="end" alignmentBaseline="middle">
              {v >= 0 ? "+" : ""}{v.toFixed(1)}%
            </text>
          </g>
        ))}

        {/* Zero line */}
        {yMin <= 0 && yMax >= 0 && (
          <line x1={PADL} x2={W - PADR} y1={yOf(0)} y2={yOf(0)} stroke="#52525b" strokeWidth={1} strokeDasharray="3,3" />
        )}

        {/* Benchmark (gray) */}
        <path d={benchPath} fill="none" stroke="#71717a" strokeWidth={1.5} strokeDasharray="4,3" />
        {/* Strategy */}
        <path d={stratPath} fill="none" stroke={stratColor} strokeWidth={2} />

        {xLabels.map((d, i) => {
          if (!d) return null;
          const xs = [PADL, (W - PADR + PADL) / 2, W - PADR];
          return (
            <text
              key={i} x={xs[i]} y={H - 6}
              fill="#71717a" fontSize="10"
              textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}
            >
              {d.slice(0, 10)}
            </text>
          );
        })}
      </svg>
    </div>
  );
}
