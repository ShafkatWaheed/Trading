"use client";

import Link from "next/link";
import { Layers, X } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  selected: string[];
  onClear: () => void;
  onRemove: (sym: string) => void;
};

export function SelectionToolbar({ selected, onClear, onRemove }: Props) {
  if (selected.length === 0) return null;
  const tooMany = selected.length > 4;

  return (
    <div className="card p-3 border-l-4 border-accent-violet/50 flex items-center gap-3 flex-wrap">
      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
          Selected ({selected.length}){tooMany && <span className="text-accent-amber ml-1">· max 4 for compare</span>}
        </span>
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        {selected.map((s) => (
          <span
            key={s}
            className="inline-flex items-center bg-accent-violet/10 text-accent-violet border border-accent-violet/40 rounded-md px-2 py-0.5 text-[11px] font-mono font-bold"
          >
            {s}
            <button
              onClick={() => onRemove(s)}
              className="ml-1 opacity-70 hover:opacity-100"
              aria-label={`Remove ${s}`}
            >
              <X size={10} />
            </button>
          </span>
        ))}
      </div>

      <div className="ml-auto flex items-center gap-2">
        <button
          onClick={onClear}
          className="text-[11px] text-text-muted hover:text-text-primary"
        >
          Clear
        </button>
        <Link
          href={`/deep-dive/compare?symbols=${encodeURIComponent(selected.slice(0, 4).join(","))}`}
          className={cn(
            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-semibold transition-colors",
            "bg-accent-violet/10 text-accent-violet border border-accent-violet/40 hover:bg-accent-violet/20"
          )}
        >
          <Layers size={12} />
          Compare {Math.min(selected.length, 4)}
        </Link>
      </div>
    </div>
  );
}
