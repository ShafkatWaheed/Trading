"use client";

import type { PeriodChange } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function PriceChart({ data }: { data: PeriodChange }) {
  const points = data.spark || [];
  if (points.length < 2) {
    return (
      <div className="card p-6 text-text-muted text-sm">
        Not enough price history for a chart.
      </div>
    );
  }

  const W = 800, H = 240, PAD = 28;
  const closes = points.map((p) => p.close);
  const yMin = Math.min(...closes);
  const yMax = Math.max(...closes);
  const yRange = yMax - yMin || 1;
  const xStep = (W - PAD * 2) / Math.max(closes.length - 1, 1);

  const positive = data.change_pct >= 0;
  const stroke = positive ? "#4ade80" : "#f87171";
  const fillId = positive ? "ddPriceGreen" : "ddPriceRed";

  const coords = closes.map((c, i) => {
    const x = PAD + i * xStep;
    const y = H - PAD - ((c - yMin) / yRange) * (H - PAD * 2);
    return [x, y] as const;
  });
  const path = coords.map(([x, y], i) => (i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`)).join(" ");
  const last = coords[coords.length - 1];
  const area = `${path} L ${last[0]} ${H - PAD} L ${coords[0][0]} ${H - PAD} Z`;

  // Y-axis ticks
  const ticks = [yMin, (yMin + yMax) / 2, yMax];
  const tickY = (v: number) => H - PAD - ((v - yMin) / yRange) * (H - PAD * 2);

  // X-axis tick dates (first, mid, last)
  const xLabels = [
    points[0]?.date,
    points[Math.floor(points.length / 2)]?.date,
    points[points.length - 1]?.date,
  ];

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-base font-semibold">Price · {data.period}</h3>
        <div className={cn(
          "text-sm font-semibold tabular-nums",
          positive ? "text-accent-greenSoft" : "text-accent-redSoft"
        )}>
          {positive ? "↑" : "↓"} {data.change_pct >= 0 ? "+" : ""}{data.change_pct.toFixed(2)}%
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-60">
        <defs>
          <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.3" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Y gridlines + ticks */}
        {ticks.map((v, i) => (
          <g key={i}>
            <line
              x1={PAD} x2={W - PAD}
              y1={tickY(v)} y2={tickY(v)}
              stroke="#27272a" strokeWidth={1}
            />
            <text
              x={PAD - 4} y={tickY(v)}
              fill="#71717a" fontSize="10" textAnchor="end" alignmentBaseline="middle"
            >
              ${v.toFixed(0)}
            </text>
          </g>
        ))}

        {/* Area + line */}
        <path d={area} fill={`url(#${fillId})`} />
        <path d={path} fill="none" stroke={stroke} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={last[0]} cy={last[1]} r={3.5} fill={stroke} stroke="#09090b" strokeWidth={1.5} />

        {/* X-axis labels */}
        {xLabels.map((d, i) => {
          if (!d) return null;
          const xs = [PAD, W / 2, W - PAD];
          return (
            <text
              key={i} x={xs[i]} y={H - 6}
              fill="#71717a" fontSize="10"
              textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}
            >
              {d.slice(5)}
            </text>
          );
        })}
      </svg>
    </div>
  );
}
