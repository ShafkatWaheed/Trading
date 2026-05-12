"use client";

import { useEffect, useState } from "react";
import { Bookmark, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DiscoverFilters } from "./filter-bar";
import type { SortKey } from "./sort-selector";

const KEY = "discover.presets.v1";

export type Preset = {
  id: string;
  name: string;
  filters: DiscoverFilters;
  sort: SortKey;
  min_score: number;
  period: string;
  scope: "watchlist" | "all";
  regime_adjusted: boolean;
};

function load(): Preset[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Preset[]) : [];
  } catch {
    return [];
  }
}

function save(ps: Preset[]): void {
  try { localStorage.setItem(KEY, JSON.stringify(ps)); } catch {}
}

type Props = {
  current: Omit<Preset, "id" | "name">;
  onLoad: (p: Preset) => void;
};

export function SavedPresets({ current, onLoad }: Props) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");

  useEffect(() => {
    setPresets(load());
  }, []);

  const handleSave = () => {
    const n = name.trim();
    if (!n) return;
    const next: Preset[] = [
      ...presets,
      { id: crypto.randomUUID(), name: n, ...current },
    ];
    setPresets(next); save(next);
    setName(""); setNaming(false);
  };

  const handleDelete = (id: string) => {
    const next = presets.filter((p) => p.id !== id);
    setPresets(next); save(next);
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <Bookmark size={13} className="text-text-muted shrink-0" strokeWidth={2.4} />
      <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold shrink-0">
        Presets
      </span>

      {presets.map((p) => (
        <div key={p.id} className="inline-flex items-center bg-bg-base border border-bg-border rounded-md overflow-hidden">
          <button
            onClick={() => onLoad(p)}
            className="px-2.5 py-1 text-[11px] font-medium hover:bg-bg-card2 transition-colors"
            title={`Period ${p.period} · Min ${p.min_score} · Sort ${p.sort}`}
          >
            {p.name}
          </button>
          <button
            onClick={() => handleDelete(p.id)}
            className="px-1.5 py-1 text-text-muted hover:text-accent-redSoft hover:bg-accent-red/10 transition-colors"
            title="Delete preset"
            aria-label={`Delete preset ${p.name}`}
          >
            <X size={11} />
          </button>
        </div>
      ))}

      {naming ? (
        <form onSubmit={(e) => { e.preventDefault(); handleSave(); }} className="inline-flex items-center gap-1">
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value.slice(0, 24))}
            placeholder="preset name"
            className="bg-bg-base border border-accent-amber/40 rounded-md px-2 py-1 text-[11px] w-32 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!name.trim()}
            className="text-[10px] uppercase tracking-wider font-semibold text-accent-amber hover:text-accent-amberSoft disabled:opacity-40 px-2 py-1"
          >
            Save
          </button>
          <button
            type="button"
            onClick={() => { setNaming(false); setName(""); }}
            className="text-[10px] uppercase tracking-wider text-text-muted hover:text-text-primary px-2 py-1"
          >
            Cancel
          </button>
        </form>
      ) : (
        <button
          onClick={() => setNaming(true)}
          className={cn(
            "inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium",
            "border border-dashed border-bg-borderHi text-text-muted hover:text-text-primary hover:border-accent-amber/40 transition-colors"
          )}
        >
          <Plus size={11} /> Save current
        </button>
      )}
    </div>
  );
}
