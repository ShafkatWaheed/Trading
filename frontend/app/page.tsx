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
import { GeopoliticalRisks } from "@/components/market/geopolitical-risks";
import { DisruptionThemes } from "@/components/market/disruption-themes";
import { SimulationReplay } from "@/components/simulation-replay";
import { Skeleton } from "@/components/ui/skeleton";
import { SectionHeading } from "@/components/ui/card";
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
      <PageHeader
        icon={Activity}
        title="Market Pulse"
        subtitle="Understand the market regime before picking stocks."
        accent="text-accent-blue"
        iconBg="bg-accent-blue/10"
      />

      <div className="space-y-8">
        <SimulationReplay step="market_pulse" accent="blue" />

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

        <section>
          <SectionHeading title="Key Economic Indicators" />
          <KpiGrid kpis={data?.kpis} loading={isLoading && !data} />
        </section>

        {data?.yield_curve && (
          <section>
            <YieldCurveCard data={data.yield_curve} />
          </section>
        )}

        <section>
          <SectionHeading
            title="Economic Calendar"
            trailing={<Calendar size={13} className="text-accent-blue" />}
          />
          <EconomicCalendar events={calendar.data?.events} loading={calendar.isLoading} />
        </section>

        <section>
          <SectionHeading
            title="Geopolitical & Event Risk"
            trailing={<Globe size={13} className="text-accent-amber" />}
          />
          <GeopoliticalRisks events={geo.data?.events} loading={geo.isLoading} />
        </section>

        <section>
          <SectionHeading
            title="Disruptive Technology"
            trailing={
              <div className="flex items-center gap-2">
                {disruption.data?.source === "fallback" && (
                  <span className="text-[10px] text-text-muted">
                    Built-in (configure TAVILY_API_KEY for live)
                  </span>
                )}
                <Sparkles size={13} className="text-accent-violet" />
              </div>
            }
          />
          <DisruptionThemes themes={disruption.data?.themes} loading={disruption.isLoading} />
        </section>

        <section>
          <SectionHeading
            title="Sector Money Flow"
            trailing={<PeriodChips value={period} onChange={setPeriod} accent="green" size="sm" />}
          />

          {data && <SectorSummaryBar summary={data.sector_summary} period={period} />}
          <SectorFlows sectors={data?.sectors} loading={isLoading && !data} />
        </section>

        {data?.implications && data.implications.length > 0 && (
          <section>
            <ImplicationsList items={data.implications} />
          </section>
        )}

        <Link
          href="/discover"
          className="card card-hover p-6 flex items-center justify-between group bg-gradient-to-r from-accent-blue/5 to-bg-card border-l-4 border-accent-blue/40"
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
