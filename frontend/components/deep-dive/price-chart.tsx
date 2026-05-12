"use client";

import { useQuery } from "@tanstack/react-query";
import type { PeriodChange, TradePlan } from "@/lib/api/types";
import { stocksApi } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";

type Props = { data: PeriodChange; symbol?: string; tradePlan?: TradePlan | null };

export function PriceChart({ data, symbol, tradePlan }: Props) {
  const points = data.spark || [];

  // Lazy-fetch benchmarks (SPY + sector ETF) — overlays as thin reference lines.
  const benchQ = useQuery({
    queryKey: ["benchmarks", symbol, data.period],
    queryFn: () => stocksApi.benchmarks(symbol!, data.period),
    enabled: Boolean(symbol),
    staleTime: 60 * 60 * 1000,
  });
  const bench = benchQ.data;

  if (points.length < 2) {
    return (
      <div className="card p-6 text-text-muted text-sm">
        Not enough price history for a chart.
      </div>
    );
  }

  const W = 800, H = 240, PAD = 28;
  const closes = points.map((p) => p.close);

  // Normalize stock to a 0..100 index from its first close — we plot the *index*
  // for everything so SPY/sector are on the same Y scale even if dollar prices
  // differ wildly.
  const stockFirst = closes[0];
  const stockIdx = closes.map((c) => (c / stockFirst) * 100);

  // Align benchmark points to stock dates (left-join); leave gaps where missing.
  const dateToStock = new Map(points.map((p, i) => [p.date, i]));
  const spyByIdx: (number | null)[] = new Array(points.length).fill(null);
  const sectorByIdx: (number | null)[] = new Array(points.length).fill(null);
  for (const sp of bench?.spy_spark ?? []) {
    const i = dateToStock.get(sp.date);
    if (i !== undefined) spyByIdx[i] = sp.idx;
  }
  for (const sp of bench?.sector_spark ?? []) {
    const i = dateToStock.get(sp.date);
    if (i !== undefined) sectorByIdx[i] = sp.idx;
  }
  // If benchmark series have no date overlap (different trading days for indexes
  // vs stocks shouldn't happen but be safe), fall back to evenly-spaced sampling.
  const spyIndexed = spyByIdx.some((v) => v != null)
    ? spyByIdx
    : (bench?.spy_spark ?? []).map((p) => p.idx);
  const sectorIndexed = sectorByIdx.some((v) => v != null)
    ? sectorByIdx
    : (bench?.sector_spark ?? []).map((p) => p.idx);

  // Convert trade-plan dollar prices to the indexed scale (everything else
  // is already idx). We'll also pull these into yMin/yMax so the lines are
  // never off-screen.
  const planIdx = tradePlan
    ? {
        entry:   (tradePlan.entry      / stockFirst) * 100,
        stop:    (tradePlan.stop_loss  / stockFirst) * 100,
        target1: (tradePlan.target1    / stockFirst) * 100,
        target2: (tradePlan.target2    / stockFirst) * 100,
      }
    : null;

  // Y range across all visible series so they share the axis nicely.
  const allVals = [
    ...stockIdx,
    ...(spyIndexed.filter((v): v is number => v != null)),
    ...(sectorIndexed.filter((v): v is number => v != null)),
    ...(planIdx ? [planIdx.entry, planIdx.stop, planIdx.target1, planIdx.target2] : []),
  ];
  const yMin = Math.min(...allVals);
  const yMax = Math.max(...allVals);
  const yRange = yMax - yMin || 1;
  const xStep = (W - PAD * 2) / Math.max(stockIdx.length - 1, 1);

  const positive = data.change_pct >= 0;
  const stroke = positive ? "#4ade80" : "#f87171";
  const fillId = positive ? "ddPriceGreen" : "ddPriceRed";

  const toCoords = (vals: (number | null)[]) =>
    vals.map((v, i) => {
      if (v == null) return null;
      const x = PAD + i * xStep;
      const y = H - PAD - ((v - yMin) / yRange) * (H - PAD * 2);
      return [x, y] as const;
    });

  const stockCoords = toCoords(stockIdx);
  const spyCoords   = toCoords(spyIndexed);
  const secCoords   = toCoords(sectorIndexed);

  const pathFromCoords = (coords: ReturnType<typeof toCoords>): string => {
    let started = false;
    let path = "";
    for (const c of coords) {
      if (c == null) { started = false; continue; }
      const [x, y] = c;
      path += started ? ` L ${x} ${y}` : `M ${x} ${y}`;
      started = true;
    }
    return path;
  };

  const stockPath = pathFromCoords(stockCoords);
  const spyPath   = pathFromCoords(spyCoords);
  const secPath   = pathFromCoords(secCoords);

  // Area under stock line for the filled gradient
  const lastStock = stockCoords[stockCoords.length - 1]!;
  const firstStock = stockCoords[0]!;
  const area = `${stockPath} L ${lastStock[0]} ${H - PAD} L ${firstStock[0]} ${H - PAD} Z`;

  // Y-axis ticks (in the index space so SPY at 100 is meaningful)
  const ticks = [yMin, (yMin + yMax) / 2, yMax];
  const tickY = (v: number) => H - PAD - ((v - yMin) / yRange) * (H - PAD * 2);

  // X-axis tick dates
  const xLabels = [
    points[0]?.date,
    points[Math.floor(points.length / 2)]?.date,
    points[points.length - 1]?.date,
  ];

  // Compute end-of-period index for each series for legend % display
  const stockEnd = stockIdx[stockIdx.length - 1] - 100;
  const spyVals = spyIndexed.filter((v): v is number => v != null);
  const secVals = sectorIndexed.filter((v): v is number => v != null);
  const spyEnd = spyVals.length > 0 ? spyVals[spyVals.length - 1] - 100 : null;
  const secEnd = secVals.length > 0 ? secVals[secVals.length - 1] - 100 : null;

  const fmtPct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  const relColor = (a: number, b: number | null) =>
    b == null ? "text-text-muted" : a > b ? "text-accent-greenSoft" : a < b ? "text-accent-redSoft" : "text-text-secondary";

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="text-base font-semibold">Price · {data.period}</h3>
        <div className={cn(
          "text-sm font-semibold tabular-nums",
          positive ? "text-accent-greenSoft" : "text-accent-redSoft"
        )}>
          {positive ? "↑" : "↓"} {fmtPct(data.change_pct)}
        </div>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-60">
        <defs>
          <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.3" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Y gridlines */}
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
              {v.toFixed(0)}
            </text>
          </g>
        ))}

        {/* Benchmarks (drawn first, behind) */}
        {spyPath && (
          <path d={spyPath} fill="none" stroke="#a1a1aa" strokeWidth={1} strokeDasharray="3 3" strokeLinejoin="round" />
        )}
        {secPath && (
          <path d={secPath} fill="none" stroke="#60a5fa" strokeWidth={1} strokeDasharray="2 4" strokeLinejoin="round" opacity="0.8" />
        )}

        {/* Stock area + line */}
        <path d={area} fill={`url(#${fillId})`} />
        <path d={stockPath} fill="none" stroke={stroke} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={lastStock[0]} cy={lastStock[1]} r={3.5} fill={stroke} stroke="#09090b" strokeWidth={1.5} />

        {/* Trade plan levels — drawn as horizontal dashed lines with $ labels on the right */}
        {planIdx && tradePlan && (() => {
          const levels = [
            { y: planIdx.target2, label: `T2 $${tradePlan.target2.toFixed(2)} (+${tradePlan.target2_pct.toFixed(1)}%)`, color: "#22c55e", weight: 1.5 },
            { y: planIdx.target1, label: `T1 $${tradePlan.target1.toFixed(2)} (+${tradePlan.target1_pct.toFixed(1)}%)`, color: "#4ade80", weight: 1.5 },
            { y: planIdx.entry,   label: `Entry $${tradePlan.entry.toFixed(2)}`,                                       color: "#60a5fa", weight: 1.5 },
            { y: planIdx.stop,    label: `Stop $${tradePlan.stop_loss.toFixed(2)} (−${tradePlan.stop_pct.toFixed(1)}%)`, color: "#f87171", weight: 1.5 },
          ];
          return (
            <g>
              {levels.map((lvl, i) => {
                const y = tickY(lvl.y);
                if (y < PAD - 6 || y > H - PAD + 6) return null;
                return (
                  <g key={i}>
                    <line
                      x1={PAD} x2={W - PAD - 110}
                      y1={y} y2={y}
                      stroke={lvl.color} strokeWidth={lvl.weight} strokeDasharray="4 4" opacity="0.85"
                    />
                    <rect
                      x={W - PAD - 108} y={y - 8}
                      width={108} height={16} rx={3}
                      fill={lvl.color} opacity="0.18"
                      stroke={lvl.color} strokeWidth={0.8} strokeOpacity="0.5"
                    />
                    <text
                      x={W - PAD - 4} y={y}
                      fill={lvl.color} fontSize="9.5" fontWeight={600}
                      textAnchor="end" alignmentBaseline="middle"
                    >
                      {lvl.label}
                    </text>
                  </g>
                );
              })}
            </g>
          );
        })()}

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

      {/* Legend with relative-performance numbers */}
      <div className="flex items-center gap-4 mt-2 flex-wrap text-[11px]">
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 rounded" style={{ background: stroke }} />
          <span className="text-text-secondary font-medium">{symbol || "Stock"}</span>
          <span className={cn("tabular-nums font-semibold", positive ? "text-accent-greenSoft" : "text-accent-redSoft")}>
            {fmtPct(stockEnd)}
          </span>
        </div>
        {spyEnd != null && (
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-px rounded bg-text-muted" style={{ borderTop: "1px dashed #a1a1aa" }} />
            <span className="text-text-muted">SPY</span>
            <span className={cn("tabular-nums", relColor(stockEnd, spyEnd))}>
              {fmtPct(spyEnd)}
            </span>
          </div>
        )}
        {bench?.sector_etf && secEnd != null && (
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-px rounded" style={{ borderTop: "1px dashed #60a5fa" }} />
            <span className="text-text-muted">{bench.sector_etf}</span>
            <span className="text-text-muted">({bench.sector})</span>
            <span className={cn("tabular-nums", relColor(stockEnd, secEnd))}>
              {fmtPct(secEnd)}
            </span>
          </div>
        )}
        <span className="ml-auto text-[10px] text-text-dim">All series indexed to 100 at period start</span>
      </div>

      {/* Relative-performance pace explainer */}
      {(spyEnd != null || (bench?.sector_etf && secEnd != null)) && (
        <RelativePace
          symbol={symbol || "Stock"}
          stockEnd={stockEnd}
          spyEnd={spyEnd}
          secEnd={secEnd}
          sectorEtf={bench?.sector_etf}
          sectorName={bench?.sector}
          period={data.period}
        />
      )}
    </div>
  );
}

