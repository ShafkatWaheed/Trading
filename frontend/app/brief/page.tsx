"use client";

/**
 * The Brief — story-driven daily research synthesis.
 *
 * Pipeline runs on the backend (5 phases — context → discovery → score →
 * enrich → narrate). This page just renders the resulting structure:
 *   • Market story (headline + 2-3 paragraphs + investment angles chips)
 *   • Ranked picks (each with snapshot pills + Claude narrative + why-now)
 *   • Closing wrap-up
 *   • Ask AI section (unchanged — free-text query → context_search)
 */

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen, RefreshCw, Loader2, Sparkles, ArrowUpRight, AlertTriangle,
  TrendingUp, ShieldCheck, Compass, Wind, Tornado, CloudFog, Sun, Gauge, X,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { FreshnessPill } from "@/components/ui/freshness-pill";
import { Skeleton } from "@/components/ui/skeleton";
import { briefApi, contextSearchApi } from "@/lib/api/endpoints";
import type {
  Brief, BriefPick, BriefInvestmentAngle, BriefMarketStory, BriefChapter,
  BriefLens, BriefLensConvergence,
  ContextSearchResponse, ContextSearchStock,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";


// ── narrative renderer: <b>$TICKER</b> → clickable chip ──────────────

function renderNarrative(html: string) {
  const parts = html.split(/(<b>\$[A-Z][A-Z0-9.\-]{0,8}<\/b>)/g);
  return parts.map((part, i) => {
    const m = part.match(/^<b>\$([A-Z][A-Z0-9.\-]{0,8})<\/b>$/);
    if (m) {
      const sym = m[1];
      return (
        <Link
          key={i}
          href={`/deep-dive/${encodeURIComponent(sym)}`}
          className="font-mono font-semibold text-accent-blueSoft hover:text-accent-blue underline decoration-accent-blue/30 hover:decoration-accent-blue underline-offset-2"
        >
          {sym}
        </Link>
      );
    }
    const bold = part.match(/^<b>(.+?)<\/b>$/);
    if (bold) {
      return <strong key={i} className="text-text-primary font-semibold">{bold[1]}</strong>;
    }
    return <span key={i}>{part}</span>;
  });
}


// ── snapshot pills ───────────────────────────────────────────────────

function verdictTone(verdict: string | null | undefined) {
  if (!verdict) return null;
  const up = verdict.toUpperCase();
  if (up.includes("BUY"))  return { color: "text-accent-greenSoft", bg: "bg-accent-green/10 border-accent-green/30" };
  if (up.includes("SELL")) return { color: "text-accent-redSoft",   bg: "bg-accent-red/10 border-accent-red/30" };
  return { color: "text-text-secondary", bg: "bg-bg-card2 border-bg-borderHi" };
}

function macroIcon(v: string | null | undefined): typeof Wind {
  if (!v) return Wind;
  if (v === "tailwind")      return Sun;
  if (v === "mild_tailwind") return Wind;
  if (v === "headwind")      return Tornado;
  if (v === "mild_headwind") return CloudFog;
  return Wind;
}

function macroTone(v: string | null | undefined) {
  if (!v) return { color: "text-text-muted", bg: "bg-bg-card2 border-bg-borderHi" };
  if (v.includes("tailwind")) return { color: "text-accent-greenSoft", bg: "bg-accent-green/[0.06] border-accent-green/30" };
  if (v.includes("headwind")) return { color: "text-accent-redSoft",   bg: "bg-accent-red/[0.06] border-accent-red/30" };
  return { color: "text-text-secondary", bg: "bg-bg-card2 border-bg-borderHi" };
}

function bucketTone(bucket: BriefPick["bucket"]) {
  if (bucket === "promising") {
    return { color: "text-accent-amber",      bg: "bg-accent-amber/10 border-accent-amber/30", Icon: TrendingUp,    label: "Promising growth" };
  }
  if (bucket === "hype") {
    return { color: "text-accent-violet",     bg: "bg-accent-violet/10 border-accent-violet/40", Icon: AlertTriangle, label: "Hype watch" };
  }
  return { color: "text-accent-greenSoft",    bg: "bg-accent-green/10 border-accent-green/30", Icon: ShieldCheck,   label: "Stable growth" };
}

function bucketHeaderGradient(bucket: BriefPick["bucket"]): string {
  if (bucket === "promising") {
    return "radial-gradient(ellipse 60% 100% at 30% 0%, rgba(245, 158, 11, 0.10) 0%, transparent 70%)";
  }
  if (bucket === "hype") {
    return "radial-gradient(ellipse 60% 100% at 30% 0%, rgba(168, 85, 247, 0.12) 0%, transparent 70%)";
  }
  return "radial-gradient(ellipse 60% 100% at 30% 0%, rgba(34, 197, 94, 0.10) 0%, transparent 70%)";
}

function bubbleTone(score: number): { color: string; bg: string; label: string } {
  if (score >= 75) return { color: "text-accent-violet",   bg: "bg-accent-violet/15 border-accent-violet/50", label: "Extreme bubble" };
  if (score >= 65) return { color: "text-accent-amber",    bg: "bg-accent-amber/15 border-accent-amber/40",  label: "Elevated bubble" };
  if (score >= 45) return { color: "text-text-secondary",  bg: "bg-bg-card2 border-bg-borderHi",             label: "Rich-ish" };
  return                 { color: "text-accent-greenSoft", bg: "bg-accent-green/10 border-accent-green/30",  label: "Reasonable" };
}


// ── pick card ────────────────────────────────────────────────────────

function PickCard({ pick, index }: { pick: BriefPick; index: number }) {
  const snap = pick.snapshot || {};
  const bk = bucketTone(pick.bucket);
  const BkIcon = bk.Icon;
  const v = verdictTone(snap.verdict);
  const m = macroTone(snap.macro_verdict);
  const MacroIco = macroIcon(snap.macro_verdict);

  const dotsForScore = (n?: number | null) => {
    const s = n ?? 0;
    return (
      <span className="inline-flex items-center gap-[2px]" aria-label={`Score ${s}/5`}>
        {[1, 2, 3, 4, 5].map((i) => (
          <span
            key={i}
            className={cn(
              "h-1 rounded-full transition-all",
              i <= s ? "w-2.5 bg-accent-violet" : "w-1.5 bg-bg-border",
            )}
          />
        ))}
      </span>
    );
  };

  return (
    <article
      className={cn(
        "card-subtle p-5 overflow-hidden relative animate-rise",
        pick.bucket === "hype" && "border-l-2 border-l-accent-violet/60",
      )}
      style={{ animationDelay: `${index * 80}ms` }}
    >
      {/* Decorative gradient header — color tied to bucket */}
      <div
        className="absolute inset-x-0 top-0 h-24 pointer-events-none opacity-50"
        style={{ background: bucketHeaderGradient(pick.bucket) }}
      />

      <div className="relative">
        {/* Header row — symbol, name, bucket, link */}
        <header className="flex items-start justify-between gap-3 mb-3 flex-wrap">
          <div className="flex items-baseline gap-3 min-w-0">
            <span className="font-mono text-[10px] tracking-[0.22em] text-text-muted uppercase shrink-0">
              Pick {String(index + 1).padStart(2, "0")}
            </span>
            <Link
              href={`/deep-dive/${encodeURIComponent(pick.symbol)}`}
              className="group inline-flex items-baseline gap-2 hover:text-accent-blue transition-colors"
            >
              <span className="font-mono text-[22px] font-bold tabular-nums text-text-primary group-hover:text-accent-blue">
                ${pick.symbol}
              </span>
              <ArrowUpRight size={14} className="text-text-muted opacity-0 group-hover:opacity-80 transition-opacity" />
            </Link>
            {pick.name && (
              <span className="text-[12px] text-text-muted truncate" title={pick.name}>
                {pick.name}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className={cn("badge text-[10px] uppercase tracking-wider font-semibold inline-flex items-center gap-1", bk.bg, bk.color)}>
              <BkIcon size={10} />
              {bk.label}
            </span>
            {/* Profitability chip — independent of bucket, so users see e.g.
                "Promising · Profitable" (NVDA) vs "Promising · Burning cash" */}
            {pick.is_profitable && (
              <span className="badge text-[10px] uppercase tracking-wider font-semibold inline-flex items-center gap-1 bg-accent-blue/10 text-accent-blueSoft border-accent-blue/30">
                Profitable
              </span>
            )}
          </div>
        </header>

        {/* Angle row — small explainer of why it's here. If the pick surfaced
            from multiple chapters, list them all — that's a stronger signal. */}
        {(pick.chapter_headlines?.length ?? 0) > 0 && (
          <div className="text-[11px] text-text-muted flex items-baseline gap-2 mb-3 flex-wrap">
            <Compass size={11} className="shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              {pick.chapter_headlines.map((h, i) => (
                <span key={i} className="italic leading-snug">
                  {h}
                  {i < pick.chapter_headlines.length - 1 && (
                    <span className="text-text-dim mx-1.5">·</span>
                  )}
                </span>
              ))}
              {pick.chapter_headlines.length > 1 && (
                <span className="ml-2 text-[9px] uppercase tracking-wider text-accent-blue font-semibold">
                  Cross-chapter signal
                </span>
              )}
            </div>
          </div>
        )}

        {/* Snapshot pills */}
        <div className="flex flex-wrap items-center gap-1.5 mb-4">
          {snap.headline_metric && (
            <span className="badge text-[10px] bg-bg-base text-text-primary border-bg-borderHi font-mono tabular-nums">
              {snap.headline_metric}
            </span>
          )}
          {v && snap.verdict && (
            <span className={cn("badge text-[10px] uppercase tracking-wider font-semibold", v.bg, v.color)}>
              {snap.verdict}
            </span>
          )}
          {snap.fundamental_archetype && (
            <span className="badge text-[10px] bg-accent-violet/10 text-accent-violet border-accent-violet/30 inline-flex items-center gap-1">
              <Gauge size={10} />
              {snap.fundamental_archetype}
              {snap.fundamental_score != null && (
                <span className="ml-1">{dotsForScore(snap.fundamental_score)}</span>
              )}
            </span>
          )}
          {snap.macro_verdict && (
            <span className={cn("badge text-[10px] inline-flex items-center gap-1 uppercase tracking-wider", m.bg, m.color)}>
              <MacroIco size={10} />
              {snap.macro_verdict.replace("_", " ")}
            </span>
          )}
          {snap.bubble_score != null && (() => {
            const bt = bubbleTone(snap.bubble_score);
            return (
              <span
                className={cn("badge text-[10px] inline-flex items-center gap-1 font-mono tabular-nums", bt.bg, bt.color)}
                title={snap.bubble_label ? `Bubble: ${snap.bubble_label}` : bt.label}
              >
                Bubble {snap.bubble_score.toFixed(0)}
              </span>
            );
          })()}
          {snap.price != null && (
            <span className="badge text-[10px] bg-bg-base text-text-secondary border-bg-borderHi font-mono tabular-nums ml-auto">
              ${snap.price.toFixed(2)}
              {snap.change_pct != null && (
                <span className={cn(
                  "ml-1",
                  snap.change_pct >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft",
                )}>
                  {snap.change_pct >= 0 ? "+" : ""}{snap.change_pct.toFixed(1)}%
                </span>
              )}
            </span>
          )}
        </div>

        {/* The story */}
        <p className="text-[14px] leading-[1.65] text-text-secondary mb-4">
          {renderNarrative(pick.narrative)}
        </p>

        {/* Web-validated finding — surfaces what Claude found checking the
            last 7 days with WebSearch/WebFetch. Color-coded by verdict so
            the user sees at a glance whether the thesis still holds. */}
        {(() => {
          const wv = (pick.snapshot as { full_signals?: { web_validation?: { verdict: string; summary?: string; web_sources?: string[] } } })
            ?.full_signals?.web_validation;
          if (!wv || !wv.summary) return null;
          const tone =
            wv.verdict === "invalidates"   ? "bg-accent-red/[0.07] border-accent-red/40 text-accent-redSoft" :
            wv.verdict === "flags_concern" ? "bg-accent-amber/[0.07] border-accent-amber/40 text-accent-amber" :
                                              "bg-accent-blue/[0.05] border-accent-blue/30 text-accent-blueSoft";
          const label =
            wv.verdict === "invalidates"   ? "Disqualifying news" :
            wv.verdict === "flags_concern" ? "Flag from web check" :
                                              "Web check confirms";
          return (
            <div className={cn("rounded-md border p-2.5 mb-4 text-[12px] leading-snug", tone)}>
              <div className="font-mono text-[9px] tracking-[0.22em] uppercase opacity-70 mb-1">
                {label}
              </div>
              <div className="text-text-primary">{wv.summary}</div>
              {wv.web_sources && wv.web_sources.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1.5 text-[10px] opacity-80">
                  {wv.web_sources.slice(0, 3).map((u, i) => {
                    let host = u;
                    try { host = new URL(u).hostname.replace(/^www\./, ""); } catch {/* keep raw */}
                    return (
                      <a key={i} href={u} target="_blank" rel="noopener noreferrer"
                         className="underline decoration-current/40 hover:decoration-current">
                        {host}
                      </a>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })()}

        {/* Why now */}
        {pick.why_now && pick.why_now.length > 0 && (
          <div className="pt-3 border-t border-bg-divider">
            <div className="font-mono text-[10px] tracking-[0.22em] uppercase text-text-muted mb-2">
              Why now
            </div>
            <ul className="space-y-1">
              {pick.why_now.map((bullet, i) => (
                <li key={i} className="text-[12px] text-text-secondary leading-snug flex items-start gap-2">
                  <span className="text-text-muted mt-0.5">·</span>
                  <span>{bullet}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </article>
  );
}


// ── hype watch card (compact, muted) ─────────────────────────────────

function HypeWatchCard({ pick, index }: { pick: BriefPick; index: number }) {
  const snap = pick.snapshot || {};
  const bubble = snap.bubble_score;
  return (
    <Link
      href={`/deep-dive/${encodeURIComponent(pick.symbol)}`}
      className="card-subtle p-3 hover:border-bg-borderHi transition-all hover:translate-y-[-1px] block animate-rise border-l-2 border-l-accent-amber/40"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      <div className="flex items-baseline justify-between gap-2 mb-1.5">
        <span className="font-mono text-[15px] font-bold tabular-nums text-text-primary group-hover:text-accent-blue">
          ${pick.symbol}
        </span>
        <span className="badge text-[9px] uppercase tracking-wider bg-accent-amber/10 text-accent-amber border-accent-amber/40">
          Hype
        </span>
      </div>
      {pick.name && (
        <div className="text-[10px] text-text-muted truncate mb-1.5" title={pick.name}>
          {pick.name}
        </div>
      )}
      {bubble != null && (
        <div className="flex items-center gap-1.5 text-[10px] mb-1.5">
          <span className="text-text-muted">Bubble score:</span>
          <span className={cn(
            "font-mono tabular-nums font-semibold",
            bubble >= 75 ? "text-accent-redSoft" : bubble >= 65 ? "text-accent-amber" : "text-text-secondary",
          )}>
            {bubble.toFixed(0)}
            {snap.bubble_label && <span className="text-text-muted ml-1 font-normal">· {snap.bubble_label}</span>}
          </span>
        </div>
      )}
      {snap.headline_metric && (
        <div className="text-[10px] text-text-secondary leading-snug line-clamp-2">
          {snap.headline_metric}
        </div>
      )}
      {pick.narrative && (
        <div className="text-[10px] text-text-muted leading-snug line-clamp-3 mt-1.5 pt-1.5 border-t border-bg-divider">
          {renderNarrative(pick.narrative)}
        </div>
      )}
    </Link>
  );
}


// ── investment angles chip row ───────────────────────────────────────

function LensBanner({ lens, fallbackUsed }: { lens: BriefLens; fallbackUsed: boolean }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const convergence = lens.convergence ?? [];

  const alignmentTone = (a: string) =>
    a === "supports" ? "text-accent-greenSoft border-accent-green/30 bg-accent-green/5" :
    a === "fights"   ? "text-accent-redSoft   border-accent-red/30   bg-accent-red/5"   :
                       "text-text-muted       border-bg-borderHi      bg-bg-card/40";

  return (
    <div className="card p-5 mb-4 border-l-2 border-accent-blue/60">
      <div className="flex items-baseline gap-3 mb-2">
        <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-accent-blue">
          Today's lens
        </span>
        {fallbackUsed && (
          <span className="text-[10px] text-accent-amber font-mono">
            rule-based fallback (Claude unavailable)
          </span>
        )}
      </div>
      {lens.rationale && (
        <p className="text-[14px] text-text-primary leading-relaxed mb-3">
          {lens.rationale}
        </p>
      )}
      {lens.query && (
        <div className="rounded-md bg-bg-base/40 border border-bg-border px-3 py-2 mb-3">
          <div className="font-mono text-[9px] uppercase tracking-wider text-text-muted mb-1">
            Search query the engine ran
          </div>
          <p className="text-[12px] text-text-secondary italic leading-snug">"{lens.query}"</p>
        </div>
      )}
      {convergence.length > 0 && (
        <div>
          <div className="font-mono text-[9px] uppercase tracking-wider text-text-muted mb-2">
            Convergence — sectors where multiple lenses agreed
          </div>
          <div className="flex flex-wrap gap-2">
            {convergence.map((c, i) => {
              const isOpen = expanded === c.sector;
              return (
                <div key={i} className="relative">
                  <button
                    onClick={() => setExpanded(isOpen ? null : c.sector)}
                    className={cn(
                      "text-[11px] px-2.5 py-1 rounded-md border transition-colors",
                      alignmentTone(c.macro_alignment ?? "neutral"),
                      isOpen && "ring-1 ring-accent-blue/40",
                    )}
                  >
                    <span className="font-semibold">{c.sector}</span>
                    <span className="ml-1.5 opacity-70">
                      · {(c.lenses ?? []).length} lens{(c.lenses ?? []).length === 1 ? "" : "es"}
                    </span>
                    <span className="ml-1.5 font-mono opacity-60">
                      {c.macro_alignment ?? "neutral"}
                    </span>
                  </button>
                  {isOpen && (
                    <div className="absolute z-10 mt-1 left-0 w-72 card p-3 shadow-2xl shadow-black/60">
                      <div className="text-[11px] text-text-secondary mb-2">{c.evidence}</div>
                      <div className="font-mono text-[9px] uppercase tracking-wider text-text-muted mb-1">
                        Lenses
                      </div>
                      <ul className="space-y-0.5">
                        {(c.lenses ?? []).map((l, j) => (
                          <li key={j} className="text-[11px] text-text-secondary">{l}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}


function AnglesRow({ angles }: { angles: BriefInvestmentAngle[] }) {
  if (!angles || angles.length === 0) return null;
  return (
    <div className="card-subtle p-4 mb-8">
      <div className="font-mono text-[10px] tracking-[0.22em] uppercase text-text-muted mb-2">
        Today's investment angles
      </div>
      <ul className="space-y-1.5">
        {angles.map((a, i) => (
          <li key={i} className="text-[13px] flex items-start gap-2">
            <span className="font-mono text-[10px] text-accent-blue mt-1 shrink-0">{String(i + 1).padStart(2, "0")}</span>
            <span>
              <span className="font-semibold text-text-primary">{a.label}.</span>{" "}
              <span className="text-text-secondary">{a.rationale}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}


// ── market story block (headline + paragraphs) ───────────────────────

function MarketStoryBlock({ story, regime }: { story: BriefMarketStory; regime: string }) {
  return (
    <section className="mb-8 animate-rise">
      <div className="flex items-baseline gap-3 mb-3">
        <span className="font-mono text-[10px] tracking-[0.22em] text-text-muted uppercase">
          Today's regime
        </span>
        <span className={cn(
          "badge text-[10px]",
          regime.toLowerCase().includes("volatil")   ? "badge-amber" :
          regime.toLowerCase().includes("recession") ? "badge-red" :
          regime.toLowerCase().includes("calm")      ? "badge-green" :
                                                       "badge-blue",
        )}>
          {regime}
        </span>
      </div>

      {/* Editorial headline */}
      <h1 className="font-display text-[32px] sm:text-[40px] font-semibold leading-[1.1] tracking-tight text-text-primary mb-5 max-w-4xl">
        {story.headline}
      </h1>

      {/* Paragraphs — drop-cap on the first one */}
      {story.paragraphs.map((p, i) => (
        <p
          key={i}
          className={cn(
            "text-[15px] leading-[1.75] text-text-secondary max-w-3xl mb-4",
            i === 0 && "first-letter:text-[44px] first-letter:font-semibold first-letter:font-display first-letter:text-accent-blueSoft first-letter:float-left first-letter:mr-2 first-letter:leading-[0.85] first-letter:mt-1",
          )}
        >
          {renderNarrative(p)}
        </p>
      ))}
    </section>
  );
}


// ── ask AI section (preserved from v1) ────────────────────────────────

function AskAI() {
  const [text, setText] = useState("");

  const mut = useMutation({
    mutationFn: (q: string) => contextSearchApi.search(q, 30),
  });
  const result = mut.data as ContextSearchResponse | undefined;

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim() || mut.isPending) return;
    mut.mutate(text.trim());
  };

  return (
    <section className="mt-12 pt-10 border-t border-bg-divider">
      <header className="mb-4">
        <div className="font-mono text-[10px] tracking-[0.22em] text-text-muted uppercase mb-1">
          Ask AI
        </div>
        <h2 className="font-display text-[22px] font-semibold tracking-tight text-text-primary">
          Unlock more of the narrative
        </h2>
        <p className="text-[13px] text-text-secondary mt-1">
          Free-text query — Claude expands it into themes, fans out across the graph + news,
          returns ranked stocks with reasoning.
        </p>
      </header>

      <form onSubmit={onSubmit} className="card p-3 mb-5">
        <div className="flex items-start gap-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. 'who benefits if China cuts copper exports?' or 'which AI capex names trade at less than 30x?'"
            rows={2}
            className="flex-1 bg-transparent text-[13px] text-text-primary placeholder:text-text-dim resize-none focus:outline-none leading-relaxed"
          />
          <button
            type="submit"
            disabled={!text.trim() || mut.isPending}
            className={cn(
              "shrink-0 inline-flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-md border transition-colors whitespace-nowrap",
              mut.isPending || !text.trim()
                ? "bg-bg-card2 text-text-muted border-bg-border cursor-not-allowed"
                : "bg-accent-blue/10 hover:bg-accent-blue/20 text-accent-blue border-accent-blue/30",
            )}
          >
            {mut.isPending ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            {mut.isPending ? "Thinking" : "Ask"}
          </button>
        </div>
      </form>

      {mut.isError && (
        <div className="text-[12px] text-accent-redSoft bg-accent-red/5 border border-accent-red/30 rounded-md p-3 mb-4">
          {(mut.error as Error).message}
        </div>
      )}

      {result && <AskResult result={result} />}
    </section>
  );
}

function AskResult({ result }: { result: ContextSearchResponse }) {
  const stocks = (result.stocks ?? []).slice(0, 12);
  const themes = result.expansion?.themes ?? [];
  const commodities = result.expansion?.commodities ?? [];

  return (
    <div className="space-y-4 animate-rise">
      {(themes.length > 0 || commodities.length > 0) && (
        <div className="flex flex-wrap gap-1.5">
          {themes.map((t) => (
            <span key={`th-${t}`} className="badge badge-blue text-[10px]">
              {t}
            </span>
          ))}
          {commodities.map((c) => (
            <span key={`co-${c.code}`} className="badge badge-amber text-[10px]">
              {c.code} {c.direction === "up" ? "↑" : "↓"}
            </span>
          ))}
        </div>
      )}

      {stocks.length === 0 ? (
        <div className="text-[13px] text-text-muted italic">
          No stocks scored above the noise floor for this query.
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-2">
          {stocks.map((s: ContextSearchStock) => (
            <Link
              key={s.symbol}
              href={`/deep-dive/${encodeURIComponent(s.symbol)}`}
              className="card p-3 hover:border-bg-borderHi transition-colors group"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-mono text-[14px] font-semibold tabular-nums text-accent-blueSoft">
                  {s.symbol}
                </span>
                <span className={cn(
                  "font-mono text-[12px] tabular-nums",
                  s.polarity >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft",
                )}>
                  {s.composite_score.toFixed(2)}
                </span>
              </div>
              {s.name && (
                <div className="text-[11px] text-text-muted truncate mt-0.5">{s.name}</div>
              )}
              {s.reasoning && s.reasoning.length > 0 && (
                <div className="text-[11px] text-text-secondary mt-1.5 line-clamp-2 leading-snug">
                  {s.reasoning.join(" · ")}
                </div>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}


// ── page ─────────────────────────────────────────────────────────────

export default function BriefPage() {
  const qc = useQueryClient();
  // Sector-diversity toggle — when ON, the picker caps actionable picks at
  // max 2 per sector (forces diversity). Default OFF: top-by-score, no
  // sector cap. The queryKey + cache key both include the flag so the on/off
  // variants don't poison each other.
  const [diversity, setDiversity] = useState(false);
  // queryKey bumped to "v4" — server now returns status: "computing" on cold
  // cache and we auto-poll until it's "ready". Older client caches without
  // the status field should miss + re-fetch the new shape.
  const { data, isLoading, error, isFetching } = useQuery<Brief>({
    queryKey: ["brief", "v4", diversity ? "div" : "nodiv"],
    queryFn: () => briefApi.get({ diversity }),
    staleTime: 30 * 60 * 1000,
    // Auto-poll every 10s while the backend is still generating. The route
    // returns a "computing" stub instantly + kicks generation in a background
    // thread; next poll picks up the populated cache. Without this the user
    // sees an empty brief and has to manually refresh.
    refetchInterval: (q) => ((q.state.data as { status?: string } | undefined)?.status === "computing" ? 10000 : false),
  });

  const isComputing = (data as { status?: string } | undefined)?.status === "computing";
  // Progress fields from the durable background-jobs tracker. Only populated
  // while status === "computing"; absent on the legacy stub and on the
  // "ready" payload.
  const currentPhase = (data as Brief | undefined)?.current_phase ?? null;
  const progressPct  = (data as Brief | undefined)?.progress_pct ?? 0;
  const elapsedS     = (data as Brief | undefined)?.elapsed_s ?? 0;

  const [forceRefreshing, setForceRefreshing] = useState(false);
  const forceRefresh = async () => {
    setForceRefreshing(true);
    try {
      const fresh = await briefApi.get({ force: true, diversity });
      // Write to the SAME query key the page reads from. (Previously this
      // wrote to "v3" while useQuery reads "v4", so the fresh data landed
      // in a slot nothing renders and the page appeared not to refresh.)
      qc.setQueryData(["brief", "v4", diversity ? "div" : "nodiv"], fresh);
    } finally {
      setForceRefreshing(false);
    }
  };

  // Cancel-and-restart: wipes the in-flight job row + the per-phase
  // checkpoints, then refetches so the API kicks a fresh background build
  // and returns a new computing stub. Doesn't kill the Claude subprocess
  // (Python threads can't be force-cancelled) — but the user immediately
  // gets a fresh progress meter instead of being stuck on a hung phase.
  const [restarting, setRestarting] = useState(false);
  const cancelAndRestart = async () => {
    setRestarting(true);
    try {
      await briefApi.restart({ diversity });
      await qc.invalidateQueries({ queryKey: ["brief", "v4", diversity ? "div" : "nodiv"] });
    } finally {
      setRestarting(false);
    }
  };

  return (
    <div>
      <PageHeader
        icon={BookOpen}
        title="The Brief"
        subtitle="Market story → graph + online discovery → deep-dived picks. Written by Claude."
        accent="text-accent-blue"
        iconBg="bg-accent-blue/10"
        trailing={
          <div className="flex items-center gap-2">
            <FreshnessPill iso={data?.generated_at} />
            {/* Sector-diversity toggle */}
            <button
              onClick={() => setDiversity((v) => !v)}
              disabled={isFetching || forceRefreshing}
              title={diversity
                ? "Diversity ON — actionable picks capped at max 2 per sector."
                : "Diversity OFF (default) — actionable picks chosen by score only, no sector cap."}
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-medium transition-colors border",
                diversity
                  ? "bg-accent-blue/10 text-accent-blueSoft border-accent-blue/40 hover:bg-accent-blue/20"
                  : "bg-bg-card text-text-secondary border-bg-borderHi hover:text-text-primary hover:bg-bg-card2",
                "disabled:opacity-50 disabled:cursor-not-allowed",
              )}
            >
              <span
                className={cn(
                  "w-1.5 h-1.5 rounded-full",
                  diversity ? "bg-accent-blueSoft" : "bg-text-dim",
                )}
              />
              Diversity: <span className="font-mono">{diversity ? "ON" : "OFF"}</span>
            </button>
            <button
              onClick={forceRefresh}
              disabled={isFetching || forceRefreshing}
              title="Bypass cache and regenerate (60-90s — runs full pipeline + Claude)"
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
        }
      />

      {/* Loading — either initial fetch OR cold cache (server returned
          status:"computing" while Claude generates in the background). */}
      {(isLoading || isComputing) && (!data || isComputing) && (
        <div className="space-y-6">
          {isComputing && (
            <div className="card p-4 border-l-4 border-accent-blue/40">
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 mt-1.5 rounded-full bg-accent-blue animate-pulse shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[13px] text-text-primary font-semibold">
                      Generating today's brief
                      {currentPhase ? (
                        <span className="ml-2 font-mono text-[10px] tracking-[0.18em] uppercase text-accent-blueSoft">
                          · {currentPhase}
                        </span>
                      ) : null}
                    </p>
                    <button
                      onClick={cancelAndRestart}
                      disabled={restarting}
                      title="Cancel the current generation, wipe phase checkpoints, and start fresh."
                      className={cn(
                        "flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-medium transition-colors",
                        "bg-bg-card hover:bg-bg-card2 border border-bg-borderHi text-text-secondary hover:text-text-primary",
                        "disabled:opacity-50 disabled:cursor-not-allowed shrink-0",
                      )}
                    >
                      <X size={10} />
                      {restarting ? "Restarting..." : "Cancel and restart"}
                    </button>
                  </div>
                  <p className="text-[11px] text-text-muted mt-0.5 leading-relaxed">
                    Claude is composing the lens, hydrating picks, validating against the web, and writing the narrative.
                    This typically takes 1-3 minutes on a cold cache — polling every 10s, will update automatically.
                  </p>
                  {/* Progress bar — width driven by backend's progress_pct */}
                  <div className="mt-3 h-1 bg-bg-card2 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-accent-blue transition-[width] duration-700 ease-out"
                      style={{ width: `${Math.max(2, Math.min(100, progressPct ?? 0))}%` }}
                    />
                  </div>
                  <div className="mt-1.5 flex items-center justify-between text-[10px] font-mono text-text-muted">
                    <span>{progressPct != null ? `${progressPct}%` : "starting..."}</span>
                    <span>
                      {elapsedS != null && elapsedS > 0
                        ? `${Math.floor(elapsedS / 60)}m ${elapsedS % 60}s elapsed`
                        : ""}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}
          <div className="space-y-3">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-4/6" />
          </div>
          <Skeleton className="h-24 w-full" />
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="card p-6 border-l-4 border-accent-red/40">
          <p className="text-accent-redSoft text-[13px]">Failed to load the brief.</p>
          <p className="text-text-muted text-[11px] mt-1">{(error as Error).message}</p>
        </div>
      )}

      {/* Content — only render once we have a real "ready" brief */}
      {data && !isComputing && (
        <>
          {/* Defensive guard: if backend serves the legacy v1/v2 shape
              (intro + chapters but no market_story), render an upgrade notice
              and bail out instead of throwing. Hitting Regenerate will produce
              the new shape. */}
          {!data.market_story ? (
            <div className="card p-6 border-l-4 border-accent-amber/40">
              <p className="text-accent-amber font-semibold mb-1">Brief schema updated.</p>
              <p className="text-text-secondary text-sm">
                The Brief pipeline was upgraded to a 3-bucket (stable / promising / hype)
                story format. Your cached brief is in the old shape. Click <b>Regenerate</b>
                above to produce one in the new format (~60-120s).
              </p>
            </div>
          ) : (
            <>
          {/* Market story */}
          <MarketStoryBlock story={data.market_story} regime={data.regime} />

          {/* Investment angles chip block */}
          <AnglesRow angles={data.market_story.investment_angles ?? []} />

          {/* Today's lens — Claude-written context_search query + convergence chips */}
          {data.lens ? (
            <LensBanner lens={data.lens} fallbackUsed={data.meta?.lens_fallback_used ?? false} />
          ) : data.chapters && data.chapters.length > 0 ? (
            <div className="card-subtle p-3 mb-4">
              <div className="font-mono text-[10px] tracking-[0.22em] uppercase text-text-muted mb-2">
                Today's lens · rule-based fallback ({data.chapters.length} chapters)
              </div>
              <ul className="space-y-1.5">
                {data.chapters.map((ch: BriefChapter, i) => {
                  const sourceTone =
                    ch.source === "disruption"   ? "text-accent-amber" :
                    ch.source === "geopolitical" ? "text-accent-red"   :
                                                   "text-accent-blue";
                  const sourceLabel =
                    ch.source === "disruption"   ? "THEME" :
                    ch.source === "geopolitical" ? "GEO"   :
                                                   "SECTOR";
                  return (
                    <li key={ch.id} className="flex items-baseline gap-2 text-[12px]">
                      <span className={cn("font-mono text-[9px] uppercase tracking-wider shrink-0 w-12", sourceTone)}>
                        {String(i + 1).padStart(2, "0")} {sourceLabel}
                      </span>
                      <span className="text-text-secondary leading-snug">{ch.headline}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}

          {/* Picks header */}
          <div className="flex items-baseline justify-between mb-4 flex-wrap gap-2">
            <div className="flex items-baseline gap-3">
              <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-text-muted">
                Actionable picks
              </span>
              <span className="text-[11px] text-text-muted">
                {data.picks.length} stocks · {data.meta.candidates_considered} candidates scanned
              </span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {/* Bucket counts — only the 2 actionable buckets here */}
              {(["stable", "promising"] as const).map((b) => {
                const n = data.picks.filter((p) => p.bucket === b).length;
                if (n === 0) return null;
                const tone = b === "promising"  ? "badge text-[10px] bg-accent-amber/10 text-accent-amber border-accent-amber/30"
                          :                       "badge text-[10px] bg-accent-green/10 text-accent-greenSoft border-accent-green/30";
                const label = b.charAt(0).toUpperCase() + b.slice(1);
                return (
                  <span key={b} className={tone}>
                    {n} {label}
                  </span>
                );
              })}
              {/* Profitability count — independent of bucket */}
              {(() => {
                const profitableCount = data.picks.filter((p) => p.is_profitable).length;
                return profitableCount > 0 ? (
                  <span className="badge text-[10px] bg-accent-blue/10 text-accent-blueSoft border-accent-blue/30">
                    {profitableCount} profitable
                  </span>
                ) : null;
              })()}
            </div>
          </div>

          {/* Pick cards */}
          {data.picks.length === 0 ? (
            <div className="card p-6 text-text-muted text-[13px] italic">
              No stocks made the cut today — both stable and promising buckets came up empty
              after fundamentals filtering. This usually means the candidate pool needs more
              cached fundamental data.
            </div>
          ) : (
            <div className="space-y-4 mb-10">
              {data.picks.map((p, i) => (
                <PickCard key={p.symbol} pick={p} index={i} />
              ))}
            </div>
          )}

          {/* Hype watch — separate strip, clearly labeled, muted styling */}
          {(data.hype_watch?.length ?? 0) > 0 && (
            <section className="mb-10 mt-8 pt-6 border-t border-bg-divider animate-rise">
              <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
                <div className="flex items-baseline gap-3">
                  <AlertTriangle size={12} className="text-accent-amber translate-y-[2px]" />
                  <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-accent-amber">
                    Hype watch · don't chase
                  </span>
                </div>
                <span className="text-[10px] text-text-muted">
                  {data.hype_watch!.length} names where price has run ahead of fundamentals
                </span>
              </div>
              <p className="text-[12px] text-text-muted mb-3 max-w-3xl leading-relaxed">
                These aren't recommendations. They're momentum names with elevated bubble scores
                or rich multiples — surfaced so you know what's getting bid up, not what to buy.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 opacity-90">
                {data.hype_watch!.map((p, i) => (
                  <HypeWatchCard key={p.symbol} pick={p} index={i} />
                ))}
              </div>
            </section>
          )}

          {/* Closing */}
          {data.closing && (
            <section className="mb-8 animate-rise">
              <div className="font-mono text-[10px] tracking-[0.22em] uppercase text-text-muted mb-3">
                Closing
              </div>
              <p className="text-[14px] leading-[1.7] text-text-secondary max-w-3xl">
                {renderNarrative(data.closing)}
              </p>
            </section>
          )}

          {/* Ask AI */}
          <AskAI />

          {/* Footer note */}
          <footer className="mt-12 pt-6 border-t border-bg-divider text-[11px] text-text-muted leading-relaxed space-y-2">
            <p>
              <span className="text-text-secondary font-semibold">Pipeline.</span>{" "}
              <span className="text-text-primary">Read</span> the full Market Pulse —
              regime, KPIs, yield curve, breadth, top movers, price flow (1M + 3M),
              13F sector tape, congress sector tape, news, disruption themes,
              geopolitical events, upcoming catalysts. {" "}
              <span className="text-text-primary">Claude</span> reads all of it and
              writes one search lens: 1-3 convergence sectors plus a fusion query.{" "}
              <span className="text-text-primary">context_search</span> runs that
              lens per-anchor (keyword expansion + sector graph + news) and returns
              a ~30-40 stock candidate pool.
            </p>
            <p>
              <span className="text-text-primary">Light fundamentals</span> (rev
              growth · EPS growth · margin · PEG) classify each candidate into{" "}
              <span className="badge text-[9px] bg-accent-green/10 text-accent-greenSoft border-accent-green/30">stable</span>,{" "}
              <span className="badge text-[9px] bg-accent-amber/10 text-accent-amber border-accent-amber/30">promising</span>, or{" "}
              <span className="badge text-[9px] bg-accent-violet/10 text-accent-violet border-accent-violet/40">hype</span>.
              We pick the top 2 of each.
            </p>
            <p>
              For each of the 6 finalists we pull the{" "}
              <span className="text-text-primary">full deep-dive enrichment</span>
              {" "}— co-holders, supplier / customer / substitute graph, options
              flow, news sentiment, upcoming catalysts, peer valuation, bull /
              risk theses, fundamental pillars, earnings beat-miss pattern, bubble
              breakdown, smart-money tape (institutional + insider + congress),
              trade plan, benchmarks vs SPY / sector, signal evidence (per-signal
              historical win rate), plus sector-specific signals (backlog for
              defense, litigation for IP, patents for pharma, exec changes from
              8-Ks, FDA catalysts).
            </p>
            <p>
              Then{" "}
              <span className="text-text-primary">Claude validates each pick on the live web</span>
              {" "}(last 7 days only) — confirms, flags a concern, or invalidates.{" "}
              <span className="text-text-primary">Bucket-aware narration</span>{" "}
              writes the brief: stable = confident + durable, promising = optimistic
              with eyes open, hype = skeptical + warning. The narrative cites the
              lens and the convergence sectors explicitly, then ties every pick back
              to specific numbers in its full_signals block.
            </p>
            <p className="text-text-muted">
              Click any ticker to drill in. Hype picks come with a warning, not a buy.
            </p>
          </footer>
            </>
          )}
        </>
      )}
    </div>
  );
}
