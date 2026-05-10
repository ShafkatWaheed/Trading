"use client";

import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import type { StockSearchResult } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type Tone = "blue" | "amber" | "violet" | "cyan" | "pink";

const FOCUS_BORDER: Record<Tone, string> = {
  blue:   "focus:border-accent-blue/60",
  amber:  "focus:border-accent-amber/60",
  violet: "focus:border-accent-violet/60",
  cyan:   "focus:border-accent-cyan/60",
  pink:   "focus:border-accent-pink/60",
};

const HIGHLIGHT_TEXT: Record<Tone, string> = {
  blue:   "text-accent-blue",
  amber:  "text-accent-amber",
  violet: "text-accent-violet",
  cyan:   "text-accent-cyan",
  pink:   "text-accent-pink",
};

type Props = {
  /** Called when the user picks a result (or hits Enter on a non-empty value). */
  onPick: (symbol: string) => void;
  placeholder?: string;
  initialValue?: string;
  tone?: Tone;
  /** Show a label above the input. */
  label?: string;
  /** If true, clears the input after a pick. Default: true. */
  clearOnPick?: boolean;
  /** Auto-focus on mount. */
  autoFocus?: boolean;
  /** Compact (smaller padding/text) for header bars. */
  compact?: boolean;
  className?: string;
};

export function TickerSearchInput({
  onPick,
  placeholder = "Search ticker, name, or sector",
  initialValue = "",
  tone = "violet",
  label,
  clearOnPick = true,
  autoFocus = false,
  compact = false,
  className,
}: Props) {
  const [value, setValue] = useState(initialValue);
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  // Debounced search
  useEffect(() => {
    const q = value.trim();
    if (!q) {
      setResults([]);
      return;
    }
    const t = setTimeout(async () => {
      try {
        const list = await stocksApi.search(q);
        setResults(list);
        setHighlight(0);
      } catch {
        setResults([]);
      }
    }, 150);
    return () => clearTimeout(t);
  }, [value]);

  // Close on outside click
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const submit = (sym?: string) => {
    const v = (sym ?? value).trim().toUpperCase();
    if (!v) return;
    onPick(v);
    if (clearOnPick) setValue("");
    setOpen(false);
  };

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || results.length === 0) {
      if (e.key === "Enter") submit();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      submit(results[highlight]?.symbol);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const focusBorder = FOCUS_BORDER[tone];
  const accentText = HIGHLIGHT_TEXT[tone];
  const padding = compact ? "pl-8 pr-2 py-1.5" : "pl-9 pr-3 py-2";

  return (
    <div ref={wrapperRef} className={cn("relative", className)}>
      {label && (
        <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">{label}</div>
      )}
      <div className="relative">
        <Search size={compact ? 12 : 14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
        <input
          autoFocus={autoFocus}
          value={value}
          onChange={(e) => { setValue(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
          placeholder={placeholder}
          maxLength={40}
          className={cn(
            "w-full bg-bg-base border border-bg-border rounded-md text-sm focus:outline-none transition-colors",
            padding,
            focusBorder,
          )}
        />
        {open && results.length > 0 && (
          <ul className="absolute z-30 mt-1 w-full max-h-72 overflow-y-auto bg-bg-card border border-bg-border rounded-md shadow-xl">
            {results.map((s, i) => (
              <li key={s.symbol}>
                <button
                  type="button"
                  onMouseEnter={() => setHighlight(i)}
                  onClick={() => submit(s.symbol)}
                  className={cn(
                    "w-full px-3 py-2 text-left text-sm flex items-center gap-3 transition-colors",
                    i === highlight ? "bg-bg-card2" : "hover:bg-bg-card2/60",
                  )}
                >
                  <span className={cn("font-mono font-bold w-12 shrink-0", accentText)}>
                    {s.symbol}
                  </span>
                  <span className="flex-1 truncate text-text-primary">{s.name}</span>
                  {s.sector && (
                    <span className="text-[10px] text-text-muted uppercase tracking-wider shrink-0">
                      {s.sector}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
