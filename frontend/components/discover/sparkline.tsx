"use client";

import type { SparkPoint } from "@/lib/api/types";

export function Sparkline({ points, height = 60 }: { points?: SparkPoint[] | null; height?: number }) {
  if (!points || points.length < 2) return null;

  const W = 600, H = height, PAD = 4;
  const closes = points.map((p) => p.close);
  const yMin = Math.min(...closes);
  const yMax = Math.max(...closes);
  const yRange = yMax - yMin || 1;
  const xStep = (W - PAD * 2) / Math.max(closes.length - 1, 1);

  const positive = closes[closes.length - 1] >= closes[0];
  const stroke = positive ? "#4ade80" : "#f87171";
  const fillId = positive ? "sparkGreen" : "sparkRed";

  const coords = closes.map((c, i) => {
    const x = PAD + i * xStep;
    const y = H - PAD - ((c - yMin) / yRange) * (H - PAD * 2);
    return [x, y] as const;
  });

  const path = coords.map(([x, y], i) => (i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`)).join(" ");
  const lastCoord = coords[coords.length - 1];
  const area = `${path} L ${lastCoord[0]} ${H - PAD} L ${coords[0][0]} ${H - PAD} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="none" style={{ height }}>
      <defs>
        <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.25" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${fillId})`} />
      <path d={path} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lastCoord[0]} cy={lastCoord[1]} r={2.5} fill={stroke} />
    </svg>
  );
}
