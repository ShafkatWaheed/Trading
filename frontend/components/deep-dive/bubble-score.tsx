"use client";

import { useQuery } from "@tanstack/react-query";
import { Gauge, Loader2, RefreshCw } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

function tone(score: number) {
  if (score < 25)  return { color: "text-accent-greenSoft", bar: "bg-accent-green",  border: "border-accent-green/40"  };
  if (score < 50)  return { color: "text-accent-blue",      bar: "bg-accent-blue",   border: "border-accent-blue/40"   };
  if (score < 70)  return { color: "text-accent-amber",     bar: "bg-accent-amber",  border: "border-accent-amber/40"  };
  if (score < 85)  return { color: "text-accent-amberSoft", bar: "bg-accent-amber",  border: "border-accent-amber/60"  };
  return                   { color: "text-accent-redSoft",  bar: "bg-accent-red",    border: "border-accent-red/40"    };
}

function levelFor(pct: number): { label: string; color: string; bar: string } {
  if (pct < 20)  return { label: "Calm",     color: "text-accent-greenSoft", bar: "bg-accent-greenSoft" };
  if (pct < 50)  return { label: "Mild",     color: "text-accent-blue",      bar: "bg-accent-blue" };
  if (pct < 80)  return { label: "Moderate", color: "text-accent-amber",     bar: "bg-accent-amber" };
  if (pct < 100) return { label: "High",     color: "text-accent-amberSoft", bar: "bg-accent-amber" };
  return                { label: "Maxed",    color: "text-accent-redSoft",   bar: "bg-accent-red" };
}

