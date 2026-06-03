"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CalendarClock, CheckCircle2, MinusCircle, XCircle, Info,
  TrendingUp, TrendingDown, ExternalLink,
} from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import type {
  PreEarningsSetup, PreEarningsSignal, PreEarningsVerdict, PreEarningsNewsItem,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

type Props = { symbol: string };

function verdictStyle(v: PreEarningsVerdict): { label: string; tone: string; ring: string; bar: string } {
  switch (v) {
    case "pricing_in_beat":
      return { label: "PRICING IN A BEAT", tone: "text-accent-greenSoft", ring: "border-accent-green/40", bar: "bg-gradient-to-r from-accent-green/60 to-accent-greenSoft" };
    case "leaning_bullish":
      return { label: "LEANING BULLISH",    tone: "text-accent-greenSoft", ring: "border-accent-green/25", bar: "bg-gradient-to-r from-accent-green/30 to-accent-green/60" };
    case "mixed":
      return { label: "MIXED",              tone: "text-text-muted",       ring: "border-bg-borderHi",     bar: "bg-bg-borderHi" };
    case "leaning_bearish":
      return { label: "LEANING BEARISH",    tone: "text-accent-redSoft",   ring: "border-accent-red/25",   bar: "bg-gradient-to-r from-accent-red/30 to-accent-red/60" };
    case "pricing_in_miss":
      return { label: "PRICING IN A MISS",  tone: "text-accent-redSoft",   ring: "border-accent-red/40",   bar: "bg-gradient-to-r from-accent-red/60 to-accent-redSoft" };
    case "no_earnings_imminent":
      return { label: "NO EARNINGS WITHIN 45D", tone: "text-text-muted",   ring: "border-bg-borderHi",     bar: "bg-bg-borderHi" };
    default:
      return { label: "INSUFFICIENT DATA",  tone: "text-text-muted",       ring: "border-bg-borderHi",     bar: "bg-bg-borderHi" };
  }
}

function signalIcon(tone: string) {
  if (tone === "positive") return <CheckCircle2 size={12} className="text-accent-greenSoft shrink-0" />;
  if (tone === "negative") return <XCircle       size={12} className="text-accent-redSoft   shrink-0" />;
  return <MinusCircle size={12} className="text-text-muted shrink-0" />;
}

export function PreEarningsSetupCard({ symbol }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["pre-earnings-setup", symbol],
    queryFn: () => stocksApi.preEarningsSetup(symbol),
    staleTime: 30 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) return <Skeleton className="h-48 w-full" />;
  if (!data) return null;

  const style = verdictStyle(data.verdict);
  const isActionable = data.verdict !== "no_earnings_imminent" && data.verdict !== "insufficient_data";
  // Score is -100..+100 → map to a 0..100 width centered on 50
  const barWidth = Math.min(100, Math.max(0, 50 + data.score / 2));

  return (
    <section className={cn("card p-5 border", style.ring)}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <CalendarClock size={16} className={style.tone} />
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-[13px] font-semibold text-text-primary">Pre-earnings Setup</h3>
              <span className={cn("text-[10px] font-mono tracking-[0.15em]", style.tone)}>
                {style.label}
              </span>
            </div>
            <p className="text-[11px] text-text-muted mt-0.5 leading-snug">{data.headline}</p>
          </div>
        </div>
        {data.days_to_next_earnings != null && (
          <div className="text-right shrink-0">
            <div className="text-[10px] uppercase tracking-wider text-text-muted">Next earnings</div>
            <div className="text-[13px] font-semibold text-text-primary tabular-nums">
              {data.days_to_next_earnings === 0 ? "today" : `${data.days_to_next_earnings}d`}
            </div>
            {data.next_earnings_date && (
              <div className="text-[10px] text-text-muted tabular-nums">{data.next_earnings_date}</div>
            )}
          </div>
        )}
      </div>

      {/* Composite score bar (only for actionable verdicts) */}
      {isActionable && (
        <div className="relative h-2 bg-bg-base rounded-full mb-4">
          <div className="absolute inset-y-0 left-1/2 w-px bg-bg-borderHi" />
          <div
            className={cn("absolute h-2 rounded-full transition-all duration-500", style.bar)}
            style={{ width: `${barWidth}%`, left: data.score >= 0 ? "50%" : "auto", right: data.score < 0 ? "50%" : "auto" }}
          />
        </div>
      )}

      {/* Per-signal breakdown */}
      {data.signals.length > 0 && (
        <div className="space-y-1.5 mb-3">
          {data.signals.map((s: PreEarningsSignal, i) => (
            <div key={i} className="flex items-center gap-2.5 text-[12px]">
              {signalIcon(s.tone)}
              <span className="text-text-muted w-32 shrink-0">{s.label}</span>
              <span
                className={cn(
                  "tabular-nums",
                  s.tone === "positive" && "text-accent-greenSoft",
                  s.tone === "negative" && "text-accent-redSoft",
                  s.tone === "neutral"  && "text-text-secondary",
                )}
              >
                {s.value}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Recent positive / negative news that COULD inform the print */}
      {(data.recent_news?.bullish?.length || data.recent_news?.bearish?.length) ? (
        <div className="mb-3 pt-3 border-t border-bg-border">
          <div className="flex items-baseline justify-between mb-2">
            <div className="font-mono text-[9px] uppercase tracking-wider text-text-muted">
              Recent news context
            </div>
            {data.recent_news?.net_sentiment && (
              <div className="text-[10px] text-text-muted">
                net 14d: <span className={cn(
                  data.recent_news.net_sentiment === "bullish" && "text-accent-greenSoft",
                  data.recent_news.net_sentiment === "bearish" && "text-accent-redSoft",
                  data.recent_news.net_sentiment === "mixed" && "text-text-secondary",
                )}>{data.recent_news.net_sentiment}</span>
              </div>
            )}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <NewsColumn
              tone="bullish"
              items={data.recent_news?.bullish ?? []}
              label="Recent positive headlines"
            />
            <NewsColumn
              tone="bearish"
              items={data.recent_news?.bearish ?? []}
              label="Recent negative headlines"
            />
          </div>
          {data.recent_news?.source_warning && (
            <p className="text-[10px] text-accent-amber mt-2">{data.recent_news.source_warning}</p>
          )}
        </div>
      ) : null}

      {/* Honesty footer */}
      <div className="flex items-start gap-1.5 pt-3 border-t border-bg-border text-[10px] text-text-muted leading-relaxed">
        <Info size={10} className="shrink-0 mt-0.5" />
        <p>
          {data.disclaimer ||
            "Composite view of market positioning into earnings. NOT an insider-trading detector."}
          {" "}Recent headlines are sentiment-tagged at fetch time — they're context, not causation.
        </p>
      </div>
    </section>
  );
}


function categoryPill(cat: string) {
  const map: Record<string, { label: string; cls: string }> = {
    earnings_preview:  { label: "PREVIEW",  cls: "bg-accent-blue/15   text-accent-blueSoft   border-accent-blue/30" },
    channel_check:     { label: "CHANNEL",  cls: "bg-accent-cyan/15   text-accent-cyan       border-accent-cyan/30" },
    analyst_revision:  { label: "ANALYST",  cls: "bg-accent-violet/15 text-accent-violet     border-accent-violet/30" },
    product_news:      { label: "PRODUCT",  cls: "bg-accent-green/15  text-accent-greenSoft  border-accent-green/30" },
    legal:             { label: "LEGAL",    cls: "bg-accent-red/15    text-accent-redSoft    border-accent-red/30" },
    merger:            { label: "M&A",      cls: "bg-accent-amber/15  text-accent-amber      border-accent-amber/30" },
  };
  const meta = map[cat];
  if (!meta) return null;
  return (
    <span className={cn(
      "shrink-0 text-[8px] font-mono uppercase tracking-wider px-1 py-px rounded border whitespace-nowrap",
      meta.cls,
    )}>
      {meta.label}
    </span>
  );
}


function NewsColumn({
  tone, items, label,
}: { tone: "bullish" | "bearish"; items: PreEarningsNewsItem[]; label: string }) {
  const Icon = tone === "bullish" ? TrendingUp : TrendingDown;
  const accentText = tone === "bullish" ? "text-accent-greenSoft" : "text-accent-redSoft";
  const accentBg   = tone === "bullish" ? "bg-accent-green/5"     : "bg-accent-red/5";
  const accentBorder = tone === "bullish" ? "border-accent-green/20" : "border-accent-red/20";

  if (items.length === 0) {
    return (
      <div className={cn("rounded-md p-2.5 border", accentBorder, "bg-bg-base/30")}>
        <div className={cn("flex items-center gap-1.5 text-[11px] font-semibold mb-1", accentText)}>
          <Icon size={11} />
          <span>{label}</span>
        </div>
        <p className="text-[10px] text-text-dim italic">none in last 14d</p>
      </div>
    );
  }

  return (
    <div className={cn("rounded-md p-2.5 border", accentBorder, accentBg)}>
      <div className={cn("flex items-center gap-1.5 text-[11px] font-semibold mb-1.5", accentText)}>
        <Icon size={11} />
        <span>{label}</span>
        <span className="text-text-muted font-normal">· {items.length}</span>
      </div>
      <ul className="space-y-1.5">
        {items.slice(0, 4).map((n, i) => (
          <li key={i} className="text-[11px] leading-snug">
            <div className="flex items-start gap-1.5">
              {n.category && categoryPill(n.category)}
              {n.url ? (
                <a
                  href={n.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-text-secondary hover:text-text-primary transition-colors inline-flex items-start gap-1"
                >
                  <span>{n.title}</span>
                  <ExternalLink size={9} className="shrink-0 opacity-50 mt-0.5" />
                </a>
              ) : (
                <span className="text-text-secondary">{n.title}</span>
              )}
            </div>
            {(n.source || n.published) && (
              <div className="text-[9px] text-text-muted mt-0.5 tabular-nums ml-0">
                {n.source}{n.source && n.published ? " · " : ""}{(n.published || "").slice(0, 10)}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
