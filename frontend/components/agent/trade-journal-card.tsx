"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookText, Plus, X, ArrowUpRight, Loader2,
  TrendingUp, TrendingDown, Minus,
} from "lucide-react";
import { journalApi } from "@/lib/api/endpoints";
import type { JournalHolding, JournalPosition } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatCurrency } from "@/lib/utils";

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function pnlTone(pnl: number | null | undefined): string {
  if (pnl == null) return "text-text-muted";
  if (pnl > 0) return "text-accent-greenSoft";
  if (pnl < 0) return "text-accent-redSoft";
  return "text-text-secondary";
}

export function TradeJournalCard() {
  const qc = useQueryClient();
  const { data: holdingsData, isLoading: hl } = useQuery({
    queryKey: ["journal", "holdings"],
    queryFn: () => journalApi.holdings(),
    staleTime: 30_000,
  });
  const { data: positions, isLoading: pl } = useQuery({
    queryKey: ["journal", "positions"],
    queryFn: () => journalApi.positions({ limit: 50 }),
    staleTime: 30_000,
  });

  const [adding, setAdding] = useState(false);
  const [closing, setClosing] = useState<number | null>(null);

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["journal"] });
    qc.invalidateQueries({ queryKey: ["gap-finder"] });
  };

  const holdings = holdingsData?.holdings ?? [];
  const open = (positions?.positions ?? []).filter((p) => p.status === "open");
  const recentClosed = (positions?.positions ?? []).filter((p) => p.status === "closed").slice(0, 5);

  return (
    <section className="card-subtle p-6 relative overflow-hidden">
      <div
        className="absolute inset-x-0 top-0 h-24 pointer-events-none opacity-50"
        style={{ background: "radial-gradient(ellipse 60% 100% at 30% 0%, rgba(59, 130, 246, 0.10) 0%, transparent 70%)" }}
      />

      <div className="relative">
        <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
          <div className="flex items-center gap-2">
            <BookText size={16} className="text-accent-blue" />
            <h3 className="text-base font-semibold">Your Trade Journal</h3>
            <span className="text-[10px] uppercase tracking-wider text-text-muted">
              {holdings.length} holdings · {open.length} open · {recentClosed.length} recent closed
            </span>
          </div>
          <button
            onClick={() => setAdding(true)}
            className="inline-flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-md
                       bg-accent-blue/10 hover:bg-accent-blue/20 text-accent-blue border border-accent-blue/30
                       transition-colors"
          >
            <Plus size={12} /> Log a trade
          </button>
        </div>

        {/* Current holdings — aggregated per symbol */}
        <div className="mb-5">
          <div className="font-mono text-[10px] tracking-[0.22em] uppercase text-text-muted mb-2">
            Current holdings
          </div>
          {hl ? (
            <Skeleton className="h-20 w-full" />
          ) : holdings.length === 0 ? (
            <div className="text-[12px] text-text-muted italic py-3">
              No positions logged yet. Click "Log a trade" to start — the AI Gap Finder below will
              read your holdings and recommend what to buy / sell / hold.
            </div>
          ) : (
            <ul className="divide-y divide-bg-divider">
              {holdings.map((h: JournalHolding) => (
                <HoldingRow key={h.symbol} holding={h} />
              ))}
            </ul>
          )}
        </div>

        {/* Open positions (lots) — collapsible-ish */}
        {open.length > 0 && (
          <details className="mb-3 group">
            <summary className="cursor-pointer text-[11px] text-text-muted hover:text-text-primary list-none flex items-center gap-1.5">
              <span className="font-mono uppercase tracking-wider">
                Open lots · {open.length}
              </span>
              <ArrowUpRight size={10} className="rotate-90 group-open:rotate-[135deg] transition-transform" />
            </summary>
            <div className="mt-2 space-y-1">
              {open.map((p: JournalPosition) => (
                <PositionRow
                  key={p.id}
                  position={p}
                  onClose={() => setClosing(p.id)}
                />
              ))}
            </div>
          </details>
        )}

        {/* Recently closed */}
        {recentClosed.length > 0 && (
          <details className="group">
            <summary className="cursor-pointer text-[11px] text-text-muted hover:text-text-primary list-none flex items-center gap-1.5">
              <span className="font-mono uppercase tracking-wider">
                Recently closed · {recentClosed.length}
              </span>
              <ArrowUpRight size={10} className="rotate-90 group-open:rotate-[135deg] transition-transform" />
            </summary>
            <div className="mt-2 space-y-1">
              {recentClosed.map((p: JournalPosition) => (
                <PositionRow key={p.id} position={p} />
              ))}
            </div>
          </details>
        )}
      </div>

      {/* Modals */}
      {adding && (
        <AddTradeModal onClose={() => setAdding(false)} onSaved={invalidateAll} />
      )}
      {closing != null && (
        <CloseTradeModal
          positionId={closing}
          position={open.find((p) => p.id === closing) ?? null}
          onClose={() => setClosing(null)}
          onSaved={invalidateAll}
        />
      )}
    </section>
  );
}


