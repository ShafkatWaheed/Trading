"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, BookOpen, Database, Layers, Filter } from "lucide-react";
import { agentApi } from "@/lib/api/endpoints";
import type { AgentPersonality } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const PORTFOLIO_AGENTS = [
  "momentum",
  "value",
  "contrarian",
  "macro",
  "disruption",
  "insider",
  "flow",
] as const;

const PIPELINE_STEPS = [
  {
    title: "Screen the universe",
    detail:
      "All 69 stocks → fetch 1y history → compute RSI / MACD / SMA / Bollinger / volume / opportunity score → rank → take top N (default 15).",
    icon: Filter,
  },
  {
    title: "Per-agent stock picks",
    detail:
      "Each of 7 personality agents sees the SAME ranked candidate ladder + their own personality lens (philosophy / prioritizes / avoids), and picks up to 3 to BUY (or NONE).",
    icon: Layers,
  },
  {
    title: "Tally consensus",
    detail:
      "Count distinct agents per symbol. Symbols with ≥3 agents enter the consensus pool. Top 5 by agent count form the suggested portfolio.",
    icon: Database,
  },
];

const SHARED_CONTEXT = [
  { label: "Price + 1y OHLC history", source: "yfinance daily bars" },
  { label: "RSI / MACD / SMA / Bollinger", source: "computed point-in-time per symbol" },
  { label: "20-day return vs benchmark", source: "computed from price history" },
  { label: "Opportunity score (0-100)", source: "shared scorer used by Discover" },
  { label: "Strategy label", source: "Momentum / Breakout / Support Bounce / Golden Cross / etc." },
  { label: "Volume vs 20-day avg", source: "yfinance volume" },
  { label: "Bull / bear signal counts", source: "Deep-Dive equivalent technical engine" },
  { label: "Sector classification", source: "STOCK_DB catalog (69 stocks, 9 sectors)" },
];

const AGENT_PICK_INSTRUCTION =
  "Reply on a SINGLE LINE: SYMBOL1 | reason | SYMBOL2 | reason | ... or NONE | reason";

export function PortfolioStrategyReference() {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["agent", "personalities"],
    queryFn: () => agentApi.personalities(),
    staleTime: 60 * 60_000,
  });

  const agents = (data?.agents ?? []).filter((a) =>
    (PORTFOLIO_AGENTS as readonly string[]).includes(a.key)
  );

  return (
    <div className="card p-0 overflow-hidden border-accent-violet/30">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full px-4 py-3 flex items-center gap-3 hover:bg-bg-card2/40 transition-colors"
      >
        <BookOpen size={14} className="text-accent-violet" strokeWidth={2.4} />
        <span className="text-sm font-semibold tracking-tight">
          Strategy Reference — how the portfolio AI picks stocks
        </span>
        <span className="text-[10px] uppercase tracking-wider text-text-muted ml-auto">
          69-stock universe · 7 agents · ranked consensus
        </span>
        <ChevronDown
          size={14}
          className={cn("text-text-muted transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <div className="border-t border-bg-divider p-4 space-y-4 bg-bg-base/40">
          <section>
            <div className="text-[11px] uppercase tracking-wider text-text-muted font-semibold mb-2">
              Pipeline
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              {PIPELINE_STEPS.map((s, i) => {
                const Icon = s.icon;
                return (
                  <div
                    key={s.title}
                    className="rounded-md border border-bg-divider bg-bg-card2/40 p-3"
                  >
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="w-5 h-5 rounded-full bg-accent-violet/15 grid place-items-center text-[10px] font-bold text-accent-violet">
                        {i + 1}
                      </span>
                      <Icon size={11} className="text-accent-violet" strokeWidth={2.4} />
                      <span className="text-xs font-semibold text-text-primary">{s.title}</span>
                    </div>
                    <p className="text-[11px] text-text-secondary leading-snug">{s.detail}</p>
                  </div>
                );
              })}
            </div>
          </section>

          <section>
            <div className="flex items-center gap-2 mb-2">
              <Layers size={12} className="text-accent-blue" strokeWidth={2.4} />
              <span className="text-[11px] uppercase tracking-wider text-text-muted font-semibold">
                Shared candidate ladder — every agent sees the SAME ranked list
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
              Each agent receives one line per candidate: rank, sector, opportunity score,
              strategy, price, 20-day change, RSI, volume ratio, bull/bear signal counts.
            </p>
          </section>

          <section>
            <div className="text-[11px] uppercase tracking-wider text-text-muted font-semibold mb-2">
              Each agent's lens — personality + how they read the ladder
            </div>
            {isLoading ? (
              <div className="text-[11px] text-text-muted">Loading personalities…</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {PORTFOLIO_AGENTS.map((key) => {
                  const a = agents.find((x) => x.key === key);
                  if (!a) return null;
                  return <AgentCard key={key} a={a} />;
                })}
              </div>
            )}
          </section>

          <section>
            <div className="text-[11px] uppercase tracking-wider text-text-muted font-semibold mb-2">
              Reply contract
            </div>
            <div className="rounded-md border border-bg-divider bg-bg-card2/40 px-3 py-2 text-[11px] font-mono text-text-secondary leading-snug">
              {AGENT_PICK_INSTRUCTION}
            </div>
            <p className="text-[10px] text-text-muted mt-2 italic leading-snug">
              The reply parser only accepts symbols that were in the candidate ladder — agents
              can't invent or hallucinate tickers outside the screened universe.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}

function AgentCard({ a }: { a: AgentPersonality }) {
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
        <div className="text-[10px] text-text-muted leading-snug">
          <span className="text-accent-redSoft font-semibold">Avoids:</span>{" "}
          {a.avoids.slice(0, 3).join(" · ")}
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