function RelativePace({
  symbol, stockEnd, spyEnd, secEnd, sectorEtf, sectorName, period,
}: {
  symbol: string;
  stockEnd: number;
  spyEnd: number | null;
  secEnd: number | null;
  sectorEtf?: string | null;
  sectorName?: string | null;
  period: string;
}) {
  const vsSpy = spyEnd != null ? stockEnd - spyEnd : null;
  const vsSec = secEnd != null ? stockEnd - secEnd : null;

  const headline =
    vsSpy != null && vsSec != null
      ? vsSpy > 0 && vsSec > 0
        ? "Beating both the market and its sector"
        : vsSpy > 0 && vsSec <= 0
          ? "Beating the market but lagging its sector"
          : vsSpy <= 0 && vsSec > 0
            ? "Lagging the market but leading its sector"
            : "Lagging both the market and its sector"
      : vsSpy != null
        ? vsSpy > 0 ? "Beating the market" : "Lagging the market"
        : "—";

  const headlineTone =
    vsSpy != null && vsSec != null
      ? vsSpy > 0 && vsSec > 0
        ? "text-accent-greenSoft"
        : vsSpy > 0 || vsSec > 0
          ? "text-accent-amber"
          : "text-accent-redSoft"
      : (vsSpy ?? 0) > 0 ? "text-accent-greenSoft" : "text-accent-redSoft";

  const fmt = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)} pp`;
  const colorFor = (v: number | null) =>
    v == null ? "text-text-muted" : v > 0 ? "text-accent-greenSoft" : v < 0 ? "text-accent-redSoft" : "text-text-secondary";

  return (
    <div className="mt-3 pt-3 border-t border-bg-border bg-bg-base/50 rounded-md p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] uppercase tracking-wider text-text-muted">Relative pace · {period}</span>
        <span className={cn("text-xs font-semibold", headlineTone)}>{headline}</span>
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-[11px]">
        {vsSpy != null && (
          <div>
            <span className="text-text-muted">{symbol} vs SPY: </span>
            <span className={cn("font-semibold tabular-nums", colorFor(vsSpy))}>{fmt(vsSpy)}</span>
            <span className="text-text-dim ml-1">
              ({vsSpy > 0 ? "outperformed" : vsSpy < 0 ? "underperformed" : "matched"} the market)
            </span>
          </div>
        )}
        {vsSec != null && sectorEtf && (
          <div>
            <span className="text-text-muted">{symbol} vs {sectorEtf}: </span>
            <span className={cn("font-semibold tabular-nums", colorFor(vsSec))}>{fmt(vsSec)}</span>
            <span className="text-text-dim ml-1">
              ({vsSec > 0 ? "outperformed" : vsSec < 0 ? "underperformed" : "matched"} {sectorName?.toLowerCase() || "sector"} peers)
            </span>
          </div>
        )}
      </div>
      <p className="text-[10px] text-text-muted mt-2 leading-snug">
        <span className="font-semibold">pp</span> = percentage points (a stock up 12% while SPY is up 8% beats the market by 4 pp).
        Outperforming both lines = best-in-sector; lagging both = capital is going elsewhere.
      </p>
    </div>
  );
}
