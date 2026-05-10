"use client";

import type { TradingImplication } from "@/lib/api/types";
import { Lightbulb } from "lucide-react";
import { cn } from "@/lib/utils";

function dot(tone: TradingImplication["tone"]) {
  switch (tone) {
    case "red": return "bg-accent-redSoft shadow-[0_0_8px_rgba(248,113,113,0.5)]";
    case "amber": return "bg-accent-amber shadow-[0_0_8px_rgba(245,158,11,0.5)]";
    case "green": return "bg-accent-greenSoft shadow-[0_0_8px_rgba(74,222,128,0.4)]";
  }
}

export function ImplicationsList({ items }: { items: TradingImplication[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="card p-6">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-7 h-7 rounded-lg bg-accent-amber/10 grid place-items-center ring-1 ring-inset ring-white/5">
          <Lightbulb size={14} className="text-accent-amber" strokeWidth={2.4} />
        </div>
        <h3 className="text-sm font-semibold tracking-tight">Trading Implications</h3>
        <span className="ml-auto text-[10px] uppercase tracking-wider text-text-muted">
          {items.length} signal{items.length === 1 ? "" : "s"}
        </span>
      </div>
      <ul className="space-y-3">
        {items.map((it, i) => (
          <li key={i} className="flex items-start gap-3 text-[13px] leading-relaxed">
            <span className={cn("w-1.5 h-1.5 rounded-full mt-1.5 shrink-0", dot(it.tone))} />
            <span className="text-text-secondary">{it.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
