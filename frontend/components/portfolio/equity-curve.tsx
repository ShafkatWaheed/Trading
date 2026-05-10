"use client";

import type { EquityPoint } from "@/lib/api/types";

export function EquityCurve({ points }: { points: EquityPoint[] }) {
  if (!points || points.length < 2) {
    return (
      <div className="card p-6">
        <h3 className="text-base font-semibold mb-2">Equity Curve</h3>
        <p className="text-text-muted text-sm">Need at least 2 data points to draw a curve.</p>
      </div>
    );
  }

  const W = 800, H = 220, PAD = 16;
  const xs = points.map((_, i) => i);
  const ys = points.map((p) => p.equity);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const yRange = yMax - yMin || 1;

  const xStep = (W - PAD * 2) / Math.max(xs.length - 1, 1);
  const points2d = points.map((p, i) => {
    const x = PAD + i * xStep;
    const y = H - PAD - ((p.equity - yMin) / yRange) * (H - PAD * 2);
    return [x, y] as const;
  });

  const path = points2d.map(([x, y], i) => (i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`)).join(" ");
  const area = `${path} L ${points2d[points2d.length - 1][0]} ${H - PAD} L ${points2d[0][0]} ${H - PAD} Z`;

  const positive = ys[ys.length - 1] >= ys[0];
  const stroke = positive ? "#4ade80" : "#f87171";
  const fill = positive ? "url(#greenGrad)" : "url(#redGrad)";

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-base font-semibold">Equity Curve</h3>
        <span className="text-xs text-text-muted">{points.length} days</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-56">
        <defs>
          <linearGradient id="greenGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4ade80" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#4ade80" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="redGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f87171" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#f87171" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill={fill} />
        <path d={path} fill="none" stroke={stroke} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      </svg>
    </div>
  );
}
