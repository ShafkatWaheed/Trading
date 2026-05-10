"use client";

import Link from "next/link";
import { ArrowRight, Target } from "lucide-react";
import type { OpportunityCard as Op } from "@/lib/api/types";
import { cn } from "@/lib/utils";

function scoreColor(score: number) {
  if (score >= 80) return "text-accent-greenSoft";
  if (score >= 65) return "text-accent-amber";
  if (score >= 50) return "text-text-primary";
  return "text-text-secondary";
}

function labelTone(label: string) {
  const l = label.toLowerCase();
  if (l.includes("excellent") || l.includes("strong")) return "badge-green";
  if (l.includes("good")) return "badge-blue";
  if (l.includes("fair")) return "badge-amber";
  return "badge-zinc";
}

export function OpportunityCard({ op }: { op: Op }) {
  return (
    <Link
      href={`/deep-dive/${op.symbol}`}
      className="card card-hover p-5 flex flex-col gap-3 group"
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-lg font-semibold tracking-tight">{op.symbol}</span>
            <span className={labelTone(op.label)}>{op.label}</span>
          </div>
          {op.name && (
            <div className="text-text-secondary text-sm mt-0.5 truncate max-w-[14rem]">{op.name}</div>
          )}
        </div>
        <div className="text-right">
          <div className={cn("text-2xl font-semibold tabular-nums", scoreColor(op.score))}>
            {op.score.toFixed(0)}
          </div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Score</div>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs">
        <div className="text-text-secondary flex items-center gap-1.5">
          <Target size={12} /> {op.strategy}
        </div>
        {op.risk_reward_ratio && op.risk_reward_ratio > 0 && (
          <div className="text-text-secondary tabular-nums">RR {op.risk_reward_ratio.toFixed(1)}:1</div>
        )}
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-bg-border">
        <span className="text-xs text-text-muted">{op.sector || "—"}</span>
        <ArrowRight size={14} className="text-text-muted group-hover:text-accent-blue transition-colors" />
      </div>
    </Link>
  );
}
