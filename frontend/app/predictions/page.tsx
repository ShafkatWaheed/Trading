"use client";

/**
 * Daily Top-10 Predictions
 *
 * Three sections:
 *   1. Today's predictions — symbols + reasoning + active strategy
 *   2. Yesterday's results — predictions enriched with actual close + universe rank
 *   3. Accuracy — rolling 30-day hit rate (default threshold: top 25 in Tier A)
 *
 * Backend writes predictions at 6:30 ET via scheduler, records actuals at
 * 16:15 ET. The "today" call lazy-generates on first hit if the scheduler
 * hasn't fired (e.g. uvicorn was off during the morning slot).
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Target, TrendingUp, Calendar as CalendarIcon, Activity, Sparkles, CheckCircle2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { predictionsApi } from "@/lib/api/endpoints";
import type {
  PredictionsPayload,
  PredictionsAccuracyPayload,
  PredictionPick,
  PredictionStrategyRow,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

function _yesterdayISO(): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function fmtRank(rank: number | null | undefined, size: number | null | undefined): string {
  if (rank == null) return "—";
  return size ? `${rank} / ${size}` : `#${rank}`;
}

function pickTone(rank: number | null | undefined, threshold = 25): string {
  if (rank == null) return "border-bg-divider";
  if (rank <= 10) return "border-l-accent-green/60";
  if (rank <= threshold) return "border-l-accent-blue/60";
  return "border-l-bg-divider";
}

function pctTone(v: number | null | undefined): string {
  if (v == null) return "text-text-muted";
  if (v > 0) return "text-accent-greenSoft";
  if (v < 0) return "text-accent-redSoft";
  return "text-text-muted";
}

function PickRow({ p, showActuals }: { p: PredictionPick; showActuals: boolean }) {
  return (
    <div
      className={cn(
        "card p-3 border-l-4 flex items-center gap-3",
        showActuals ? pickTone(p.universe_rank) : "border-l-bg-divider",
      )}
    >
      <div className="font-mono text-[11px] tabular-nums w-7 text-text-muted shrink-0">
        #{p.rank}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-text-primary">{p.symbol}</div>
        {p.reasoning && (
          <div className="text-[11px] text-text-secondary mt-0.5 truncate">{p.reasoning}</div>
        )}
      </div>
      {showActuals && (
        <>
          <div className="text-right shrink-0 w-20">
            <div className={cn("text-[12px] font-semibold tabular-nums", pctTone(p.actual_change_pct))}>
              {fmtPct(p.actual_change_pct)}
            </div>
            <div className="text-[10px] text-text-muted mt-0.5">close</div>
          </div>
          <div className="text-right shrink-0 w-16">
            <div className="text-[12px] font-mono tabular-nums text-text-secondary">
              {fmtRank(p.universe_rank, p.universe_size)}
            </div>
            <div className="text-[10px] text-text-muted mt-0.5">univ rank</div>
          </div>
        </>
      )}
    </div>
  );
}

function AccuracyCard({ acc }: { acc: PredictionsAccuracyPayload }) {
  const rate = acc.hit_rate;
  // The naive baseline: random chance of landing in top-N out of universe.
  // We don't have universe size in the payload, but a 25-rank-threshold on a
  // ~500-name Tier A = ~5%. Anything above that is signal.
  const baseline = acc.hit_threshold / 500;
  const above_baseline = rate - baseline;

  const tone =
    above_baseline > 0.05  ? "border-accent-green/60 bg-accent-green/5" :
    above_baseline > 0     ? "border-accent-blue/60  bg-accent-blue/5" :
                             "border-accent-amber/60 bg-accent-amber/5";

  return (
    <div className={cn("card p-5 border-l-4", tone)}>
      <div className="flex items-baseline justify-between mb-3">
        <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-text-muted">
          Rolling {acc.window_days}-day accuracy
        </span>
        <span className="text-[11px] text-text-muted">
          {acc.days_evaluated} days evaluated
        </span>
      </div>
      <div className="flex items-end gap-6 flex-wrap">
        <div>
          <div className="text-3xl font-bold text-text-primary tabular-nums">
            {(rate * 100).toFixed(1)}%
          </div>
          <div className="text-[10px] text-text-muted mt-1">
            {acc.hits} of {acc.predictions_total} picks landed in top {acc.hit_threshold}
          </div>
        </div>
        <div className="text-[11px] text-text-secondary leading-relaxed flex-1 min-w-[200px]">
          {above_baseline > 0
            ? `+${(above_baseline * 100).toFixed(1)}pp above the ~${(baseline * 100).toFixed(1)}% random-chance baseline.`
            : `Below the ~${(baseline * 100).toFixed(1)}% random-chance baseline — strategy needs work.`}
        </div>
      </div>
      {Object.keys(acc.by_strategy).length > 1 && (
        <div className="mt-4 pt-3 border-t border-bg-divider">
          <div className="font-mono text-[9px] uppercase tracking-wider text-text-muted mb-2">
            By strategy version
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {Object.entries(acc.by_strategy).map(([v, b]) => (
              <div key={v} className="text-[11px]">
                <span className="font-mono text-text-muted">v{v}</span>{" "}
                <span className="font-semibold text-text-primary">{(b.hit_rate * 100).toFixed(0)}%</span>{" "}
                <span className="text-text-muted">({b.hits}/{b.predictions})</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function PredictionsPage() {
  const today = useQuery<PredictionsPayload>({
    queryKey: ["predictions", "today"],
    queryFn: () => predictionsApi.today(),
    staleTime: 5 * 60 * 1000,
  });

  const yesterday = useQuery<PredictionsPayload>({
    queryKey: ["predictions", "yesterday", _yesterdayISO()],
    queryFn: () => predictionsApi.withActuals(_yesterdayISO()),
    staleTime: 30 * 60 * 1000,
  });

  const accuracy = useQuery<PredictionsAccuracyPayload>({
    queryKey: ["predictions", "accuracy", 30, 25],
    queryFn: () => predictionsApi.accuracy(30, 25),
    staleTime: 30 * 60 * 1000,
  });

  const strategiesQ = useQuery<{ strategies: PredictionStrategyRow[] }>({
    queryKey: ["predictions", "strategies"],
    queryFn: () => predictionsApi.strategies(),
    staleTime: 5 * 60 * 1000,
  });

  const qc = useQueryClient();
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);
  const reviewM = useMutation({
    mutationFn: () => predictionsApi.reviewStrategy(14, false),
    onSuccess: (res) => {
      if (res.proposed && res.proposal) {
        setReviewMessage(`Claude proposed v${res.proposal.version} ("${res.proposal.name}"). Review and activate below.`);
      } else {
        setReviewMessage(`No new proposal — ${res.reason ?? "unknown reason"}.`);
      }
      qc.invalidateQueries({ queryKey: ["predictions", "strategies"] });
    },
    onError: (e: Error) => {
      setReviewMessage(`Review failed: ${e.message}`);
    },
  });
  const activateM = useMutation({
    mutationFn: (version: number) => predictionsApi.activateStrategy(version),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["predictions"] });
    },
  });

  const activeStrategy = today.data?.strategy_name || "—";

  return (
    <div>
      <PageHeader
        icon={Target}
        title="Daily Predictions"
        subtitle="Top-10 gainers picked each morning, scored after close, strategy adapts."
        accent="text-accent-blue"
        iconBg="bg-accent-blue/10"
        trailing={
          <div className="flex items-center gap-2 text-[11px] text-text-muted font-mono">
            <Activity size={11} />
            strategy: {activeStrategy}
          </div>
        }
      />

      {/* ── Section 1: Today ────────────────────────────────────── */}
      <section className="mb-8">
        <div className="flex items-baseline gap-3 mb-3">
          <TrendingUp size={14} className="text-accent-blue translate-y-[2px]" />
          <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-accent-blueSoft">
            Today · {today.data?.date ?? "…"}
          </span>
          <span className="text-[11px] text-text-muted">
            scored from {today.data?.universe_size ?? "—"} Tier A candidates
          </span>
        </div>
        {today.isLoading && (
          <div className="card p-6 text-text-muted text-[12px] italic">
            Scoring Tier A universe… first call of the day takes ~1 min.
          </div>
        )}
        {today.error && (
          <div className="card p-6 border-l-4 border-accent-red/40">
            <p className="text-accent-redSoft text-[13px]">Could not load today's predictions.</p>
            <p className="text-text-muted text-[11px] mt-1">{(today.error as Error).message}</p>
          </div>
        )}
        {today.data && today.data.picks.length === 0 && !today.isLoading && (
          <div className="card p-6 text-text-muted text-[12px] italic">
            No picks yet — Tier A universe may be empty.
          </div>
        )}
        {today.data && today.data.picks.length > 0 && (
          <div className="space-y-2">
            {today.data.picks.map((p) => (
              <PickRow key={p.symbol} p={p} showActuals={false} />
            ))}
          </div>
        )}
      </section>

      {/* ── Section 2: Yesterday's results ──────────────────────── */}
      <section className="mb-8">
        <div className="flex items-baseline gap-3 mb-3">
          <CalendarIcon size={14} className="text-text-secondary translate-y-[2px]" />
          <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-text-muted">
            Yesterday · {yesterday.data?.date ?? _yesterdayISO()}
          </span>
          {yesterday.data?.actuals_present === false && (
            <span className="text-[11px] text-accent-amber">
              actuals not yet recorded — runs after 16:15 ET
            </span>
          )}
        </div>
        {yesterday.isLoading && (
          <div className="card p-4 text-text-muted text-[12px] italic">Loading…</div>
        )}
        {yesterday.data && yesterday.data.picks.length === 0 && !yesterday.isLoading && (
          <div className="card p-4 text-text-muted text-[12px] italic">
            No predictions were recorded for yesterday.
          </div>
        )}
        {yesterday.data && yesterday.data.picks.length > 0 && (
          <div className="space-y-2">
            {yesterday.data.picks.map((p) => (
              <PickRow key={p.symbol} p={p} showActuals />
            ))}
          </div>
        )}
      </section>

      {/* ── Section 3: Rolling accuracy ──────────────────────────── */}
      <section className="mb-8">
        <div className="flex items-baseline gap-3 mb-3">
          <Activity size={14} className="text-accent-greenSoft translate-y-[2px]" />
          <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-accent-greenSoft">
            Accuracy
          </span>
        </div>
        {accuracy.isLoading && (
          <div className="card p-4 text-text-muted text-[12px] italic">Loading…</div>
        )}
        {accuracy.data && accuracy.data.predictions_total === 0 && !accuracy.isLoading && (
          <div className="card p-4 text-text-muted text-[12px] italic">
            No completed prediction/actual pairs yet — accuracy will populate after the first
            full trading day.
          </div>
        )}
        {accuracy.data && accuracy.data.predictions_total > 0 && (
          <AccuracyCard acc={accuracy.data} />
        )}
      </section>

      {/* ── Section 4: Strategy log + Claude proposals ─────────────── */}
      <section className="mb-8">
        <div className="flex items-baseline justify-between mb-3 gap-3 flex-wrap">
          <div className="flex items-baseline gap-3">
            <Sparkles size={14} className="text-accent-amber translate-y-[2px]" />
            <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-accent-amber">
              Strategy log
            </span>
            <span className="text-[11px] text-text-muted">
              Claude reviews completed predictions weekly and proposes new strategies
            </span>
          </div>
          <button
            onClick={() => reviewM.mutate()}
            disabled={reviewM.isPending}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[11px] font-medium transition-colors",
              "bg-accent-amber/10 hover:bg-accent-amber/20 border border-accent-amber/40 text-accent-amber",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            <Sparkles size={11} />
            {reviewM.isPending ? "Asking Claude…" : "Request new proposal"}
          </button>
        </div>
        {reviewMessage && (
          <div className="card-subtle p-3 mb-3 text-[11px] text-text-secondary">
            {reviewMessage}
          </div>
        )}
        {strategiesQ.data && strategiesQ.data.strategies.length > 0 && (
          <div className="space-y-2">
            {[...strategiesQ.data.strategies].reverse().map((s) => {
              const isProposed = !s.is_active && s.activated_at == null;
              const tone =
                s.is_active   ? "border-l-accent-green/60 bg-accent-green/5" :
                isProposed    ? "border-l-accent-amber/60 bg-accent-amber/5" :
                                "border-l-bg-divider";
              return (
                <div key={s.version} className={cn("card p-3 border-l-4", tone)}>
                  <div className="flex items-baseline justify-between gap-3 flex-wrap">
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono text-[10px] text-text-muted">v{s.version}</span>
                      <span className="text-[13px] font-semibold text-text-primary">{s.name}</span>
                      {s.is_active && (
                        <span className="badge text-[9px] bg-accent-green/10 text-accent-greenSoft border-accent-green/30">
                          <CheckCircle2 size={9} className="inline mr-0.5" />
                          ACTIVE
                        </span>
                      )}
                      {isProposed && (
                        <span className="badge text-[9px] bg-accent-amber/10 text-accent-amber border-accent-amber/30">
                          PROPOSED
                        </span>
                      )}
                    </div>
                    {isProposed && (
                      <button
                        onClick={() => activateM.mutate(s.version)}
                        disabled={activateM.isPending}
                        className="text-[10px] px-2 py-1 rounded-md bg-accent-blue/10 text-accent-blueSoft border border-accent-blue/40 hover:bg-accent-blue/20 disabled:opacity-50"
                      >
                        {activateM.isPending ? "Activating…" : "Activate"}
                      </button>
                    )}
                  </div>
                  <p className="text-[11px] text-text-secondary mt-1 leading-relaxed">{s.description}</p>
                  <div className="mt-2 font-mono text-[10px] text-text-muted">
                    signal={String(s.config.ranking_signal)} ·
                    lookback={String(s.config.lookback_days)}d ·
                    top_n={String(s.config.top_n)}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
