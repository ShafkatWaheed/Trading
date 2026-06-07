"use client";

/**
 * Daily Picks — what to buy today.
 *
 * 8 specialized agent personalities each pick their top 5 stocks via parallel
 * Claude calls on the backend. The page surfaces:
 *   • Consensus row — stocks 3+ agents agree on (highest conviction)
 *   • Contrarian highlights — each agent's best unique pick
 *   • Full grid — one column per agent with their full pick list
 *
 * Backend cache lifetime is 8h so picks are stable within a trading session.
 * The /daily-picks endpoint isn't wired yet — page renders a friendly empty
 * state until the backend ships.
 */

import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Sparkles, RefreshCw, Users, Target, AlertCircle,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { FreshnessPill } from "@/components/ui/freshness-pill";
import { dailyPicksApi } from "@/lib/api/endpoints";
import type {
  DailyPicks,
  DailyPicksAgentResult,
  DailyPicksConsensusRow,
  DailyPicksContrarian,
  OptionPlan,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";


// ── conviction → tone ────────────────────────────────────────────────

function convictionClass(c: string): string {
  if (c === "high") return "bg-accent-green/15 text-accent-greenSoft border-accent-green/40";
  if (c === "med" || c === "medium")
    return "bg-accent-blue/15 text-accent-blueSoft border-accent-blue/40";
  return "bg-bg-card2 text-text-muted border-bg-borderHi";
}


// ── option plan block ────────────────────────────────────────────────

function OptionPlanRow({ plan }: { plan?: OptionPlan }) {
  if (!plan) return null;
  return (
    <div className="mt-1 text-xs grid grid-cols-3 gap-x-3 gap-y-0.5">
      <span className="inline-flex items-center rounded px-1.5 py-0.5 bg-emerald-900/40 text-emerald-300">
        {plan.direction === "bullish" ? "Calls" : "Puts"}
      </span>
      <span>Entry <b>{plan.entry ?? "—"}</b></span>
      <span>R:R <b>{plan.rr_ratio ?? "—"}</b></span>
      <span className="text-emerald-400">Exit ▲ {plan.take_profit ?? "—"}</span>
      <span className="text-red-400">Exit ▼ {plan.stop_loss ?? "—"}</span>
      <span className="text-zinc-400">S/R {plan.support ?? "—"}–{plan.resistance ?? "—"}</span>
      <span className="col-span-3 text-zinc-400">
        {plan.contract_status === "ok" && plan.contract
          ? `${plan.contract.type.toUpperCase()} ${plan.contract.strike} @ ${plan.contract.expiry} · prem ${plan.contract.premium ?? "—"} · IV ${plan.contract.iv ?? "—"}`
          : "options data unavailable"}
      </span>
    </div>
  );
}


// ── consensus row ────────────────────────────────────────────────────

function ConsensusCard({ row, plan }: { row: DailyPicksConsensusRow; plan?: OptionPlan }) {
  return (
    <div className="card-subtle p-4 border-l-4 border-accent-green/60">
      <div className="flex items-baseline justify-between mb-2">
        <Link
          href={`/deep-dive/${encodeURIComponent(row.symbol)}`}
          className="font-mono text-lg font-bold hover:text-accent-blueSoft transition-colors"
        >
          ${row.symbol}
        </Link>
        <span className="text-[11px] text-text-secondary">
          {row.agent_count} agents
        </span>
      </div>
      <ul className="space-y-1.5 text-[13px]">
        {row.agents.slice(0, 5).map((a, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="text-[10px] px-1.5 py-0.5 rounded border bg-bg-base text-text-secondary border-bg-borderHi whitespace-nowrap">
              {a.agent_name}
            </span>
            <span className="text-text-primary flex-1 leading-snug">
              {a.rationale}
            </span>
            <span
              className={cn(
                "text-[10px] px-1 rounded border whitespace-nowrap",
                convictionClass(a.conviction),
              )}
            >
              {a.conviction}
            </span>
          </li>
        ))}
      </ul>
      <OptionPlanRow plan={plan} />
    </div>
  );
}


// ── contrarian card ──────────────────────────────────────────────────

function ContrarianCard({ pick, plan }: { pick: DailyPicksContrarian; plan?: OptionPlan }) {
  return (
    <div className="card-muted p-3">
      <div className="flex items-baseline justify-between mb-1 gap-2">
        <Link
          href={`/deep-dive/${encodeURIComponent(pick.symbol)}`}
          className="font-mono font-semibold hover:text-accent-blueSoft transition-colors"
        >
          ${pick.symbol}
        </Link>
        <span className="text-[10px] text-text-secondary truncate">
          {pick.agent_name}
        </span>
      </div>
      <p className="text-[11px] text-text-primary leading-snug">{pick.rationale}</p>
      <OptionPlanRow plan={plan} />
    </div>
  );
}


// ── full grid (one column per agent) ─────────────────────────────────

function AgentColumn({ agent, plans }: { agent: DailyPicksAgentResult; plans: Record<string, OptionPlan> }) {
  return (
    <div className="card-muted p-3 min-w-[240px] shrink-0">
      <h4 className="font-semibold mb-2 flex items-center gap-1.5 text-[13px]">
        <Sparkles className="w-3.5 h-3.5 text-accent-violet" />
        {agent.agent_name}
      </h4>
      {agent.error ? (
        <p className="text-[11px] text-accent-redSoft flex items-start gap-1">
          <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" /> {agent.error}
        </p>
      ) : (
        <ul className="space-y-2 text-[11px]">
          {agent.picks.map((pk, i) => (
            <li key={i}>
              <div className="flex items-baseline gap-1.5">
                <Link
                  href={`/deep-dive/${encodeURIComponent(pk.symbol)}`}
                  className="font-mono font-semibold hover:text-accent-blueSoft transition-colors"
                >
                  ${pk.symbol}
                </Link>
                <span
                  className={cn(
                    "text-[9px] px-1 rounded border",
                    convictionClass(pk.conviction),
                  )}
                >
                  {pk.conviction}
                </span>
                <span
                  className="text-text-secondary flex-1 truncate"
                  title={pk.rationale}
                >
                  {pk.rationale}
                </span>
              </div>
              <OptionPlanRow plan={plans[pk.symbol.toUpperCase()]} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}


// ── page ─────────────────────────────────────────────────────────────

export default function DailyPicksPage() {
  const qc = useQueryClient();
  const { data, isLoading, error, isFetching } = useQuery<DailyPicks>({
    queryKey: ["daily-picks"],
    queryFn: () => dailyPicksApi.get(),
    staleTime: 8 * 60 * 60 * 1000, // 8h — matches backend cache lifetime
    retry: false, // endpoint isn't wired yet; don't burn retries while skeleton
  });

  const refresh = useMutation({
    mutationFn: () => dailyPicksApi.get(true),
    onSuccess: (fresh) => qc.setQueryData(["daily-picks"], fresh),
  });

  const busy = refresh.isPending || isFetching;

  return (
    <div>
      <PageHeader
        icon={Target}
        title="Daily Picks"
        subtitle="What to buy today — 8 agents, ranked by consensus"
        accent="text-accent-blue"
        iconBg="bg-accent-blue/10"
        trailing={
          <div className="flex items-center gap-2">
            <FreshnessPill iso={data?.generated_at} />
            <button
              onClick={() => refresh.mutate()}
              disabled={busy}
              title="Bypass cache and re-run the 8-agent fan-out (~90s)"
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium transition-colors",
                "bg-bg-card hover:bg-bg-card2 border border-bg-borderHi text-text-secondary hover:text-text-primary",
                "disabled:opacity-50 disabled:cursor-not-allowed",
              )}
            >
              <RefreshCw size={11} className={busy ? "animate-spin" : ""} />
              Refresh
            </button>
          </div>
        }
      />

      {isLoading && (
        <div className="space-y-6">
          <Skeleton className="h-3 w-32" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
          <Skeleton className="h-40 w-full" />
        </div>
      )}

      {error && (
        <div className="card p-6 border-l-4 border-accent-amber/40">
          <p className="text-accent-amber font-semibold mb-1">
            Picks pipeline not online yet
          </p>
          <p className="text-text-secondary text-[13px]">
            The /daily-picks endpoint hasn't been wired on the backend yet.
            Once it's live the page will populate with 8-agent consensus,
            contrarian highlights, and the full per-agent grid.
          </p>
          <p className="text-text-muted text-[11px] mt-2">
            {(error as Error).message}
          </p>
        </div>
      )}

      {data && (
        <div className="space-y-8">
          <p className="text-[11px] text-zinc-500 mt-1">
            Option levels are model-derived from technicals for research only — not trading advice. Options carry substantial risk.
          </p>

          {/* Consensus section */}
          {(() => {
            const plans = data.option_plans ?? {};
            return (
              <>
                <section className="animate-rise">
                  <h2 className="text-[15px] font-semibold mb-3 flex items-center gap-2">
                    <Users className="w-4 h-4 text-accent-greenSoft" />
                    High Conviction
                    <span className="text-[12px] text-text-secondary font-normal">
                      stocks 3+ agents agree on
                    </span>
                  </h2>
                  {data.consensus.length === 0 ? (
                    <p className="text-[13px] text-text-secondary italic">
                      No strong consensus today. Each agent leaned their own
                      direction — see contrarian picks below.
                    </p>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {data.consensus.slice(0, 6).map((c) => (
                        <ConsensusCard key={c.symbol} row={c} plan={plans[c.symbol.toUpperCase()]} />
                      ))}
                    </div>
                  )}
                </section>

                {/* Contrarian section */}
                <section className="animate-rise">
                  <h2 className="text-[15px] font-semibold mb-3 flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-accent-violet" />
                    Each Agent&apos;s Edge
                    <span className="text-[12px] text-text-secondary font-normal">
                      best pick no one else saw
                    </span>
                  </h2>
                  {data.contrarians.length === 0 ? (
                    <p className="text-[13px] text-text-secondary italic">
                      No standout contrarian picks today — agents largely overlapped.
                    </p>
                  ) : (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      {data.contrarians.map((p) => (
                        <ContrarianCard key={`${p.agent_key}:${p.symbol}`} pick={p} plan={plans[p.symbol.toUpperCase()]} />
                      ))}
                    </div>
                  )}
                </section>

                {/* Full grid */}
                <section className="animate-rise">
                  <h2 className="text-[15px] font-semibold mb-3 flex items-center gap-2">
                    All Picks
                    <span className="text-[12px] text-text-secondary font-normal">
                      full list per agent
                    </span>
                  </h2>
                  {data.agents.length === 0 ? (
                    <p className="text-[13px] text-text-secondary italic">
                      Agents haven&apos;t reported yet.
                    </p>
                  ) : (
                    <div className="overflow-x-auto flex gap-3 pb-3">
                      {data.agents.map((a) => (
                        <AgentColumn key={a.agent_key} agent={a} plans={plans} />
                      ))}
                    </div>
                  )}
                </section>
              </>
            );
          })()}

          <footer className="text-[11px] text-text-muted pt-4 border-t border-bg-divider">
            Generated{" "}
            {data.generated_at && new Date(data.generated_at).toLocaleString()}
            {data.as_of_date && ` · ${data.as_of_date}`}
            {data.from_cache && " (cached)"}
          </footer>
        </div>
      )}
    </div>
  );
}
