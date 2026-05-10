"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, BookOpen, Database, Layers } from "lucide-react";
import { agentApi } from "@/lib/api/endpoints";
import type { AgentPersonality } from "@/lib/api/types";
import { cn } from "@/lib/utils";

// The AI Analyst multi-agent backtest only votes with these 7.
// Keep in sync with `_MULTI_AGENTS` in api/services/ai_analyst_service.py.
const AI_ANALYST_AGENTS = [
  "momentum",
  "value",
  "contrarian",
  "macro",
  "disruption",
  "insider",
  "flow",
] as const;

// Per-agent backtest data sources. Documents the *historical* feed each agent
// reads — sourced from the same code paths that build the prompt context.
const AGENT_DATA_SOURCES: Record<string, { label: string; source: string }[]> = {
  momentum: [
    { label: "Price + RSI/MACD", source: "yfinance daily history" },
    { label: "Volume vs 20-day avg", source: "yfinance" },
    { label: "Sector ETF momentum", source: "XLK/XLV/XLF/etc. (yfinance)" },
  ],
  value: [
    { label: "Trailing P/E", source: "yfinance quarterly_income_stmt + earnings_history" },
    { label: "TTM EPS", source: "computed from 4 most recent quarters" },
    { label: "Dividend yield", source: "yfinance" },
  ],
  contrarian: [
    { label: "RSI extremes / oversold", source: "yfinance" },
    { label: "VIX (fear gauge)", source: "^VIX historical (yfinance)" },
    { label: "Bearish news + sentiment score", source: "Polygon news (if key set) or momentum proxy" },
  ],
  macro: [
    { label: "VIX, 10Y, 5Y treasuries", source: "^VIX, ^TNX, ^FVX historical (yfinance)" },
    { label: "S&P 500 trend", source: "^GSPC historical (yfinance)" },
    { label: "Regime classification", source: "computed from yield curve + VIX + S&P trend" },
  ],
  disruption: [
    { label: "Sector ETF performance window", source: "XLK/XLV/etc. historical (yfinance)" },
    { label: "Industry classification", source: "yfinance + STOCK_DB catalog" },
  ],
  insider: [
    { label: "Form 4 insider trades", source: "SEC EDGAR (free, full historical)" },
    { label: "Congressional trades", source: "Capitol Trades MCP (free, full historical)" },
    { label: "Cluster detection (≥7-day windows)", source: "computed from above" },
  ],
  flow: [
    { label: "Daily short volume + ratio", source: "FINRA REG SHO (free, per-stock, daily)" },
    { label: "Multi-day regime", source: "computed (avg over last 3-5 sessions)" },
  ],
};

