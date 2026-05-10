"use client";

import { useState } from "react";
import { ChevronDown, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";

const SECTIONS = [
  {
    title: "Entry Rules",
    color: "text-accent-blue",
    items: [
      "Configurable min opportunity score (default 60)",
      "Configurable max buys per cycle (default 3)",
      "Require 2+ confirmation filters (Trend Pullback, Relative Strength, Volume)",
      "Only trade when 7+ of 12 signals agree on direction",
      "Prioritize signals with 70%+ historical win rate on this stock",
      "Discount signals with <40% backtest win rate",
      "Follow the money — favor sectors with positive money flow",
      "If sector flow is negative, reduce conviction even if signals are bullish",
    ],
  },
  {
    title: "Risk Rules",
    color: "text-accent-redSoft",
    items: [
      "Max risk per trade is configurable (default 2% of portfolio)",
      "Max open positions is configurable (default 8)",
      "Keep at least 20% in cash at all times",
      "Configurable stop loss % on every trade (default 12%)",
      "Set target on every trade (at resistance or +15% max)",
    ],
  },
  {
    title: "Market Regime Rules",
    color: "text-accent-amber",
    items: [
      "Normal: trade all sectors, standard position sizes",
      "High volatility (VIX > 30): defensive only, reduce sizes, raise min score",
      "Recession warning (inverted yield curve): favor healthcare, staples, utilities. Avoid cyclicals",
    ],
  },
  {
    title: "Exit Rules",
    color: "text-accent-violet",
    items: [
      "Close when stop loss hit (automatic)",
      "Close when target reached (take profit)",
      "Close when signal alignment flips bearish (7+ signals flip)",
      "Close when AI detects macro regime change affecting the position",
    ],
  },
  {
    title: "AI Decision Process",
    color: "text-accent-cyan",
    items: [
      "Step 1: Read macro environment (VIX, rates, geopolitical, disruption, sector flow)",
      "Step 2: AI picks sectors + stocks based on market context",
      "Step 3: Deep dive each pick — analyze all 12 indicators with raw data",
      "Step 4: Check backtest track record — which signals historically worked",
      "Step 5: Claude makes BUY/SELL/HOLD decision with reasoning",
      "Step 6: Execute paper trades with calculated position sizing",
    ],
  },
];

export function TradingRules() {
  const [open, setOpen] = useState(false);
  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full px-5 py-4 flex items-center justify-between text-sm hover:bg-bg-card2 transition-colors"
      >
        <span className="flex items-center gap-2">
          <BookOpen size={14} className="text-accent-blue" />
          AI Trading Rules
        </span>
        <ChevronDown size={14} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="px-5 pb-5 border-t border-bg-border pt-5 grid grid-cols-1 lg:grid-cols-2 gap-5">
          {SECTIONS.map((s) => (
            <div key={s.title}>
              <h4 className={cn("text-xs font-bold uppercase tracking-wider mb-2", s.color)}>
                {s.title}
              </h4>
              <ul className="space-y-1.5">
                {s.items.map((item, i) => (
                  <li key={i} className="text-xs text-text-secondary flex items-start gap-2 leading-relaxed">
                    <span className="text-text-muted mt-0.5">•</span>
                    <span dangerouslySetInnerHTML={{ __html: item }} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
