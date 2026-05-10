"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { FileText, Loader2, ChevronDown, ChevronUp, ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";
import { earningsApi } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

const MAX_CHARS = 12_000;

function caseTone(c?: string) {
  if (c === "strengthens") return { color: "text-accent-greenSoft", icon: ArrowUpRight, label: "Investment case strengthens" };
  if (c === "weakens")     return { color: "text-accent-redSoft",   icon: ArrowDownRight, label: "Investment case weakens" };
  return                          { color: "text-text-secondary",   icon: Minus, label: "Investment case unchanged" };
}

export function EarningsExplainer({ symbol }: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");

  const m = useMutation({
    mutationFn: () => earningsApi.explain(symbol, text),
  });

  const tone = caseTone(m.data?.case_change);
  const ToneIcon = tone.icon;

  return (
    <section className="card p-6">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-accent-cyan" />
          <h3 className="text-base font-semibold">Earnings Report Explainer</h3>
          <span className="text-[10px] uppercase tracking-wider text-text-muted">paste text · Claude</span>
        </div>
        {open ? <ChevronUp size={16} className="text-text-muted" /> : <ChevronDown size={16} className="text-text-muted" />}
      </button>

      {open && (
        <div className="mt-4 space-y-4">
          <div>
            <label className="text-xs uppercase tracking-wider text-text-muted">
              Paste earnings release / transcript / press text for {symbol}
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, MAX_CHARS))}
              rows={8}
              placeholder={`Paste the full earnings text here. Up to ${MAX_CHARS.toLocaleString()} characters.`}
              className="mt-1.5 w-full bg-bg-base border border-bg-border rounded-md px-3 py-2 text-sm font-mono leading-relaxed focus:outline-none focus:border-accent-cyan/60"
            />
            <div className="flex items-center justify-between mt-1.5 text-[10px] text-text-muted">
              <span>{text.length.toLocaleString()} / {MAX_CHARS.toLocaleString()} chars</span>
              <button
                onClick={() => m.mutate()}
                disabled={!text.trim() || m.isPending}
                className="bg-accent-cyan/10 border border-accent-cyan/40 hover:bg-accent-cyan/20 text-accent-cyan px-4 py-1.5 rounded-md text-xs font-medium flex items-center gap-1.5 disabled:opacity-40"
              >
                {m.isPending && <Loader2 size={12} className="animate-spin" />}
                {m.isPending ? "Asking Claude…" : "Explain"}
              </button>
            </div>
          </div>

          {m.isError && (
            <p className="text-accent-redSoft text-sm">{(m.error as Error)?.message}</p>
          )}

          {m.data?.error && (
            <p className="text-accent-amber text-sm">{m.data.error}</p>
          )}

          {m.data && !m.data.error && (
            <div className="space-y-4 pt-2 border-t border-bg-border">
              {m.data.summary && (
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-1.5">Summary</div>
                  <p className="text-text-secondary text-sm leading-relaxed">{m.data.summary}</p>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {m.data.beats && m.data.beats.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wider text-accent-greenSoft mb-1.5 flex items-center gap-1">
                      <ArrowUpRight size={12} /> Beats
                    </div>
                    <ul className="space-y-1.5">
                      {m.data.beats.map((b, i) => (
                        <li key={i} className="text-sm text-text-secondary leading-relaxed">• {b}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {m.data.misses && m.data.misses.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wider text-accent-redSoft mb-1.5 flex items-center gap-1">
                      <ArrowDownRight size={12} /> Misses
                    </div>
                    <ul className="space-y-1.5">
                      {m.data.misses.map((b, i) => (
                        <li key={i} className="text-sm text-text-secondary leading-relaxed">• {b}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {m.data.guidance && (
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-1.5">Forward Guidance</div>
                  <p className="text-text-secondary text-sm leading-relaxed">{m.data.guidance}</p>
                </div>
              )}

              <div className={cn("flex items-start gap-2 p-3 rounded-md border bg-bg-base", "border-bg-border")}>
                <ToneIcon size={16} className={cn("mt-0.5", tone.color)} />
                <div className="flex-1">
                  <div className={cn("text-xs font-semibold uppercase tracking-wider", tone.color)}>{tone.label}</div>
                  {m.data.case_change_reason && (
                    <p className="text-text-secondary text-sm leading-relaxed mt-1">{m.data.case_change_reason}</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
