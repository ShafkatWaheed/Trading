"use client";

import { X } from "lucide-react";
import { cn } from "@/lib/utils";

type Tone = "blue" | "amber" | "violet" | "cyan" | "pink";

const TONE: Record<Tone, string> = {
  blue:   "bg-accent-blue/10 text-accent-blue border-accent-blue/40 hover:bg-accent-blue/20",
  amber:  "bg-accent-amber/10 text-accent-amber border-accent-amber/40 hover:bg-accent-amber/20",
  violet: "bg-accent-violet/10 text-accent-violet border-accent-violet/40 hover:bg-accent-violet/20",
  cyan:   "bg-accent-cyan/10 text-accent-cyan border-accent-cyan/40 hover:bg-accent-cyan/20",
  pink:   "bg-accent-pink/10 text-accent-pink border-accent-pink/40 hover:bg-accent-pink/20",
};

const TONE_HOVER: Record<Tone, string> = {
  blue:   "hover:border-accent-blue/40 hover:text-accent-blue",
  amber:  "hover:border-accent-amber/40 hover:text-accent-amber",
  violet: "hover:border-accent-violet/40 hover:text-accent-violet",
  cyan:   "hover:border-accent-cyan/40 hover:text-accent-cyan",
  pink:   "hover:border-accent-pink/40 hover:text-accent-pink",
};

type SelectedProps = {
  symbols: string[];
  onRemove: (symbol: string) => void;
  tone?: Tone;
  emptyText?: string;
  max?: number;
  label?: string;
};

export function SelectedSymbolChips({
  symbols,
  onRemove,
  tone = "violet",
  emptyText = "No tickers selected.",
  max,
  label,
}: SelectedProps) {
  return (
    <div>
      {label !== undefined && (
        <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1.5">
          {label}{max !== undefined ? ` (${symbols.length}/${max})` : ""}
        </div>
      )}
      {symbols.length === 0 ? (
        <p className="text-xs text-text-muted">{emptyText}</p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {symbols.map((s) => (
            <button
              key={s}
              onClick={() => onRemove(s)}
              className={cn("badge font-mono", TONE[tone])}
            >
              {s} <X size={11} className="ml-1 opacity-60" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

type WatchlistAddProps = {
  watchlist: { symbol: string }[];
  selected: string[];
  onAdd: (symbol: string) => void;
  max: number;
  tone?: Tone;
  label?: string;
};

export function WatchlistQuickAdd({
  watchlist,
  selected,
  onAdd,
  max,
  tone = "violet",
  label = "From watchlist",
}: WatchlistAddProps) {
  if (watchlist.length === 0) return null;
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1.5">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {watchlist.map((w) => {
          const disabled = selected.includes(w.symbol) || selected.length >= max;
          return (
            <button
              key={w.symbol}
              onClick={() => onAdd(w.symbol)}
              disabled={disabled}
              className={cn(
                "badge bg-bg-base border-bg-border text-text-secondary font-mono disabled:opacity-30",
                !disabled && TONE_HOVER[tone],
              )}
            >
              + {w.symbol}
            </button>
          );
        })}
      </div>
    </div>
  );
}
