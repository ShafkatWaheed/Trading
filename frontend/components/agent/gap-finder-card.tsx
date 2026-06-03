"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Brain, RefreshCw, Loader2, ChevronDown,
  TrendingDown, Minus, TrendingUp, ExternalLink, Globe, AlertCircle,
} from "lucide-react";
import { journalApi } from "@/lib/api/endpoints";
import type { GapFinderDecision, GapFinderResponse } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";


function actionMeta(action: string) {
  const u = action.toUpperCase();
  if (u === "SELL_ALL") return { label: "Sell all",    color: "text-accent-redSoft",   bg: "bg-accent-red/10 border-accent-red/40",   Icon: TrendingDown };
  if (u === "TRIM_50")  return { label: "Trim 50%",    color: "text-accent-redSoft",   bg: "bg-accent-red/[0.06] border-accent-red/30", Icon: TrendingDown };
  if (u === "TRIM_25")  return { label: "Trim 25%",    color: "text-accent-amber",     bg: "bg-accent-amber/[0.06] border-accent-amber/30", Icon: TrendingDown };
  if (u === "HOLD")     return { label: "Hold",        color: "text-text-secondary",   bg: "bg-bg-card2 border-bg-borderHi",            Icon: Minus };
  if (u === "ADD")      return { label: "Add",         color: "text-accent-greenSoft", bg: "bg-accent-green/[0.08] border-accent-green/40", Icon: TrendingUp };
  if (u === "BUY")      return { label: "Buy",         color: "text-accent-greenSoft", bg: "bg-accent-green/10 border-accent-green/40", Icon: TrendingUp };
  return                       { label: action,        color: "text-text-muted",       bg: "bg-bg-card2 border-bg-borderHi",            Icon: Minus };
}

function confidenceTone(c: string): string {
  const u = c.toLowerCase();
  if (u === "high")   return "text-accent-greenSoft";
  if (u === "medium") return "text-accent-amber";
  return "text-text-muted";
}