export function AiStrategyReference() {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["agent", "personalities"],
    queryFn: () => agentApi.personalities(),
    staleTime: 60 * 60_000,
  });

  const agents = (data?.agents ?? []).filter((a) =>
    (AI_ANALYST_AGENTS as readonly string[]).includes(a.key)
  );

  return (
    <div className="card p-0 overflow-hidden border-accent-violet/30">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full px-4 py-3 flex items-center gap-3 hover:bg-bg-card2/40 transition-colors"
      >
        <BookOpen size={14} className="text-accent-violet" strokeWidth={2.4} />
        <span className="text-sm font-semibold tracking-tight">
          Strategy Reference — what each agent reads
        </span>
        <span className="text-[10px] uppercase tracking-wider text-text-muted ml-auto">
          {AI_ANALYST_AGENTS.length} agents · 7 historical feeds
        </span>
        <ChevronDown
          size={14}
          className={cn("text-text-muted transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <div className="border-t border-bg-divider p-4 space-y-4 bg-bg-base/40">
          {/* Shared context — every agent sees this per cycle */}
          <section>
            <div className="flex items-center gap-2 mb-2">
              <Layers size={12} className="text-accent-blue" strokeWidth={2.4} />
              <span className="text-[11px] uppercase tracking-wider text-text-muted font-semibold">
                Shared context — assembled per cycle, identical for all 7 agents
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-[11px] text-text-secondary">
              {SHARED_CONTEXT.map((item) => (
                <div
                  key={item.label}
                  className="flex items-start gap-2 bg-bg-card2/40 border border-bg-divider rounded-md px-2.5 py-1.5"
                >
                  <Database size={10} className="text-accent-blue/70 mt-0.5 shrink-0" strokeWidth={2.4} />
                  <div className="leading-snug">
                    <span className="text-text-primary font-medium">{item.label}</span>
                    <span className="text-text-muted"> — {item.source}</span>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-[10px] text-text-muted mt-2 italic leading-snug">
              Walk-forward guarantee: every value is point-in-time at the cycle date. No future bars,
              no future filings, no look-ahead.
            </p>
          </section>

          {/* Per-agent strategy + their preferred extra feed */}
          <section>
            <div className="text-[11px] uppercase tracking-wider text-text-muted font-semibold mb-2">
              Each agent's lens + the data they emphasize
            </div>
            {isLoading ? (
              <div className="text-[11px] text-text-muted">Loading personalities…</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {AI_ANALYST_AGENTS.map((key) => {
                  const a = agents.find((x) => x.key === key);
                  if (!a) return null;
                  return <AgentCard key={key} a={a} />;
                })}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function AgentCard({ a }: { a: AgentPersonality }) {
  const sources = AGENT_DATA_SOURCES[a.key] ?? [];
  return (
    <div className="rounded-md border border-bg-divider bg-bg-card2/40 p-3">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-base">{a.icon}</span>
        <span className="text-xs font-bold text-text-primary">{a.name}</span>
        <span className="text-[9px] uppercase tracking-wider text-text-muted ml-auto">
          {a.kind}
        </span>
      </div>
      <p className="text-[11px] text-text-secondary leading-snug mb-2">{a.philosophy}</p>

      {a.prioritizes.length > 0 && (
        <div className="text-[10px] text-text-muted leading-snug mb-1.5">
          <span className="text-accent-greenSoft font-semibold">Prioritizes:</span>{" "}
          {a.prioritizes.slice(0, 3).join(" · ")}
        </div>
      )}
      {a.avoids.length > 0 && (
        <div className="text-[10px] text-text-muted leading-snug mb-2">
          <span className="text-accent-redSoft font-semibold">Avoids:</span>{" "}
          {a.avoids.slice(0, 3).join(" · ")}
        </div>
      )}

      {sources.length > 0 && (
        <div className="border-t border-bg-divider pt-1.5 mt-1.5">
          <div className="text-[9px] uppercase tracking-wider text-accent-blue/80 font-semibold mb-1">
            Historical data emphasized
          </div>
          <ul className="space-y-0.5">
            {sources.map((s) => (
              <li key={s.label} className="text-[10px] text-text-muted leading-snug">
                <span className="text-text-secondary">{s.label}</span>{" "}
                <span className="text-text-dim">— {s.source}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {a.historical_edge && (
        <div className="mt-2 pt-1.5 border-t border-bg-divider text-[10px] text-text-dim italic leading-snug">
          {a.historical_edge}
        </div>
      )}
    </div>
  );
}

const SHARED_CONTEXT = [
  { label: "Price + OHLC history", source: "yfinance daily bars (252-day window)" },
  { label: "RSI / MACD / SMA / Bollinger", source: "computed point-in-time from price history" },
  { label: "Market Pulse (regime)", source: "^VIX + ^TNX + ^FVX + ^GSPC (yfinance)" },
  { label: "Discover-equivalent score", source: "recomputed at cycle date from same logic as live Discover" },
  { label: "Deep-Dive signals (16+)", source: "shared technical engine in src/analysis/" },
  { label: "Sector ETF performance", source: "XLK / XLV / XLF / XLE / etc. (yfinance)" },
  { label: "News + sentiment", source: "Polygon news (if POLYGON_API_KEY) or momentum proxy" },
  { label: "Trailing P/E + TTM EPS", source: "yfinance quarterly statements (point-in-time TTM)" },
  { label: "Insider window", source: "SEC EDGAR Form 4 + Capitol Trades (free historical)" },
  { label: "FINRA short volume", source: "FINRA REG SHO daily file (free, per-stock)" },
  { label: "Trade plan (entry/stop/targets)", source: "computed from ATR + support/resistance" },
  { label: "Open position state", source: "the simulated trade book at cycle t" },
];
