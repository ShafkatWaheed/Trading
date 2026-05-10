"use client";

import type { Candle, FullBacktestTrade } from "@/lib/api/types";
import { cn, formatPercent } from "@/lib/utils";

type Props = {
  candles: Candle[];
  trades: FullBacktestTrade[];
  symbol: string;
  signalLabel: string;
  period: string;
};

export function SignalChart({ candles, trades, symbol, signalLabel, period }: Props) {
  if (candles.length < 2) {
    return (
      <div className="card p-6 text-text-muted text-sm">
        Not enough price history.
      </div>
    );
  }

  const W = 1000, H = 360, PADL = 50, PADR = 10, PADT = 24, PADB = 28;
  const closes = candles.map((c) => c.close);
  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const yMin = Math.min(...lows);
  const yMax = Math.max(...highs);
  const yRange = yMax - yMin || 1;

  const xStep = (W - PADL - PADR) / Math.max(candles.length - 1, 1);
  const dateToIndex = new Map(candles.map((c, i) => [c.date, i]));

  const xOf = (idx: number) => PADL + idx * xStep;
  const yOf = (price: number) => H - PADB - ((price - yMin) / yRange) * (H - PADT - PADB);

  // Price line + area
  const linePath = candles.map((c, i) => {
    const x = xOf(i), y = yOf(c.close);
    return i === 0 ? `M ${x} ${y}` : `L ${x} ${y}`;
  }).join(" ");
  const areaPath = `${linePath} L ${xOf(candles.length - 1)} ${H - PADB} L ${xOf(0)} ${H - PADB} Z`;

  // Markers for trades
  const wins = trades.filter((t) => t.outcome === "win");
  const losses = trades.filter((t) => t.outcome === "loss");

  const ticks = [yMin, (yMin + yMax) / 2, yMax];
  const xLabels = [
    candles[0]?.date,
    candles[Math.floor(candles.length / 2)]?.date,
    candles[candles.length - 1]?.date,
  ];

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <h3 className="text-base font-semibold">
          {signalLabel} · {symbol}
          <span className="ml-2 text-xs text-text-muted font-normal">{period} hold</span>
        </h3>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-accent-greenSoft inline-flex items-center gap-1">
            <span className="text-base leading-none">▲</span> Win ({wins.length})
          </span>
          <span className="text-accent-redSoft inline-flex items-center gap-1">
            <span className="text-base leading-none">▼</span> Loss ({losses.length})
          </span>
        </div>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-72">
        <defs>
          <linearGradient id="signalChartFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
          </linearGradient>
        </defs>

        {ticks.map((v, i) => (
          <g key={i}>
            <line x1={PADL} x2={W - PADR} y1={yOf(v)} y2={yOf(v)} stroke="#27272a" strokeWidth={1} />
            <text x={PADL - 6} y={yOf(v)} fill="#71717a" fontSize="10" textAnchor="end" alignmentBaseline="middle">
              ${v.toFixed(0)}
            </text>
          </g>
        ))}

        <path d={areaPath} fill="url(#signalChartFill)" />
        <path d={linePath} fill="none" stroke="#3b82f6" strokeWidth={1.5} strokeLinejoin="round" />

        {/* Win triangles */}
        {wins.map((t, i) => {
          const idx = dateToIndex.get(t.entry_date);
          if (idx == null) return null;
          const x = xOf(idx);
          const y = yOf(t.entry_price);
          return (
            <g key={`w${i}`}>
              <title>{`WIN: ${formatPercent(t.pnl_percent)} in ${t.hold_days}d (${t.entry_date})`}</title>
              <polygon
                points={`${x},${y - 8} ${x - 6},${y + 4} ${x + 6},${y + 4}`}
                fill="#4ade80" stroke="#09090b" strokeWidth={1}
              />
            </g>
          );
        })}

        {/* Loss triangles */}
        {losses.map((t, i) => {
          const idx = dateToIndex.get(t.entry_date);
          if (idx == null) return null;
          const x = xOf(idx);
          const y = yOf(t.entry_price);
          return (
            <g key={`l${i}`}>
              <title>{`LOSS: ${formatPercent(t.pnl_percent)} in ${t.hold_days}d (${t.entry_date})`}</title>
              <polygon
                points={`${x},${y + 8} ${x - 6},${y - 4} ${x + 6},${y - 4}`}
                fill="#f87171" stroke="#09090b" strokeWidth={1}
              />
            </g>
          );
        })}

        {xLabels.map((d, i) => {
          if (!d) return null;
          const xs = [PADL, (W - PADR + PADL) / 2, W - PADR];
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
