"use client";

import { useState } from "react";
import { ChevronDown, Info } from "lucide-react";
import { cn } from "@/lib/utils";

const FACTORS = [
  { name: "Volume", weight: "25%", desc: "Recent volume vs 20-day average" },
  { name: "Price",  weight: "25%", desc: "RSI momentum + trend + MACD direction" },
  { name: "Flow",   weight: "25%", desc: "Options put/call ratio + insider buying" },
  { name: "Risk/Reward", weight: "25%", desc: "Distance to support vs resistance" },
];

const RANGES = [
  { range: "80-100", label: "Excellent", tone: "text-accent-greenSoft" },
  { range: "60-79",  label: "Good",      tone: "text-accent-blue" },
  { range: "40-59",  label: "Fair",      tone: "text-accent-amber" },
  { range: "0-39",   label: "Poor",      tone: "text-accent-redSoft" },
];

export function ScoreExplainer() {
  const [open, setOpen] = useState(false);
  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full px-5 py-4 flex items-center justify-between text-sm hover:bg-bg-card2 transition-colors"
      >
        <span className="flex items-center gap-2">
          <Info size={14} className="text-accent-blue" />
          How Opportunity Scores Work
        </span>
        <ChevronDown size={14} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="px-5 pb-5 grid grid-cols-1 md:grid-cols-2 gap-6 text-sm border-t border-bg-border pt-5">
          <div>
            <h4 className="text-xs uppercase tracking-wider text-text-muted mb-2">
              Score Composition (each factor /25)
            </h4>
            <table className="w-full text-xs">
              <tbody>
                {FACTORS.map((f) => (
                  <tr key={f.name} className="border-b border-bg-border last:border-0">
                    <td className="py-2 pr-2 font-medium">{f.name}</td>
                    <td className="py-2 pr-2 text-accent-blue tabular-nums">{f.weight}</td>
                    <td className="py-2 text-text-secondary">{f.desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <h4 className="text-xs uppercase tracking-wider text-text-muted mb-2">
              Score Ranges
            </h4>
            <ul className="space-y-1.5 text-xs">
              {RANGES.map((r) => (
                <li key={r.range} className="flex items-center gap-3">
                  <span className="font-mono tabular-nums text-text-muted w-16">{r.range}</span>
                  <span className={cn("font-semibold", r.tone)}>{r.label}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
