"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Layers, ArrowUp, ArrowDown, Minus, RefreshCw, Loader2 } from "lucide-react";
import { marketApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function ppColor(v: number | null | undefined): string {
  if (v == null) return "text-text-muted";
  if (v > 0)     return "text-accent-greenSoft";
  if (v < 0)     return "text-accent-redSoft";
  return "text-text-secondary";
}

function vixToneClass(regime: string | null | undefined): string {
  if (regime === "calm")     return "text-accent-greenSoft";
  if (regime === "normal")   return "text-text-secondary";
  if (regime === "stressed") return "text-accent-amber";
  if (regime === "panic")    return "text-accent-redSoft";
  return "text-text-muted";
}

function pp(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)} pp`;
}

function pct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

export function BreadthCard() {
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["market-dashboard"],
    queryFn: () => marketApi.dashboard(),
    staleTime: 2 * 60 * 1000,
  });

  // Detect cached-empty: the cache only stores responses with real data now,
  // but a stale entry from before that fix can still be present in the React
  // Query in-memory cache. Auto-trigger one refetch in that case.
  const breadthEmpty = (() => {
    if (!data) return false;
    const b = data.breadth || {};
    return (
      b.vix_level == null &&
      b.spy_pct_above_50d == null &&
      b.spy_vs_rsp_1m_pp == null
    );
  })();

  useEffect(() => {
    if (breadthEmpty && !isFetching) {
      refetch();
    }
  }, [breadthEmpty, isFetching, refetch]);

  if (isLoading) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <Layers size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">Market Breadth</h3>
        </div>
        <Skeleton className="h-32 w-full" />
      </section>
    );
  }
  if (!data) return null;
  const b = data.breadth;

  return (
    <section className="card-subtle p-6">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Layers size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">Market Breadth</h3>
          {data.from_cache && (
            <span className="text-[10px] uppercase tracking-wider text-text-muted">cached</span>
          )}
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            title="Refresh breadth data"
            className="text-text-muted hover:text-text-primary flex items-center disabled:opacity-40 ml-1"
          >
            {isFetching
              ? <Loader2 size={11} className="animate-spin" />
              : <RefreshCw size={11} />}
          </button>
        </div>
        <span className="text-[11px] text-text-secondary italic">{b.headline}</span>
      </div>

      {breadthEmpty && (
        <div className="mb-3 p-2.5 rounded-md bg-accent-amber/5 border border-accent-amber/30 text-[11px] text-accent-amber">
          Breadth data unavailable from upstream. Auto-retrying…
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
        <Metric
          label="SPY vs RSP (1M)"
          value={pp(b.spy_vs_rsp_1m_pp)}
          valueColor={ppColor(b.spy_vs_rsp_1m_pp)}
          hint={
            (b.spy_vs_rsp_1m_pp ?? 0) > 1.5
              ? "narrow rally — mega-caps leading"
              : (b.spy_vs_rsp_1m_pp ?? 0) < -1.5
                ? "broad rally — equal-weight leading"
                : "balanced participation"
          }
          Icon={(b.spy_vs_rsp_1m_pp ?? 0) > 0 ? ArrowUp : ArrowDown}
        />
        <Metric
          label="IWM vs SPY (1M)"
          value={pp(b.iwm_vs_spy_1m_pp)}
          valueColor={ppColor(b.iwm_vs_spy_1m_pp)}
          hint={
            (b.iwm_vs_spy_1m_pp ?? 0) >= 0
              ? "small caps in sync / leading"
              : "small caps lagging — narrow market"
          }
          Icon={(b.iwm_vs_spy_1m_pp ?? 0) >= 0 ? ArrowUp : ArrowDown}
        />
        <Metric
          label="VIX"
          value={b.vix_level != null ? b.vix_level.toFixed(1) : "—"}
          valueColor={vixToneClass(b.vix_regime)}
          hint={b.vix_regime ? `${b.vix_regime} volatility regime` : undefined}
          Icon={
            b.vix_regime === "calm" ? ArrowDown :
            b.vix_regime === "panic" || b.vix_regime === "stressed" ? ArrowUp : Minus
          }
        />
        <Metric
          label="SPY vs 50-DMA"
          value={pct(b.spy_pct_above_50d)}
          valueColor={ppColor(b.spy_pct_above_50d)}
          hint={
            (b.spy_pct_above_50d ?? 0) >= 0
              ? "trend intact (above 50-day)"
              : "below 50-day — short-term weakness"
          }
          Icon={(b.spy_pct_above_50d ?? 0) >= 0 ? ArrowUp : ArrowDown}
        />
      </div>

      <details className="mt-4 pt-3 border-t border-bg-border">
        <summary className="text-xs text-text-muted hover:text-text-secondary cursor-pointer select-none">
          What do these mean? (click to learn)
        </summary>
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <Explainer
            term="SPY vs RSP"
            tagline="Is the rally broad or narrow?"
            body={
              <>
                <p>
                  <span className="font-semibold text-text-secondary">SPY</span> tracks the
                  S&P 500 by <em>market cap</em> — Apple, Microsoft, Nvidia are huge weights;
                  the top 10 stocks make up ~35% of the index.
                  <span className="font-semibold text-text-secondary"> RSP</span> tracks the
                  same 500 companies with <em>equal weight</em> — each company gets ~0.2%.
                </p>
                <p className="mt-2">
                  <span className="text-accent-amber font-semibold">When SPY beats RSP</span>{" "}
                  by a wide margin, only the biggest stocks are doing well — the average stock
                  is being left behind. That's a <em>narrow rally</em>: historically a yellow
                  flag (late-1999, mid-2007, 2023–24 "Mag 7").
                </p>
                <p className="mt-2">
                  <span className="text-accent-greenSoft font-semibold">When RSP beats SPY</span>,
                  every stock is participating — a <em>broad, healthy rally</em>.
                </p>
              </>
            }
          />
          <Explainer
            term="IWM vs SPY"
            tagline="Are small caps in sync with the big board?"
            body={
              <>
                <p>
                  <span className="font-semibold text-text-secondary">IWM</span> is the
                  Russell 2000 — 2,000 small-cap U.S. companies. <span className="font-semibold text-text-secondary">SPY</span> is the S&P 500 mega-caps.
                </p>
                <p className="mt-2">
                  When IWM lags SPY significantly, it means investors are crowding into
                  large-cap safety while ignoring smaller companies — usually a
                  <em> risk-off</em> tell even if the headline indices are up.
                </p>
                <p className="mt-2">
                  When IWM is in sync (or ahead), risk appetite is healthy across cap sizes.
                </p>
              </>
            }
          />
          <Explainer
            term="VIX"
            tagline="The market's 'fear gauge'"
            body={
              <>
                <p>
                  VIX measures <em>implied volatility</em> on S&P 500 options — basically how
                  much insurance investors are buying. Low VIX = complacency. High VIX = panic.
                </p>
                <p className="mt-2">
                  <span className="text-accent-greenSoft font-semibold">&lt;15 calm</span>{" "}·{" "}
                  <span className="text-text-secondary font-semibold">15-25 normal</span>{" "}·{" "}
                  <span className="text-accent-amber font-semibold">25-35 stressed</span>{" "}·{" "}
                  <span className="text-accent-redSoft font-semibold">35+ panic</span>
                </p>
                <p className="mt-2">
                  Counterintuitively, very calm VIX (&lt;13) can precede sell-offs because it
                  signals complacency. Spiking VIX during a sell-off often marks a near-term
                  bottom.
                </p>
              </>
            }
          />
          <Explainer
            term="SPY vs 50-DMA"
            tagline="Is the medium-term trend intact?"
            body={
              <>
                <p>
                  The <em>50-day moving average</em> is the average closing price over the
                  last 50 trading days (~10 weeks). Big institutional algos and discretionary
                  managers use it as a "is this stock/index in an uptrend?" line.
                </p>
                <p className="mt-2">
                  <span className="text-accent-greenSoft font-semibold">Above 50-DMA</span>:
                  trend is intact, buy-the-dip mentality dominates.
                </p>
                <p className="mt-2">
                  <span className="text-accent-redSoft font-semibold">Below 50-DMA</span>:
                  short-term trend has broken — momentum sellers usually pile on; rallies
                  get sold instead of bought.
                </p>
              </>
            }
          />
        </div>
      </details>

      <p className="text-[10px] text-text-muted mt-3 leading-relaxed">
        Negative VIX move + price above 50-DMA + broad participation (RSP keeping up with SPY)
        = textbook risk-on conditions. Diverging from those = caution warranted.
      </p>
    </section>
  );
}

function Explainer({ term, tagline, body }: { term: string; tagline: string; body: React.ReactNode }) {
  return (
    <div className="bg-bg-base rounded-md p-3 border border-bg-border">
      <div className="text-accent-blue font-semibold mb-1">
        {term} <span className="text-text-muted font-normal">— {tagline}</span>
      </div>
      <div className="text-text-secondary leading-relaxed">{body}</div>
    </div>
  );
}

function Metric({ label, value, valueColor, hint, Icon }: {
  label: string; value: string; valueColor: string; hint?: string; Icon: typeof ArrowUp;
}) {
  return (
    <div className="bg-bg-base rounded-md p-3 border border-bg-border">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] uppercase tracking-wider text-text-muted">{label}</span>
        <Icon size={11} className={cn(valueColor)} strokeWidth={2.4} />
      </div>
      <div className={cn("text-lg font-bold tabular-nums", valueColor)}>{value}</div>
      {hint && <div className="text-[10px] text-text-muted leading-snug mt-1">{hint}</div>}
    </div>
  );
}
