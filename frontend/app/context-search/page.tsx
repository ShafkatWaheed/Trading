"use client";

import { useState, useMemo } from "react";
import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import {
  Search,
  Send,
  ChevronDown,
  ChevronRight,
  Hash,
  Flame,
  Factory,
  Sparkles,
  Loader2,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  Minus,
  BarChart3,
  Network,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { contextSearchApi } from "@/lib/api/endpoints";
import type { ContextSearchResponse, ContextSearchStock } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const EXAMPLE_QUERIES = [
  "middle east war oil supplies hit hard",
  "AI capex boom 2026, who benefits 2 hops out",
  "uranium renaissance from data center power demand",
  "GLP-1 weight loss drugs reshape processed food",
  "tariffs on Chinese EVs, domestic auto plays",
];

function TierBadge({ tier }: { tier?: string | null }) {
  if (!tier) return null;
  const tone = tier === "A" ? "badge-green" : tier === "B" ? "badge-amber" : "badge-zinc";
  return <span className={cn("badge text-[9px] uppercase", tone)}>Tier {tier}</span>;
}

function PolarityIcon({ score }: { score: number }) {
  if (score > 0.1) return <TrendingUp size={12} className="text-accent-green" />;
  if (score < -0.1) return <TrendingDown size={12} className="text-accent-red" />;
  return <Minus size={12} className="text-text-muted" />;
}

function LegPill({ leg }: { leg: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    keywords: { label: "keyword", cls: "bg-accent-blue/10 text-accent-blue border-accent-blue/20" },
    graph_relevance: { label: "commodity-graph", cls: "bg-accent-pink/10 text-accent-pink border-accent-pink/20" },
    commodities: { label: "commodity", cls: "bg-accent-pink/10 text-accent-pink border-accent-pink/20" },
  };
  const m = map[leg] ?? { label: leg, cls: "bg-bg-card2 text-text-secondary border-bg-border" };
  return <span className={cn("text-[9px] px-1.5 py-0.5 rounded border font-medium", m.cls)}>{m.label}</span>;
}

function ExpansionPanel({ data }: { data: ContextSearchResponse }) {
  const [open, setOpen] = useState(true);
  const e = data.expansion;
  const hasAnything =
    e.keywords.length || e.commodities.length || e.industries.length || e.themes.length;

  return (
    <div className="card mb-4">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-2 p-3 hover:bg-bg-card2/40 rounded-t-lg transition-colors"
      >
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-accent-violet" strokeWidth={2.2} />
          <div className="text-[13px] font-semibold">What Claude understood</div>
        </div>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && (
        <div className="p-3 pt-0 space-y-3">
          {e.interpretation && (
            <div className="text-[12px] italic text-text-secondary leading-relaxed">
              &ldquo;{e.interpretation}&rdquo;
            </div>
          )}

          {!hasAnything && (
            <div className="text-[11px] text-text-muted">
              Claude returned no structured themes for this query. Results below come
              from the keyword tokenizer only.
            </div>
          )}

          {e.keywords.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold mb-1 flex items-center gap-1">
                <Hash size={10} /> Keywords
              </div>
              <div className="flex flex-wrap gap-1">
                {e.keywords.map((kw) => (
                  <span key={kw} className="text-[10px] px-2 py-0.5 rounded bg-accent-blue/10 text-accent-blue font-mono">
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}

          {e.commodities.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold mb-1 flex items-center gap-1">
                <Flame size={10} /> Commodities
              </div>
              <div className="flex flex-wrap gap-1">
                {e.commodities.map((c) => (
                  <span
                    key={c.code}
                    className={cn(
                      "text-[10px] px-2 py-0.5 rounded font-mono inline-flex items-center gap-1",
                      c.direction === "up"
                        ? "bg-accent-green/10 text-accent-greenSoft"
                        : "bg-accent-red/10 text-accent-redSoft"
                    )}
                  >
                    {c.code} {c.direction === "up" ? "↑" : "↓"} ({c.intensity.toFixed(1)})
                  </span>
                ))}
              </div>
            </div>
          )}

          {e.industries.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold mb-1 flex items-center gap-1">
                <Factory size={10} /> Industries
              </div>
              <div className="flex flex-wrap gap-1">
                {e.industries.map((i) => (
                  <span
                    key={i.code}
                    className={cn(
                      "text-[10px] px-2 py-0.5 rounded font-mono",
                      i.polarity > 0
                        ? "bg-accent-green/10 text-accent-greenSoft"
                        : i.polarity < 0
                          ? "bg-accent-red/10 text-accent-redSoft"
                          : "bg-bg-card2 text-text-secondary"
                    )}
                  >
                    {i.code} ({i.polarity > 0 ? "+" : ""}{i.polarity.toFixed(1)})
                  </span>
                ))}
              </div>
            </div>
          )}

          {e.themes.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold mb-1">
                Themes
              </div>
              <div className="flex flex-wrap gap-1">
                {e.themes.map((t) => (
                  <span key={t} className="text-[10px] px-2 py-0.5 rounded bg-bg-card2 text-text-secondary font-mono">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {e.substitutes_hint.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold mb-1">
                Substitution hints
              </div>
              <ul className="text-[11px] text-text-secondary space-y-0.5 list-disc pl-4">
                {e.substitutes_hint.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StockCard({ stock }: { stock: ContextSearchStock }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card p-3 hover:border-accent-blue/30 transition-colors group">
      <div className="flex items-center gap-2 flex-wrap">
        <Link
          href={`/neighborhood/${encodeURIComponent(stock.symbol)}`}
          className="font-mono font-semibold text-[14px] hover:text-accent-violet"
          title="Open 1-hop graph neighborhood"
        >
          {stock.symbol}
        </Link>
        <TierBadge tier={stock.tier} />
        <PolarityIcon score={stock.composite_score} />
        <span className={cn(
          "text-[11px] font-mono tabular-nums",
          stock.composite_score > 0 ? "text-accent-greenSoft" : stock.composite_score < 0 ? "text-accent-redSoft" : "text-text-muted"
        )}>
          {stock.composite_score > 0 ? "+" : ""}{stock.composite_score.toFixed(2)}
        </span>
        <div className="flex gap-1">
          {stock.legs.map((leg) => (
            <LegPill key={leg} leg={leg} />
          ))}
        </div>
        {stock.name && (
          <span className="text-[11px] text-text-muted truncate min-w-0 flex-1 text-right">
            {stock.name}
          </span>
        )}
        <div className="flex items-center gap-1 ml-auto opacity-0 group-hover:opacity-100 transition-opacity">
          <Link
            href={`/neighborhood/${encodeURIComponent(stock.symbol)}`}
            className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border border-bg-borderHi bg-bg-card2 hover:bg-bg-card text-text-secondary hover:text-text-primary"
            title="Open 1-hop graph neighborhood"
          >
            <Network size={10} /> Graph
          </Link>
          <Link
            href={`/deep-dive/${encodeURIComponent(stock.symbol)}`}
            className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border border-accent-violet/30 bg-accent-violet/10 text-accent-violet hover:bg-accent-violet/20"
            title="Open Deep Dive analysis"
          >
            <BarChart3 size={10} /> Deep Dive
          </Link>
        </div>
      </div>
      {stock.industry_code && (
        <div className="text-[10px] text-text-secondary mt-1">
          {stock.sector ? `${stock.sector} · ` : ""}{stock.industry_code}
        </div>
      )}
      {stock.reasoning.length > 0 && (
        <button
          onClick={() => setOpen(!open)}
          className="mt-1.5 flex items-center gap-1 text-[10px] text-text-muted hover:text-text-secondary transition-colors"
        >
          {open ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          why? ({stock.reasoning.length})
        </button>
      )}
      {open && (
        <ul className="mt-1.5 text-[10px] text-text-secondary space-y-0.5 list-disc pl-4">
          {stock.reasoning.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function IndustryGroups({ data }: { data: ContextSearchResponse }) {
  if (!data.by_industry.length) return null;

  const sorted = [...data.by_industry].sort((a, b) => Math.abs(b.strength) - Math.abs(a.strength));

  return (
    <div className="space-y-3">
      {sorted.map((row) => {
        const groupStocks = data.stocks.filter((s) => s.industry_code === row.industry_code);
        if (!groupStocks.length) return null;
        return (
          <div key={row.industry_code} className="card p-3">
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <Factory size={12} className={row.polarity > 0 ? "text-accent-greenSoft" : "text-accent-redSoft"} />
              <div className="text-[13px] font-semibold">{row.industry_code}</div>
              <span className={cn(
                "text-[10px] font-mono",
                row.polarity > 0 ? "text-accent-greenSoft" : "text-accent-redSoft"
              )}>
                {row.polarity > 0 ? "+" : ""}{row.polarity.toFixed(1)} · strength {row.strength.toFixed(2)}
              </span>
              {row.contributing_keywords.length > 0 && (
                <span className="text-[10px] text-text-muted">
                  via {row.contributing_keywords.slice(0, 3).join(", ")}
                </span>
              )}
            </div>
            <div className="space-y-2">
              {groupStocks.map((s) => (
                <StockCard key={s.symbol} stock={s} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function ContextSearchPage() {
  const [text, setText] = useState("");
  const [groupBy, setGroupBy] = useState<"flat" | "industry">("flat");

  const mutation = useMutation({
    mutationFn: (q: string) => contextSearchApi.search(q, 60),
  });

  const ungroupedStocks = useMemo(() => {
    if (!mutation.data) return [];
    if (groupBy === "industry") {
      // hide stocks that appear in an industry group
      const inGroup = new Set(
        mutation.data.by_industry.flatMap((g) =>
          mutation.data.stocks.filter((s) => s.industry_code === g.industry_code).map((s) => s.symbol)
        )
      );
      return mutation.data.stocks.filter((s) => !inGroup.has(s.symbol));
    }
    return mutation.data.stocks;
  }, [mutation.data, groupBy]);

  const onSubmit = (q: string) => {
    if (!q.trim()) return;
    setText(q);
    mutation.mutate(q);
  };

  return (
    <div>
      <PageHeader
        icon={Search}
        title="Context Search"
        subtitle="Free-text scenario → ranked stocks. Claude translates your query into structured themes, then the graph fans out across keywords, commodities, peers, and supply chains."
        accent="text-accent-violet"
        iconBg="bg-accent-violet/10"
      />

      {/* Input */}
      <div className="card p-3 mb-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit(text);
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. 'middle east war oil supplies hit hard'"
            className="flex-1 bg-bg-card2 border border-bg-border rounded-md px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-accent-violet/50 focus:border-accent-violet/50"
          />
          <button
            type="submit"
            disabled={!text.trim() || mutation.isPending}
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 rounded-md border text-[12px] font-medium transition-colors whitespace-nowrap",
              !text.trim() || mutation.isPending
                ? "bg-bg-card2 text-text-muted border-bg-border cursor-not-allowed"
                : "bg-accent-violet/10 hover:bg-accent-violet/20 text-accent-violet border-accent-violet/30"
            )}
          >
            {mutation.isPending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Send size={12} />
            )}
            {mutation.isPending ? "Thinking…" : "Search"}
          </button>
        </form>

        {/* Example chips */}
        <div className="mt-2 flex flex-wrap gap-1.5">
          <span className="text-[10px] text-text-muted">Try:</span>
          {EXAMPLE_QUERIES.map((q) => (
            <button
              key={q}
              onClick={() => onSubmit(q)}
              disabled={mutation.isPending}
              className="text-[10px] px-2 py-0.5 rounded bg-bg-card2 hover:bg-bg-card text-text-secondary hover:text-text-primary border border-bg-border transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* Loading */}
      {mutation.isPending && (
        <div className="card p-6 grid place-items-center text-center">
          <Loader2 size={20} className="text-accent-violet animate-spin mb-2" />
          <div className="text-[13px] font-medium">Translating your query…</div>
          <div className="text-[10px] text-text-muted mt-1">
            Claude is mapping your scenario to commodities, industries, and themes (~5-10 sec)
          </div>
        </div>
      )}

      {/* Error */}
      {mutation.isError && (
        <div className="card p-4 border-l-[3px] border-l-accent-red/70">
          <div className="flex items-center gap-2 text-[13px] text-accent-redSoft">
            <AlertCircle size={14} />
            Search failed: {(mutation.error as Error)?.message ?? "unknown error"}
          </div>
        </div>
      )}

      {/* Results */}
      {mutation.data && !mutation.isPending && (
        <>
          <ExpansionPanel data={mutation.data} />

          {/* Group control */}
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <div className="text-[11px] text-text-muted">
              <span className="font-mono">{mutation.data.stocks.length}</span> stocks across{" "}
              <span className="font-mono">{mutation.data.by_industry.length}</span> industries
            </div>
            <div className="flex items-center gap-1 text-[11px]">
              <span className="text-text-muted mr-1">Group:</span>
              {(["industry", "flat"] as const).map((opt) => (
                <button
                  key={opt}
                  onClick={() => setGroupBy(opt)}
                  className={cn(
                    "px-2 py-1 rounded transition-colors capitalize",
                    groupBy === opt
                      ? "bg-accent-violet/10 text-accent-violet"
                      : "text-text-secondary hover:text-text-primary hover:bg-bg-card2"
                  )}
                >
                  {opt}
                </button>
              ))}
            </div>
          </div>

          {/* By-industry view */}
          {groupBy === "industry" && (
            <>
              <IndustryGroups data={mutation.data} />
              {ungroupedStocks.length > 0 && (
                <div className="mt-4">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold mb-2">
                    Other graph-relevance hits (no direct industry match)
                  </div>
                  <div className="space-y-2">
                    {ungroupedStocks.slice(0, 20).map((s) => (
                      <StockCard key={s.symbol} stock={s} />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {/* Flat view */}
          {groupBy === "flat" && (
            <div className="space-y-2">
              {mutation.data.stocks.map((s) => (
                <StockCard key={s.symbol} stock={s} />
              ))}
            </div>
          )}

          {mutation.data.stocks.length === 0 && (
            <div className="card p-6 text-center text-[13px] text-text-muted">
              No stocks matched. Try a query with more concrete terms (commodities,
              industries, named events).
            </div>
          )}
        </>
      )}
    </div>
  );
}
