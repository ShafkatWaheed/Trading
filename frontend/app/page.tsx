"use client";

import Link from "next/link";
import { useState } from "react";
import { Activity, Calendar, Globe, Sparkles, ArrowRight } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { RegimeCard } from "@/components/market/regime-card";
import { KpiGrid } from "@/components/market/kpi-grid";
import { YieldCurveCard } from "@/components/market/yield-curve-card";
import { SectorFlows } from "@/components/market/sector-flows";
import { SectorSummaryBar } from "@/components/market/sector-summary-bar";
import { ImplicationsList } from "@/components/market/implications-list";
import { EconomicCalendar } from "@/components/market/economic-calendar";
import { NextCatalystPill } from "@/components/market/next-catalyst-pill";
import { GeopoliticalRisks } from "@/components/market/geopolitical-risks";
import { DisruptionThemes } from "@/components/market/disruption-themes";
import { MarketTakeaway } from "@/components/market/market-takeaway";
import { StickyMarketBar } from "@/components/market/sticky-market-bar";
import { LiveIndicesStrip } from "@/components/market/live-indices-strip";
import { BreadthCard } from "@/components/market/breadth-card";
import { TopMovers } from "@/components/market/top-movers";
import { MarketNews } from "@/components/market/market-news";
import { SectionHeader } from "@/components/deep-dive/section-header";
import { SimulationReplay } from "@/components/simulation-replay";
import { Skeleton } from "@/components/ui/skeleton";
import { PeriodChips } from "@/components/ui/period-chips";
import { useMarketPulse } from "@/lib/hooks/use-market-pulse";
import {
  useEconomicCalendar,
  useGeopoliticalEvents,
  useDisruptionThemes,
} from "@/lib/hooks/use-market-extras";
import { formatRelativeTime } from "@/lib/utils";


export default function MarketPulsePage() {
  const [period, setPeriod] = useState("1M");
  const { data, isLoading, error } = useMarketPulse(period);
  const calendar = useEconomicCalendar();
  const geo = useGeopoliticalEvents();
  const disruption = useDisruptionThemes();

  return (
    <div>
      {/* Sticky live ticker — slides in below the nav after scroll */}
      <StickyMarketBar />

      <PageHeader
        icon={Activity}
        title="Market Pulse"
        subtitle="Understand the market regime before picking stocks."
        accent="text-accent-blue"
        iconBg="bg-accent-blue/10"
      />

      <div className="space-y-6">
        <SimulationReplay step="market_pulse" accent="blue" />

        {/* ── 01 · TODAY'S TAKEAWAY (hero) ─────────────────────────────── */}
        <SectionHeader index={1} label="Today's takeaway" subtitle="3-second read · what does the market favor today" id="takeaway" />

        <MarketTakeaway />

        <LiveIndicesStrip />

        {isLoading && !data ? (
          <Skeleton className="h-32" />
        ) : error ? (
          <div className="card p-6 border-l-4 border-accent-red/40">
            <p className="text-accent-redSoft">Failed to load market pulse.</p>
            <p className="text-text-muted text-sm mt-1">{(error as Error).message}</p>
          </div>
        ) : data ? (
          <RegimeCard regime={data.regime} explanation={data.regime_explanation} />
        ) : null}

        {/* ── 02 · MACRO BACKDROP ──────────────────────────────────────── */}
        <SectionHeader index={2} label="Macro backdrop" subtitle="Fed · rates · volatility · yield curve" id="macro" />

        <section>
          <KpiGrid kpis={data?.kpis} loading={isLoading && !data} />
        </section>

        {data?.yield_curve && (
          <section>
            <YieldCurveCard data={data.yield_curve} />
          </section>
        )}

        {/* ── 03 · MARKET INTERNALS ────────────────────────────────────── */}
        <SectionHeader index={3} label="Market internals" subtitle="breadth · top movers · what's actually moving" id="internals" />

        <BreadthCard />
        <TopMovers />

        {/* ── 04 · WHAT'S HAPPENING ────────────────────────────────────── */}
        <SectionHeader index={4} label="What's happening" subtitle="top headlines · sentiment" id="news" />

        <MarketNews />

        {/* ── 05 · WHERE MONEY IS GOING ────────────────────────────────── */}
        <SectionHeader index={5} label="Where money is going" subtitle="sector flows · disruptive themes" id="flows" />

        <section>
          <div className="flex items-center justify-end mb-2">
            <PeriodChips value={period} onChange={setPeriod} accent="green" size="sm" />
          </div>
          {data && <SectorSummaryBar summary={data.sector_summary} period={period} />}
          <SectorFlows sectors={data?.sectors} loading={isLoading && !data} />
        </section>

        <DisruptionThemes themes={disruption.data?.themes} loading={disruption.isLoading} />
        {disruption.data?.source === "fallback" && (
          <p className="text-[10px] text-text-muted -mt-2">
            Built-in themes (configure TAVILY_API_KEY for live AI-derived themes)
          </p>
        )}

        {/* ── 06 · UPCOMING CATALYSTS ──────────────────────────────────── */}
        <SectionHeader index={6} label="Upcoming catalysts" subtitle="economic calendar · geopolitical risk" id="catalysts" />

        <NextCatalystPill
          nextEvent={calendar.data?.next_event}
          nextHighImpact={calendar.data?.next_high_impact}
        />

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <EconomicCalendar events={calendar.data?.events} loading={calendar.isLoading} />
          <GeopoliticalRisks events={geo.data?.events} loading={geo.isLoading} />
        </section>

        {/* ── 07 · TRADING IMPLICATIONS ────────────────────────────────── */}
        {data?.implications && data.implications.length > 0 && (
          <>
            <SectionHeader index={7} label="Trading implications" subtitle="what to do with this regime" id="implications" />
            <ImplicationsList items={data.implications} />
          </>
        )}

        <Link
          href="/discover"
          className="card card-hover p-6 flex items-center justify-between group bg-gradient-to-r from-accent-blue/5 to-bg-card border-l-4 border-accent-blue/40 mt-2"
        >
          <div>
            <div className="text-xs uppercase tracking-wider text-text-muted">Step 2</div>
            <div className="text-lg font-semibold mt-0.5">Find Stocks to Trade</div>
            <div className="text-sm text-text-secondary mt-1">
              Now that you understand the market, let&apos;s find ranked opportunities to act on.
            </div>
          </div>
          <ArrowRight
            size={20}
            className="text-accent-blue group-hover:translate-x-1 transition-transform"
          />
        </Link>

        {data && (
          <p className="text-xs text-text-muted text-right">
            Last updated {formatRelativeTime(data.last_updated)}
          </p>
        )}
      </div>
    </div>
  );
}