function ComponentRow({ label, value, max, evidence }: {
  label: string; value: number; max: number; evidence: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const lvl = levelFor(pct);
  return (
    <div className="bg-bg-base rounded-md p-3 border border-bg-border">
      <div className="flex items-center justify-between mb-2 gap-2">
        <span className="text-[11px] font-semibold text-text-primary">{label}</span>
        <span className={cn("text-[10px] font-bold uppercase tracking-wider", lvl.color)}>
          {lvl.label}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-bg-card overflow-hidden mb-2">
        <div className={cn("h-full transition-all", lvl.bar)} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-[11px] text-text-secondary leading-snug">{evidence}</p>
    </div>
  );
}

function gapEvidence(price1y: number | null | undefined,
                     fundamental: number | null | undefined,
                     gap: number | null | undefined): string {
  if (gap == null) return "Not enough data to measure the gap.";
  if (price1y == null) return `Gap of ${gap.toFixed(0)}% between price and business growth.`;
  const fStr = fundamental != null ? `${fundamental.toFixed(0)}%` : "n/a";
  if (gap > 0) return `Stock +${price1y.toFixed(0)}% over 1Y, business +${fStr} → ${gap.toFixed(0)}% gap (price ahead).`;
  return `Stock ${price1y >= 0 ? "+" : ""}${price1y.toFixed(0)}% over 1Y, business +${fStr} → ${gap.toFixed(0)}% gap (business ahead — healthy).`;
}

function valEvidence(pe: number | null | undefined, ps: number | null | undefined,
                     pfcf: number | null | undefined): string {
  const flagged: string[] = [];
  if (pe != null && pe > 30)   flagged.push(`P/E ${pe.toFixed(0)}`);
  if (ps != null && ps > 5)    flagged.push(`P/S ${ps.toFixed(0)}`);
  if (pfcf != null && pfcf > 30) flagged.push(`P/FCF ${pfcf.toFixed(0)}`);
  if (flagged.length === 0) return "All multiples in normal range.";
  return `${flagged.join(" + ")} — above broad-market norms.`;
}

function momEvidence(price3m: number | null | undefined): string {
  if (price3m == null) return "No 3M data.";
  if (price3m >= 60)   return `+${price3m.toFixed(0)}% in 3 months — parabolic.`;
  if (price3m >= 30)   return `+${price3m.toFixed(0)}% in 3 months — hot run.`;
  if (price3m > 0)     return `+${price3m.toFixed(0)}% in 3 months — normal.`;
  return `${price3m.toFixed(0)}% in 3 months — no upward heat.`;
}

function Metric({ label, hint, value, unit, highlight }: {
  label: string; hint?: string;
  value: number | null | undefined; unit?: string; highlight?: boolean;
}) {
  return (
    <div className="bg-bg-base rounded-md p-2.5 border border-bg-border" title={hint}>
      <div className="text-[10px] uppercase tracking-wider text-text-muted">{label}</div>
      <div className={cn("text-base font-bold tabular-nums mt-0.5", highlight ? "text-accent-amber" : "text-text-primary")}>
        {value == null ? "—" : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${unit || ""}`}
      </div>
      {hint && (
        <div className="text-[10px] text-text-muted leading-snug mt-1">{hint}</div>
      )}
    </div>
  );
}

const GLOSSARY: { term: string; short: string; long: string }[] = [
  { term: "P/E",   short: "Years of profit you're paying for",
                   long:  "If P/E is 35, you pay $35 for every $1 of yearly profit. Typical: 20–25. Bubble territory: 50+." },
  { term: "P/S",   short: "$ per $1 of yearly sales",
                   long:  "If P/S is 10, you pay $10 for every $1 of yearly revenue. Typical: 1–5. Hot tech: 10–20. Bubble: 30+." },
  { term: "P/FCF", short: "Years of actual cash generated you're paying for",
                   long:  "Like P/E but using cash (harder to fake than accounting profit). Healthy: 15–30. Stretched: 50+." },
  { term: "Growth Gap", short: "Price growth − business growth",
                   long:  "Stock up 40%, sales up 15% → gap +25% (overvaluation signal). Negative number means the business grew FASTER than the price — fundamentals catching up, not running ahead. Big negatives (-100%+) usually come from a small profit base growing fast (a $5M → $20M jump is 300% but fragile)." },
];

export function BubbleScoreCard({ symbol }: Props) {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["bubble-score", symbol],
    queryFn: () => stocksApi.bubbleScore(symbol),
    staleTime: 6 * 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) {
    return (
      <section className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Gauge size={16} className="text-accent-amber" />
          <h3 className="text-base font-semibold">Bubble Score</h3>
        </div>
        <Skeleton className="h-40 w-full" />
      </section>
    );
  }

  if (isError) {
    return (
      <section className="card p-6 border-l-4 border-accent-red/40">
        <p className="text-accent-redSoft text-sm">
          {(error as Error)?.message || "Failed to load bubble score."}
        </p>
      </section>
    );
  }

  if (!data) return null;

  const t = tone(data.score);
  const m = data.metrics;
  const gap = m.growth_gap_pct ?? null;

  return (
    <section className={cn("card p-6 border-l-4", t.border)}>
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <Gauge size={16} className={t.color} />
          <h3 className="text-base font-semibold">Bubble Score</h3>
          {data.from_cache && (
            <span className="text-[10px] uppercase tracking-wider text-text-muted">cached</span>
          )}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          title="Recompute"
          className="text-xs text-text-muted hover:text-text-primary flex items-center gap-1.5 disabled:opacity-40"
        >
          {isFetching ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[180px_1fr] gap-6 mb-5">
        <div className="flex flex-col items-center justify-center">
          <div className={cn("text-6xl font-bold tabular-nums", t.color)}>
            {data.score.toFixed(0)}
          </div>
          <div className="text-text-muted text-[10px] uppercase tracking-wider mt-1">/ 100</div>
          <div className={cn("text-sm font-semibold mt-2", t.color)}>
            {data.label}
          </div>
        </div>

        <div className="flex flex-col justify-center gap-2.5">
          <ComponentRow
            label="Growth Gap"
            value={data.components.growth_gap}
            max={35}
            evidence={gapEvidence(m.price_change_1y_pct, m.fundamental_growth_pct, m.growth_gap_pct)}
          />
          <ComponentRow
            label="Valuation Multiples"
            value={data.components.valuation}
            max={45}
            evidence={valEvidence(m.pe_ratio, m.ps_ratio, m.pfcf_ratio)}
          />
          <ComponentRow
            label="Momentum (3M)"
            value={data.components.momentum}
            max={20}
            evidence={momEvidence(m.price_change_3m_pct)}
          />
        </div>
      </div>

      <div className="mb-5 bg-bg-base border border-bg-border rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Vibes Premium</div>
          <div className="text-[10px] text-text-dim">% of 1Y price gain not backed by business</div>
        </div>

        {(m.price_change_1y_pct ?? 0) <= 0 ? (
          <div className="text-text-secondary text-sm leading-snug">
            Stock is <span className="font-semibold text-accent-redSoft">down {Math.abs(m.price_change_1y_pct ?? 0).toFixed(0)}%</span> over the last year — no price gain to decompose into vibes vs fundamentals.
          </div>
        ) : m.vibes_share_pct == null ? (
          <div className="text-text-muted text-sm leading-snug">Not enough fundamentals data to compute the vibes share.</div>
        ) : (
          <>
            <div className="flex items-end gap-3 flex-wrap">
              <div className={cn(
                "text-4xl font-bold tabular-nums leading-none",
                m.vibes_share_pct >= 60 ? "text-accent-redSoft"
                  : m.vibes_share_pct >= 30 ? "text-accent-amber"
                  : "text-accent-greenSoft"
              )}>
                {m.vibes_share_pct.toFixed(0)}%
              </div>
              <div className="text-text-secondary text-sm leading-snug pb-1">
                For every <span className="font-semibold text-text-primary">$100</span> of price gain in the last year,
                {" "}<span className="font-semibold text-accent-amber">${m.vibes_share_pct.toFixed(0)}</span>{" "}
                came from sentiment / story, only
                {" "}<span className="font-semibold text-accent-greenSoft">${(100 - m.vibes_share_pct).toFixed(0)}</span>{" "}
                from actual business growth.
              </div>
            </div>
            {m.fundamental_growth_pct != null && (
              <div className="text-[11px] text-text-muted mt-2">
                Stock up {(m.price_change_1y_pct ?? 0).toFixed(0)}% over 1Y · Business grew {m.fundamental_growth_pct.toFixed(0)}%
              </div>
            )}
          </>
        )}
      </div>

      <div className="mb-5">
        <div className={cn("text-sm font-semibold mb-2", t.color)}>
          {data.verdict}
        </div>
        {data.reasons && data.reasons.length > 0 ? (
          <ul className="space-y-2">
            {data.reasons.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-text-secondary leading-relaxed">
                <span className={cn("mt-1.5 w-1 h-1 rounded-full shrink-0", t.bar)} />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-text-secondary leading-relaxed">
            The price isn't running ahead of the business and multiples are sensible.
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
        <Metric label="1Y Price"
                hint="Stock's % change over the last year"
                value={m.price_change_1y_pct} unit="%"
                highlight={(m.price_change_1y_pct ?? 0) > 50} />
        <Metric label="3M Price"
                hint="Stock's % change over the last 3 months"
                value={m.price_change_3m_pct} unit="%"
                highlight={(m.price_change_3m_pct ?? 0) > 30} />
        <Metric label="Revenue Growth"
                hint="How much sales grew vs same quarter last year"
                value={m.revenue_growth_pct} unit="%" />
        <Metric label="Earnings Growth"
                hint="How much profit grew vs same quarter last year"
                value={m.earnings_growth_pct} unit="%" />
        <Metric label="Growth Gap"
                hint={
                  gap == null
                    ? "Price growth − business growth"
                    : gap > 20
                      ? "Price ran far ahead of the business — overvaluation signal."
                      : gap > 0
                        ? "Price slightly ahead of business growth."
                        : "Negative = business grew faster than price (catch-up, not overvaluation)."
                }
                value={gap} unit="%"
                highlight={(gap ?? 0) > 20} />
        <Metric label="P/E"
                hint="Years of profit you're paying for. Typical: 20–25. Bubble: 50+."
                value={m.pe_ratio}
                highlight={(m.pe_ratio ?? 0) > 40} />
        <Metric label="P/S"
                hint="$ per $1 of yearly sales. Typical: 1–5. Bubble: 30+."
                value={m.ps_ratio}
                highlight={(m.ps_ratio ?? 0) > 10} />
        <Metric label="P/FCF"
                hint="Years of real cash generated you're paying for. Healthy: 15–30."
                value={m.pfcf_ratio}
                highlight={(m.pfcf_ratio ?? 0) > 40} />
      </div>

      <details className="mt-4 pt-3 border-t border-bg-border">
        <summary className="text-xs text-text-muted hover:text-text-secondary cursor-pointer select-none">
          What do these numbers mean? (click to learn)
        </summary>
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          {GLOSSARY.map((g) => (
            <div key={g.term} className="bg-bg-base rounded-md p-3 border border-bg-border">
              <div className="text-accent-blue font-semibold mb-1">
                {g.term} <span className="text-text-muted font-normal">— {g.short}</span>
              </div>
              <p className="text-text-secondary leading-relaxed">{g.long}</p>
            </div>
          ))}
        </div>
      </details>

      <p className="text-[10px] text-text-muted mt-3">
        Higher score = price has run further ahead of fundamentals.
        Not a forecast. Cross-check with the Downside Brief and your own due diligence.
      </p>
    </section>
  );
}
