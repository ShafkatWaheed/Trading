"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X, Sparkles, Search } from "lucide-react";
import { watchlistApi, stocksApi } from "@/lib/api/endpoints";
import type { StockSearchResult } from "@/lib/api/types";

export function WatchlistManager() {
  const qc = useQueryClient();
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<StockSearchResult[]>([]);
  const [showDrop, setShowDrop] = useState(false);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  const { data: watchlist = [] } = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => watchlistApi.list(),
    staleTime: 30 * 1000,
  });

  // Debounced autocomplete fetch
  useEffect(() => {
    const q = input.trim();
    if (!q) {
      setSuggestions([]);
      return;
    }
    const t = setTimeout(async () => {
      try {
        const results = await stocksApi.search(q);
        setSuggestions(results);
      } catch {
        setSuggestions([]);
      }
    }, 150);
    return () => clearTimeout(t);
  }, [input]);

  // Close dropdown on outside click
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowDrop(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["watchlist"] });
    qc.invalidateQueries({ queryKey: ["discover"] });
  };

  const addMutation = useMutation({
    mutationFn: (symbol: string) => watchlistApi.add(symbol),
    onSuccess: (res) => {
      if (!res.ok) {
        setError(res.error || "Failed to add");
        return;
      }
      setError(null);
      setInput("");
      invalidate();
    },
    onError: (e: Error) => setError(e.message),
  });

  const removeMutation = useMutation({
    mutationFn: (symbol: string) => watchlistApi.remove(symbol),
    onSuccess: invalidate,
  });

  const top5Mutation = useMutation({
    mutationFn: () => watchlistApi.addTop5(),
    onSuccess: invalidate,
  });

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-accent-amber/10 grid place-items-center ring-1 ring-inset ring-white/5">
            <Sparkles size={13} className="text-accent-amber" strokeWidth={2.4} />
          </div>
          <h3 className="text-sm font-semibold tracking-tight">Watchlist</h3>
          <span className="badge-zinc">
            {watchlist.length} stock{watchlist.length === 1 ? "" : "s"}
          </span>
        </div>
        <button
          onClick={() => top5Mutation.mutate()}
          disabled={top5Mutation.isPending}
          className="btn btn-outline text-[11px] h-7 px-2.5 hover:border-accent-amber/40 hover:text-accent-amber"
        >
          {top5Mutation.isPending ? "Adding…" : "+ Add Top 5"}
        </button>
      </div>

      <form
        ref={wrapperRef}
        onSubmit={(e) => {
          e.preventDefault();
          const sym = input.trim().toUpperCase();
          if (sym) {
            addMutation.mutate(sym);
            setShowDrop(false);
          }
        }}
        className="relative flex items-center gap-2 mb-3"
      >
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
          <input
            value={input}
            onChange={(e) => { setInput(e.target.value); setShowDrop(true); }}
            onFocus={() => setShowDrop(true)}
            placeholder="Search by ticker, name, or sector"
            maxLength={40}
            className="w-full bg-bg-base border border-bg-border rounded-md pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-accent-amber/60"
          />
          {showDrop && suggestions.length > 0 && (
            <ul className="absolute z-20 mt-1 w-full max-h-64 overflow-y-auto bg-bg-card border border-bg-border rounded-md shadow-lg">
              {suggestions.map((s) => (
                <li key={s.symbol}>
                  <button
                    type="button"
                    onClick={() => {
                      addMutation.mutate(s.symbol);
                      setInput("");
                      setShowDrop(false);
                    }}
                    className="w-full px-3 py-2 text-left text-sm hover:bg-bg-card2 flex items-center gap-3"
                  >
                    <span className="font-mono font-bold text-accent-amber w-12 shrink-0">{s.symbol}</span>
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
        <button
          type="submit"
          disabled={!input.trim() || addMutation.isPending}
          className="bg-accent-amber/10 border border-accent-amber/40 hover:bg-accent-amber/20 text-accent-amber px-3 py-2 rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
        >
          <Plus size={14} />
          Add
        </button>
      </form>

      {error && (
        <p className="text-xs text-accent-redSoft mb-3">{error}</p>
      )}

      <div className="flex flex-wrap gap-1.5">
        {watchlist.length === 0 ? (
          <p className="text-xs text-text-muted">
            Empty. Search above or click <span className="text-text-secondary">+ Add Top 5</span> to seed it.
          </p>
        ) : (
          watchlist.map((w) => (
            <button
              key={w.symbol}
              onClick={() => removeMutation.mutate(w.symbol)}
              className="badge bg-bg-base border-bg-border text-text-secondary hover:border-accent-red/40 hover:text-accent-redSoft font-mono group"
              title="Click to remove"
            >
              {w.symbol}
              <X size={11} className="ml-1 opacity-50 group-hover:opacity-100" />
            </button>
          ))
        )}
      </div>
    </div>
  );
}
