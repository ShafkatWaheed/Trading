"use client";

import { useState } from "react";
import Link from "next/link";
import { Target, Edit2, ExternalLink, ChevronDown } from "lucide-react";
import { TickerSearchInput } from "@/components/ui/ticker-search-input";
import { cn } from "@/lib/utils";

type Props = {
  symbol: string;
  onChange: (sym: string) => void;
};

/**
 * The single source of truth for "which stock you're backtesting" — sits at
 * the top of Prove It so every tab below operates on the same anchor. Click
 * "Change" to swap; press Enter on any ticker to commit.
 */
export function StockAnchor({ symbol, onChange }: Props) {
  const [editing, setEditing] = useState(false);

  return (
    <section className="card p-5 border-l-4 border-accent-cyan/40">
      <div className="flex items-center gap-4 flex-wrap">
        <div className="shrink-0 w-11 h-11 rounded-lg grid place-items-center bg-accent-cyan/10 text-accent-cyan ring-1 ring-inset ring-accent-cyan/30">
          <Target size={20} strokeWidth={2.4} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
            Selected stock
          </div>
          {!editing ? (
            <div className="flex items-baseline gap-2 mt-0.5 flex-wrap">
              <span className="font-mono text-3xl font-bold tracking-tight text-text-primary">
                {symbol}
              </span>
              <button
                onClick={() => setEditing(true)}
                className={cn(
                  "text-[11px] text-text-muted hover:text-accent-cyan flex items-center gap-1",
                  "px-2 py-1 rounded-md border border-bg-borderHi hover:border-accent-cyan/40 transition-colors"
                )}
              >
                <Edit2 size={11} />
                Change
              </button>
              <Link
                href={`/deep-dive/${encodeURIComponent(symbol)}`}
                className="text-[11px] text-text-muted hover:text-accent-violet flex items-center gap-1 px-2 py-1 rounded-md hover:bg-bg-card2 transition-colors"
              >
                Open in Deep Dive
                <ExternalLink size={10} />
              </Link>
            </div>
          ) : (
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <div className="w-56">
                <TickerSearchInput
                  onPick={(sym) => { onChange(sym); setEditing(false); }}
                  placeholder={`Search… (current: ${symbol})`}
                  tone="cyan"
                  compact
                  clearOnPick
                />
              </div>
              <button
                onClick={() => setEditing(false)}
                className="text-[11px] text-text-muted hover:text-text-primary px-2 py-1"
              >
                Cancel
              </button>
            </div>
          )}

          <p className="text-[11px] text-text-muted mt-1 leading-snug">
            Every backtest below runs against this stock. For multi-stock comparisons
            and portfolio simulations, it's automatically included as the anchor.
          </p>
        </div>
      </div>
    </section>
  );
}