function HoldingRow({ holding }: { holding: JournalHolding }) {
  return (
    <li className="flex items-center justify-between gap-3 py-2 text-sm">
      <div className="flex items-baseline gap-3 min-w-0">
        <Link
          href={`/deep-dive/${encodeURIComponent(holding.symbol)}`}
          className="font-mono font-bold text-[14px] text-text-primary hover:text-accent-blue"
        >
          ${holding.symbol}
        </Link>
        <span className="text-text-muted text-[11px] tabular-nums">
          {holding.shares} sh @ ${holding.avg_entry_price?.toFixed(2)}
        </span>
        {holding.lots > 1 && (
          <span className="text-[9px] uppercase tracking-wider text-text-dim">
            {holding.lots} lots
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 text-[12px] shrink-0">
        <span className="text-text-secondary font-mono tabular-nums">
          {holding.total_cost != null ? formatCurrency(holding.total_cost) : "—"}
        </span>
      </div>
    </li>
  );
}


function PositionRow({ position, onClose }: { position: JournalPosition; onClose?: () => void }) {
  const isOpen = position.status === "open";
  return (
    <div className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-bg-base/40">
      <div className="flex items-baseline gap-2 min-w-0 text-[12px]">
        <span className="font-mono font-semibold text-text-primary">${position.symbol}</span>
        <span className="text-text-muted tabular-nums">
          {position.shares} @ ${position.entry_price?.toFixed(2)}
        </span>
        <span className="text-[10px] text-text-muted">{position.entry_date}</span>
        {position.thesis && (
          <span className="text-text-secondary italic truncate text-[11px]">
            · {position.thesis}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {!isOpen && (
          <span className={cn("text-[11px] font-mono tabular-nums font-semibold", pnlTone(position.pnl))}>
            {fmtPct(position.pnl_percent)}
          </span>
        )}
        {isOpen && onClose && (
          <button
            onClick={onClose}
            className="text-[10px] px-2 py-0.5 rounded border border-bg-borderHi hover:border-accent-redSoft hover:text-accent-redSoft text-text-muted"
          >
            Close
          </button>
        )}
      </div>
    </div>
  );
}


// ── Add trade modal ─────────────────────────────────────────────────

function AddTradeModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [symbol, setSymbol] = useState("");
  const [price, setPrice] = useState("");
  const [shares, setShares] = useState("");
  const [thesis, setThesis] = useState("");

  const mut = useMutation({
    mutationFn: () => journalApi.open({
      symbol: symbol.toUpperCase().trim(),
      entry_price: parseFloat(price),
      shares: parseInt(shares, 10),
      thesis,
    }),
    onSuccess: () => { onSaved(); onClose(); },
  });

  const canSubmit = symbol && price && shares && !mut.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="card p-6 w-full max-w-md mx-4 relative">
        <button onClick={onClose} className="absolute top-3 right-3 text-text-muted hover:text-text-primary">
          <X size={16} />
        </button>
        <h3 className="text-base font-semibold mb-1">Log a buy</h3>
        <p className="text-[11px] text-text-muted mb-4">
          The AI Gap Finder reads your open positions to decide what to sell, hold, or buy next.
        </p>

        <div className="space-y-3">
          <Field label="Symbol">
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="e.g. NVDA"
              className="w-full bg-bg-base border border-bg-border rounded-md px-3 py-2 text-sm font-mono uppercase focus:outline-none focus:border-accent-blue/60"
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Entry price ($)">
              <input
                type="number" step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="120.00"
                className="w-full bg-bg-base border border-bg-border rounded-md px-3 py-2 text-sm tabular-nums focus:outline-none focus:border-accent-blue/60"
              />
            </Field>
            <Field label="Shares">
              <input
                type="number"
                value={shares}
                onChange={(e) => setShares(e.target.value)}
                placeholder="50"
                className="w-full bg-bg-base border border-bg-border rounded-md px-3 py-2 text-sm tabular-nums focus:outline-none focus:border-accent-blue/60"
              />
            </Field>
          </div>
          <Field label="Thesis (optional — why you bought)">
            <textarea
              value={thesis}
              onChange={(e) => setThesis(e.target.value)}
              rows={2}
              placeholder="AI infra duopoly + estimate momentum"
              className="w-full bg-bg-base border border-bg-border rounded-md px-3 py-2 text-sm focus:outline-none focus:border-accent-blue/60"
            />
          </Field>
        </div>

        {mut.isError && (
          <div className="mt-3 text-[12px] text-accent-redSoft">
            {(mut.error as Error).message}
          </div>
        )}

        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onClose}
            className="text-[12px] px-3 py-1.5 rounded-md border border-bg-borderHi text-text-secondary hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            onClick={() => canSubmit && mut.mutate()}
            disabled={!canSubmit}
            className={cn(
              "text-[12px] px-3 py-1.5 rounded-md inline-flex items-center gap-1.5 border",
              canSubmit
                ? "bg-accent-blue/10 hover:bg-accent-blue/20 text-accent-blue border-accent-blue/30"
                : "bg-bg-card2 text-text-muted border-bg-border cursor-not-allowed",
            )}
          >
            {mut.isPending && <Loader2 size={12} className="animate-spin" />}
            {mut.isPending ? "Saving" : "Save trade"}
          </button>
        </div>
      </div>
    </div>
  );
}


function CloseTradeModal({
  positionId, position, onClose, onSaved,
}: {
  positionId: number;
  position: JournalPosition | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [price, setPrice] = useState("");
  const [notes, setNotes] = useState("");

  const mut = useMutation({
    mutationFn: () => journalApi.close(positionId, {
      exit_price: parseFloat(price),
      notes,
    }),
    onSuccess: () => { onSaved(); onClose(); },
  });

  if (!position) return null;
  const canSubmit = price && !mut.isPending;
  const previewPct = price && position.entry_price
    ? ((parseFloat(price) - position.entry_price) / position.entry_price) * 100
    : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="card p-6 w-full max-w-md mx-4 relative">
        <button onClick={onClose} className="absolute top-3 right-3 text-text-muted hover:text-text-primary">
          <X size={16} />
        </button>
        <h3 className="text-base font-semibold mb-1">Close ${position.symbol}</h3>
        <p className="text-[11px] text-text-muted mb-4">
          {position.shares} shares bought at ${position.entry_price?.toFixed(2)} on {position.entry_date}
        </p>

        <div className="space-y-3">
          <Field label="Exit price ($)">
            <input
              type="number" step="0.01"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="current market price"
              className="w-full bg-bg-base border border-bg-border rounded-md px-3 py-2 text-sm tabular-nums focus:outline-none focus:border-accent-blue/60"
            />
          </Field>
          {previewPct != null && (
            <div className={cn(
              "text-[12px] font-mono tabular-nums",
              previewPct >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft",
            )}>
              P&L: {previewPct >= 0 ? "+" : ""}{previewPct.toFixed(2)}%
            </div>
          )}
          <Field label="Notes (optional)">
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="why you closed"
              className="w-full bg-bg-base border border-bg-border rounded-md px-3 py-2 text-sm focus:outline-none focus:border-accent-blue/60"
            />
          </Field>
        </div>

        {mut.isError && (
          <div className="mt-3 text-[12px] text-accent-redSoft">
            {(mut.error as Error).message}
          </div>
        )}

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="text-[12px] px-3 py-1.5 rounded-md border border-bg-borderHi text-text-secondary hover:text-text-primary">
            Cancel
          </button>
          <button
            onClick={() => canSubmit && mut.mutate()}
            disabled={!canSubmit}
            className={cn(
              "text-[12px] px-3 py-1.5 rounded-md inline-flex items-center gap-1.5 border",
              canSubmit
                ? "bg-accent-red/10 hover:bg-accent-red/20 text-accent-redSoft border-accent-red/30"
                : "bg-bg-card2 text-text-muted border-bg-border cursor-not-allowed",
            )}
          >
            {mut.isPending && <Loader2 size={12} className="animate-spin" />}
            {mut.isPending ? "Closing" : "Close position"}
          </button>
        </div>
      </div>
    </div>
  );
}


function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wider text-text-muted mb-1 block">
        {label}
      </span>
      {children}
    </label>
  );
}
