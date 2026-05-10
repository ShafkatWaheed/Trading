"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import {
  Newspaper,
  TrendingUp,
  TrendingDown,
  ArrowUpRight,
  Info,
  Globe,
  AlertTriangle,
  Loader2,
  Sparkles,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { newsImpactApi } from "@/lib/api/endpoints";
import type {
  NewsImpactResponse,
  NewsImpactStock,
  Tier,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

const TIER_TONE: Record<
  Tier,
  { badge: string; ring: string; label: string }
> = {
  A: { badge: "badge-amber", ring: "ring-accent-amber/40", label: "A" },
  B: { badge: "badge-blue", ring: "ring-accent-blue/40", label: "B" },
  C: { badge: "badge-zinc", ring: "ring-bg-borderHi/40", label: "C" },
  D: { badge: "badge-zinc", ring: "ring-bg-border/40", label: "D" },
};

const SAMPLE_HEADLINES = [
  "OpenAI announces $50B GPU build-out for new data center with Oracle",
  "Iran fires missiles at Saudi Aramco oil refinery, output cut 30%",
  "FTC blocks Capital One Discover merger citing antitrust concerns",
  "FDA rejects Eli Lilly Alzheimer's drug after panel vote",
  "European natural gas storage at 30%, lowest since 2022, prices surge",
  "Hurricane Milton makes landfall in Florida with Category 4 strength",
  "Fed announces 25bp rate cut, signaling end of tightening cycle",
];

function tierBadge(t: Tier) {
  const tone = TIER_TONE[t];
  return (
    <span className={cn("badge text-[10px] tabular-nums px-1.5 py-0.5", tone.badge)}>
      {tone.label}
    </span>
  );
}

function fmtPct(p: number, withSign = true): string {
  const sign = withSign && p > 0 ? "+" : "";
  return `${sign}${(p * 100).toFixed(0)}%`;
}

function StockRow({ s }: { s: NewsImpactStock }) {
  const isBull = s.polarity > 0;
  const isBear = s.polarity < 0;

  // Detect graph-expansion provenance ("via:NVDA" markers in contributing_industries)
  const viaSymbols = s.contributing_industries
    .filter((x) => x.startsWith("via:"))
    .map((x) => x.slice(4));
  const isGraphExpanded = viaSymbols.length > 0 && s.contributing_keywords.length === 0;

  return (
    <div
      className={cn(
        "card p-3 border-l-[3px] transition-colors",
        isBull ? "border-l-accent-green/60" : isBear ? "border-l-accent-red/60" : "border-l-bg-borderHi"
      )}
    >
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          {tierBadge(s.tier)}
          <Link
            href={`/neighborhood/${encodeURIComponent(s.symbol)}`}
            className="font-mono text-[14px] font-semibold tabular-nums hover:text-accent-violet"
          >
            {s.symbol}
          </Link>
          {s.name && (
            <span className="text-[11px] text-text-muted truncate max-w-[280px]">
              {s.name}
            </span>
          )}
          {s.direct_target && (
            <span className="badge badge-violet text-[9px] px-1.5 py-0">
              direct
            </span>
          )}
          {isGraphExpanded && (
            <span
              className="badge badge-cyan text-[9px] px-1.5 py-0"
              title={`Surfaced via graph: ${viaSymbols.join(", ")}`}
            >
              via {viaSymbols[0]}
              {viaSymbols.length > 1 ? `+${viaSymbols.length - 1}` : ""}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 ml-auto">
          {/* Polarity arrow */}
          <div className="flex items-center gap-1">
            {isBull ? (
              <TrendingUp size={12} className="text-accent-green" strokeWidth={2.4} />
            ) : isBear ? (
              <TrendingDown size={12} className="text-accent-red" strokeWidth={2.4} />
            ) : null}
            <span
              className={cn(
                "text-[11px] font-mono tabular-nums",
                isBull
                  ? "text-accent-green"
                  : isBear
                  ? "text-accent-red"
                  : "text-text-muted"
              )}
            >
              {fmtPct(s.polarity)}
            </span>
          </div>

          {/* Composite score */}
          <div className="text-right tabular-nums">
            <div className="text-[12px] font-mono font-semibold">
              {(s.composite_score * 100).toFixed(0)}
            </div>
            <div className="text-[9px] text-text-muted">score</div>
          </div>
        </div>
      </div>

      {/* Why trace */}
      {(s.contributing_keywords.length > 0 || s.contributing_industries.length > 0) && (
        <div className="text-[10px] text-text-muted mt-2 flex flex-wrap gap-x-2 gap-y-1">
          {s.contributing_keywords.length > 0 && (
            <span>
              <span className="text-text-dim">keywords:</span>{" "}
              <span className="font-mono text-accent-violet">
                {s.contributing_keywords.slice(0, 4).join(", ")}
              </span>
            </span>
          )}
          {s.industry_code && (
            <span>
              <span className="text-text-dim">industry:</span>{" "}
              <span>{s.industry_code}</span>
            </span>
          )}
          {viaSymbols.length > 0 && (
            <span>
              <span className="text-text-dim">graph hop from:</span>{" "}
              <span className="font-mono text-accent-cyan">
                {viaSymbols.slice(0, 3).join(", ")}
              </span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function IndustryGroup({
  industryCode,
  stocks,
  polarity,
  strength,
  contributingKeywords,
}: {
  industryCode: string;
  stocks: NewsImpactStock[];
  polarity: number;
  strength: number;
  contributingKeywords: string[];
}) {
  const isBull = polarity > 0;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 px-1">
        <h3 className="text-[12px] font-semibold uppercase tracking-wider text-text-secondary">
          {industryCode}
        </h3>
        <span
          className={cn(
            "text-[10px] tabular-nums",
            isBull ? "text-accent-green" : "text-accent-red"
          )}
        >
          {fmtPct(polarity)} · str {fmtPct(strength, false)}
        </span>
        <span className="text-[10px] text-text-muted ml-auto">
          {contributingKeywords.slice(0, 3).join(" · ")}
        </span>
      </div>
      <div className="space-y-1.5">
        {stocks.map((s) => (
          <StockRow key={s.symbol} s={s} />
        ))}
      </div>
    </div>
  );
}

export default function NewsImpactPage() {
  const [text, setText] = useState("");

  const mutation = useMutation({
    mutationFn: (t: string) => newsImpactApi.analyze(t),
  });

  const data = mutation.data as NewsImpactResponse | undefined;

  // Group stocks by their primary industry for the rendered output
  const grouped = useMemo(() => {
    if (!data) return [];
    const byIndustry = new Map<string, NewsImpactStock[]>();
    for (const s of data.stocks) {
      const key = s.industry_code || "Unclassified";
      if (!byIndustry.has(key)) byIndustry.set(key, []);
      byIndustry.get(key)!.push(s);
    }

    const industryMeta = new Map(data.industries.map((i) => [i.industry_code, i]));
    const groups = Array.from(byIndustry.entries()).map(([code, stocks]) => {
      const meta = industryMeta.get(code);
      // Aggregate polarity & strength: use industry-level if present, else weighted avg from stocks
      const polarity = meta?.polarity ?? avg(stocks.map((s) => s.polarity));
      const strength = meta?.strength ?? avg(stocks.map((s) => s.strength));
      const keywords = meta?.contributing_keywords ?? [];
      return { code, stocks, polarity, strength, contributingKeywords: keywords };
    });

    // Sort: highest aggregate signal first (|polarity| × strength)
    groups.sort((a, b) => Math.abs(b.polarity) * b.strength - Math.abs(a.polarity) * a.strength);
    return groups;
  }, [data]);

  const sampleClick = (h: string) => {
    setText(h);
    mutation.mutate(h);
  };

  const totalStocks = data?.stocks.length ?? 0;
  const bullishCount = data?.stocks.filter((s) => s.polarity > 0).length ?? 0;
  const bearishCount = data?.stocks.filter((s) => s.polarity < 0).length ?? 0;

  return (
    <div>
      <PageHeader
        icon={Newspaper}
        title="News Impact"
        subtitle="Paste a headline; get ranked stocks via keywords → industries → graph expansion."
        accent="text-accent-cyan"
        iconBg="bg-accent-cyan/10"
      />

      {/* Input panel */}
      <div className="card p-4 mb-4">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste a news headline or short article..."
          rows={3}
          className="w-full bg-bg-card2 rounded-lg p-3 text-[13px] text-text-primary placeholder:text-text-muted resize-none border border-bg-border focus:border-accent-cyan/40 focus:outline-none"
        />
        <div className="flex items-center gap-3 mt-3 flex-wrap">
          <button
            disabled={!text.trim() || mutation.isPending}
            onClick={() => mutation.mutate(text)}
            className={cn(
              "btn-primary inline-flex items-center gap-2 text-[12px] px-4 py-2 rounded-lg font-medium",
              "bg-accent-cyan/10 hover:bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/30 transition-colors",
              "disabled:opacity-40 disabled:cursor-not-allowed"
            )}
          >
            {mutation.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Sparkles size={14} />
            )}
            Analyze
          </button>
          {text && (
            <button
              onClick={() => {
                setText("");
                mutation.reset();
              }}
              className="text-[11px] text-text-muted hover:text-text-primary"
            >
              Clear
            </button>
          )}
          <span className="text-[10px] text-text-muted ml-auto">
            Press <kbd className="font-mono px-1 bg-bg-card2 rounded border border-bg-border">Cmd+Enter</kbd> to analyze
          </span>
        </div>

        {/* Sample headlines */}
        {!data && !mutation.isPending && (
          <div className="mt-4 pt-3 border-t border-bg-border">
            <div className="text-[10px] uppercase tracking-wider text-text-muted mb-2">
              Try a sample
            </div>
            <div className="flex flex-wrap gap-1.5">
              {SAMPLE_HEADLINES.map((h) => (
                <button
                  key={h}
                  onClick={() => sampleClick(h)}
                  className="text-[11px] px-2.5 py-1 rounded-md bg-bg-card2 hover:bg-bg-card text-text-secondary hover:text-text-primary transition-colors text-left max-w-full truncate"
                  title={h}
                >
                  {h.length > 60 ? h.slice(0, 60) + "…" : h}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Loading */}
      {mutation.isPending && (
        <div className="card p-6 grid place-items-center text-center">
          <Loader2 size={20} className="animate-spin text-accent-cyan mb-2" />
          <div className="text-[12px] text-text-secondary">Tokenizing → matching keywords → expanding graph…</div>
        </div>
      )}

      {/* Error */}
      {mutation.isError && (
        <div className="card p-4 border-l-[3px] border-l-accent-red/70">
          <div className="flex items-start gap-2">
            <AlertTriangle size={14} className="text-accent-red shrink-0 mt-0.5" />
            <div className="text-[13px] text-accent-redSoft">
              Analyze failed. Make sure the API is running on :8000 and the seed
              data has been loaded (Tier A + keyword_impact + relations + peers).
            </div>
          </div>
        </div>
      )}

      {/* Empty result */}
      {data && totalStocks === 0 && (
        <div className="card p-6 grid place-items-center text-center">
          <Info size={18} className="text-text-muted mb-2" />
          <div className="text-[13px] font-medium">No matches found</div>
          <div className="text-[11px] text-text-muted mt-1 max-w-md">
            The headline didn't trigger any keyword matches in our seeded
            dictionary. Try one of the samples above, or rephrase using terms
            like AI, oil, tariff, FDA, hurricane, GLP-1, etc.
          </div>
        </div>
      )}

      {/* Results header strip */}
      {data && totalStocks > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
          <div className="card p-3">
            <div className="text-[10px] uppercase tracking-wider text-text-muted">Total</div>
            <div className="text-xl font-semibold tabular-nums">{totalStocks}</div>
            <div className="text-[10px] text-text-muted">stocks</div>
          </div>
          <div className="card p-3">
            <div className="text-[10px] uppercase tracking-wider text-text-muted">Bullish</div>
            <div className="text-xl font-semibold tabular-nums text-accent-green">
              {bullishCount}
            </div>
            <div className="text-[10px] text-text-muted">positive polarity</div>
          </div>
          <div className="card p-3">
            <div className="text-[10px] uppercase tracking-wider text-text-muted">Bearish</div>
            <div className="text-xl font-semibold tabular-nums text-accent-red">
              {bearishCount}
            </div>
            <div className="text-[10px] text-text-muted">negative polarity</div>
          </div>
          <div className="card p-3">
            <div className="text-[10px] uppercase tracking-wider text-text-muted">Industries</div>
            <div className="text-xl font-semibold tabular-nums">
              {data.industries.length}
            </div>
            <div className="text-[10px] text-text-muted">affected</div>
          </div>
        </div>
      )}

      {/* Matched trace strip */}
      {data && (data.matched_keywords.length > 0 || data.matched_countries.length > 0) && (
        <div className="card p-3 mb-4 flex flex-wrap items-center gap-2">
          {data.matched_keywords.length > 0 && (
            <>
              <span className="text-[10px] uppercase tracking-wider text-text-muted">
                Keywords
              </span>
              {data.matched_keywords.slice(0, 12).map((k) => (
                <span
                  key={k}
                  className={cn(
                    "badge text-[10px]",
                    data.negated_keywords.includes(k)
                      ? "badge-red line-through"
                      : "badge-violet"
                  )}
                >
                  {k}
                </span>
              ))}
            </>
          )}
          {data.matched_countries.length > 0 && (
            <>
              <Globe size={10} className="text-text-muted ml-2" />
              {data.matched_countries.map((c) => (
                <span key={c} className="badge badge-blue text-[10px]">
                  {c}
                </span>
              ))}
            </>
          )}
        </div>
      )}

      {/* Grouped results */}
      {data && totalStocks > 0 && (
        <div className="space-y-5">
          {grouped.map((g) => (
            <IndustryGroup
              key={g.code}
              industryCode={g.code}
              stocks={g.stocks}
              polarity={g.polarity}
              strength={g.strength}
              contributingKeywords={g.contributingKeywords}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function avg(xs: number[]): number {
  if (xs.length === 0) return 0;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}