export function GapFinderCard() {
  const qc = useQueryClient();
  const { data, isLoading, error, isFetching } = useQuery<GapFinderResponse>({
    queryKey: ["gap-finder"],
    queryFn: () => journalApi.gapFinder(false),
    staleTime: 6 * 60 * 60 * 1000,
  });

  const [forceRefreshing, setForceRefreshing] = useState(false);
  const forceRefresh = async () => {
    setForceRefreshing(true);
    try {
      const fresh = await journalApi.gapFinder(true);
      qc.setQueryData(["gap-finder"], fresh);
    } finally {
      setForceRefreshing(false);
    }
  };

  if (isLoading) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <Brain size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">Position Reviewer — AI portfolio adviser</h3>
        </div>
        <Skeleton className="h-64 w-full" />
      </section>
    );
  }

  if (error) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-3">
          <Brain size={16} className="text-accent-violet" />
          <h3 className="text-base font-semibold">Position Reviewer</h3>
        </div>
        <p className="text-text-muted text-sm">{(error as Error).message}</p>
      </section>
    );
  }

  if (!data) return null;

  const hasHoldings = (data.holdings_count ?? 0) > 0;
  const totalRecs = data.sells.length + data.holds.length + data.buys.length;

  return (
    <section className="card-subtle p-6 relative overflow-hidden">
      <div
        className="absolute inset-x-0 top-0 h-24 pointer-events-none opacity-50"
        style={{ background: "radial-gradient(ellipse 60% 100% at 30% 0%, rgba(168, 85, 247, 0.10) 0%, transparent 70%)" }}
      />

      <div className="relative">
        <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <Brain size={16} className="text-accent-violet" />
            <h3 className="text-base font-semibold">Position Reviewer</h3>
            <span className="text-[10px] uppercase tracking-wider text-text-muted">
              {data.holdings_count} holdings · {data.candidates_considered} candidates scanned
            </span>
            {data.meta?.web_research_enabled && (
              <span className="badge text-[10px] bg-accent-violet/10 text-accent-violet border-accent-violet/30 inline-flex items-center gap-1">
                <Globe size={9} />
                web-enabled
              </span>
            )}
            {data.from_cache && (
              <span className="text-[10px] uppercase tracking-wider text-text-muted">cached</span>
            )}
          </div>
          <button
            onClick={forceRefresh}
            disabled={isFetching || forceRefreshing}
            title="Re-judge with fresh web research (~60-180s)"
            className={cn(
              "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium transition-colors",
              "bg-bg-card hover:bg-bg-card2 border border-bg-borderHi text-text-secondary hover:text-text-primary",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            <RefreshCw size={11} className={(isFetching || forceRefreshing) ? "animate-spin" : ""} />
            Regenerate
          </button>
        </div>

        <p className="text-[12px] text-text-secondary leading-relaxed mb-5 max-w-3xl">
          AI portfolio adviser. Claude reads your journal, runs trigger sensors, and (for stocks
          with material signals) reasons over the evidence with fresh web context to recommend
          <span className="text-accent-redSoft"> sells</span>,
          <span className="text-text-secondary"> holds</span>, and
          <span className="text-accent-greenSoft"> buys</span>. Each rec ships with key factors
          and a "what would change my mind" condition.
        </p>

        {!hasHoldings ? (
          <div className="card p-4 border-l-4 border-accent-blue/40">
            <p className="text-[13px] text-text-secondary">
              Log a buy in the journal above to activate the Position Reviewer. With at least one open
              position, Claude will recommend what to sell / hold and find adjacent stocks to buy.
            </p>
          </div>
        ) : totalRecs === 0 ? (
          <p className="text-text-muted text-sm italic">
            No recommendations yet. Click <b>Regenerate</b> to run the pipeline (~60-180s).
          </p>
        ) : (
          <div className="space-y-5">
            {/* SELLS */}
            {data.sells.length > 0 && (
              <Section title="Sell / trim" Icon={TrendingDown} color="text-accent-redSoft" count={data.sells.length}>
                {data.sells.map((d) => <DecisionCard key={d.symbol + d.action} decision={d} />)}
              </Section>
            )}

            {/* BUYS */}
            {data.buys.length > 0 && (
              <Section title="Buy / add" Icon={TrendingUp} color="text-accent-greenSoft" count={data.buys.length}>
                {data.buys.map((d) => <DecisionCard key={d.symbol + d.action} decision={d} />)}
              </Section>
            )}

            {/* HOLDS */}
            {data.holds.length > 0 && (
              <Section title="Hold" Icon={Minus} color="text-text-secondary" count={data.holds.length} collapsedByDefault>
                {data.holds.map((d) => <DecisionCard key={d.symbol + d.action} decision={d} compact />)}
              </Section>
            )}
          </div>
        )}

        <p className="text-[10px] text-text-muted mt-5 pt-3 border-t border-bg-border">
          {data.meta?.judged_by_claude ?? 0} stocks judged by Claude
          {data.meta?.auto_holds ? ` · ${data.meta.auto_holds} auto-held (no triggers fired)` : ""}
          {" · "}Model: {data.meta?.model ?? "haiku"}
          {" · "}WebSearch + WebFetch{" "}
          {data.meta?.web_research_enabled ? "enabled" : "disabled"}.
          Recommendations are research aids, not investment advice. Always validate before trading.
        </p>
      </div>
    </section>
  );
}


function Section({
  title, Icon, color, count, children, collapsedByDefault = false,
}: {
  title: string;
  Icon: typeof TrendingDown;
  color: string;
  count: number;
  children: React.ReactNode;
  collapsedByDefault?: boolean;
}) {
  const [open, setOpen] = useState(!collapsedByDefault);
  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-2 mb-2 group"
      >
        <div className="flex items-center gap-2">
          <Icon size={12} className={color} />
          <span className={cn("font-mono text-[11px] uppercase tracking-[0.22em] font-semibold", color)}>
            {title}
          </span>
          <span className="text-[10px] text-text-muted">· {count}</span>
        </div>
        <ChevronDown
          size={12}
          className={cn(
            "text-text-muted transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open && <div className="space-y-2">{children}</div>}
    </div>
  );
}


function DecisionCard({ decision, compact = false }: { decision: GapFinderDecision; compact?: boolean }) {
  const meta = actionMeta(decision.action);
  const ActionIcon = meta.Icon;
  const [expand, setExpand] = useState(false);

  if (compact) {
    return (
      <div className="flex items-center gap-3 px-3 py-2 rounded-md border border-bg-divider bg-bg-base/20">
        <span className={cn("badge text-[9px] uppercase tracking-wider font-semibold inline-flex items-center gap-1", meta.bg, meta.color)}>
          <ActionIcon size={9} />
          {meta.label}
        </span>
        <Link href={`/deep-dive/${encodeURIComponent(decision.symbol)}`}
              className="font-mono font-bold text-[13px] hover:text-accent-blue">
          ${decision.symbol}
        </Link>
        <span className="text-[11px] text-text-secondary flex-1 truncate">
          {decision.rationale}
        </span>
        <span className={cn("text-[10px] uppercase tracking-wider", confidenceTone(decision.confidence))}>
          {decision.confidence}
        </span>
      </div>
    );
  }

  return (
    <article className={cn(
      "rounded-lg border p-4 transition-colors",
      meta.bg,
    )}>
      <header className="flex items-center justify-between gap-2 mb-2 flex-wrap">
        <div className="flex items-center gap-3">
          <span className={cn("badge text-[10px] uppercase tracking-wider font-semibold inline-flex items-center gap-1", meta.bg, meta.color)}>
            <ActionIcon size={10} />
            {meta.label}
          </span>
          <Link
            href={`/deep-dive/${encodeURIComponent(decision.symbol)}`}
            className="font-mono font-bold text-[18px] text-text-primary hover:text-accent-blue"
          >
            ${decision.symbol}
          </Link>
        </div>
        <span className={cn("text-[10px] uppercase tracking-wider font-semibold", confidenceTone(decision.confidence))}>
          {decision.confidence} confidence
        </span>
      </header>

      <p className="text-[13px] leading-relaxed text-text-secondary mb-3">
        {decision.rationale}
      </p>

      {decision.key_factors.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {decision.key_factors.map((f, i) => (
            <span key={i} className="badge text-[10px] bg-bg-base text-text-secondary border-bg-borderHi">
              {f}
            </span>
          ))}
        </div>
      )}

      {decision.reevaluate_if.length > 0 && (
        <div className="pt-3 border-t border-bg-divider">
          <div className="font-mono text-[9px] tracking-[0.22em] uppercase text-text-muted mb-1.5 flex items-center gap-1.5">
            <AlertCircle size={9} /> Reevaluate if
          </div>
          <ul className="space-y-0.5">
            {decision.reevaluate_if.map((r, i) => (
              <li key={i} className="text-[12px] text-text-secondary leading-snug">
                · {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {decision.web_sources.length > 0 && (
        <div className="pt-3 mt-2 border-t border-bg-divider">
          <div className="font-mono text-[9px] tracking-[0.22em] uppercase text-text-muted mb-1.5 flex items-center gap-1.5">
            <Globe size={9} /> Web sources Claude consulted
          </div>
          <ul className="space-y-0.5">
            {decision.web_sources.map((u, i) => (
              <li key={i} className="text-[11px]">
                <a href={u} target="_blank" rel="noopener noreferrer"
                   className="text-accent-blue hover:underline inline-flex items-center gap-1 break-all">
                  <ExternalLink size={9} />
                  {(() => {
                    try { return new URL(u).hostname; } catch { return u.slice(0, 60); }
                  })()}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {decision.evidence && (
        <button
          onClick={() => setExpand(!expand)}
          className="mt-3 text-[10px] uppercase tracking-wider text-text-muted hover:text-text-primary inline-flex items-center gap-1"
        >
          Raw evidence
          <ChevronDown size={10} className={cn("transition-transform", expand && "rotate-180")} />
        </button>
      )}
      {expand && decision.evidence && (
        <pre className="mt-2 p-3 rounded-md bg-bg-base/40 border border-bg-divider text-[10px] text-text-muted overflow-x-auto leading-relaxed">
          {JSON.stringify(decision.evidence, null, 2)}
        </pre>
      )}
    </article>
  );
}
