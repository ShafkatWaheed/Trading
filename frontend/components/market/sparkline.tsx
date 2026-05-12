"use client";

import { cn } from "@/lib/utils";

type Props = {
  points: number[];
  width?: number;
  height?: number;
  /** 'auto' colors green if last >= first, red otherwise. Or pass a stroke. */
  tone?: "auto" | "neutral" | string;
  className?: string;
  showDot?: boolean;
};

export function Sparkline({
  points, width = 64, height = 22, tone = "auto", className, showDot = true,
}: Props) {
  if (!points || points.length < 2) {
    return <div className={cn("text-[10px] text-text-dim", className)}>—</div>;
  }
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const xStep = width / (points.length - 1);

  let stroke = "#a1a1aa";
  if (tone === "auto") {
    stroke = points[points.length - 1] >= points[0] ? "#4ade80" : "#f87171";
  } else if (tone !== "neutral") {
    stroke = tone;
  }

  const coords = points.map((p, i) => {
    const x = i * xStep;
    const y = height - ((p - min) / range) * (height - 2) - 1;
    return [x, y] as const;
  });
  const path = coords
    .map(([x, y], i) => (i === 0 ? `M ${x.toFixed(2)} ${y.toFixed(2)}` : `L ${x.toFixed(2)} ${y.toFixed(2)}`))
    .join(" ");
  const last = coords[coords.length - 1];

  return (
    <svg
      className={cn("inline-block", className)}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden
    >
      <path d={path} fill="none" stroke={stroke} strokeWidth={1.25} strokeLinejoin="round" strokeLinecap="round" />
      {showDot && (
        <circle cx={last[0]} cy={last[1]} r={1.6} fill={stroke} />
      )}
    </svg>
  );
}
