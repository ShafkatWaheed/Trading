"use client";

import { ShieldCheck, ShieldAlert, Pause, ThumbsUp, ThumbsDown } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

function verdictStyle(verdict: string): {
  bg: string; border: string; accent: string; iconBg: string;
  icon: LucideIcon; label: string; glow: string;
} {
  const v = verdict.toLowerCase();
  if (v.includes("strong buy")) {
    return {
      bg: "from-accent-green/10 to-transparent",
      border: "border-l-accent-green/60",
      accent: "text-accent-greenSoft",
      iconBg: "bg-accent-green/15",
      icon: ThumbsUp,
      label: "Strong Buy",
      glow: "card-glow-green",
    };
  }
  if (v.includes("buy")) {
    return {
      bg: "from-accent-green/8 to-transparent",
      border: "border-l-accent-green/50",
      accent: "text-accent-greenSoft",
      iconBg: "bg-accent-green/15",
      icon: ThumbsUp,
      label: "Buy",
      glow: "card-glow-green",
    };
  }
  if (v.includes("strong sell")) {
    return {
      bg: "from-accent-red/10 to-transparent",
      border: "border-l-accent-red/60",
      accent: "text-accent-redSoft",
      iconBg: "bg-accent-red/15",
      icon: ThumbsDown,
      label: "Strong Sell",
      glow: "card-glow-amber",
    };
  }
  if (v.includes("sell")) {
    return {
      bg: "from-accent-red/8 to-transparent",
      border: "border-l-accent-red/50",
      accent: "text-accent-redSoft",
      iconBg: "bg-accent-red/15",
      icon: ThumbsDown,
      label: "Sell",
      glow: "card-glow-amber",
    };
  }
  return {
    bg: "from-accent-amber/8 to-transparent",
    border: "border-l-accent-amber/50",
    accent: "text-accent-amber",
    iconBg: "bg-accent-amber/15",
    icon: Pause,
    label: verdict,
    glow: "card-glow-amber",
  };
}

type Props = {
  symbol: string;
  name?: string | null;
  sector?: string | null;
  verdict: string;
  confidence: string;
  riskRating: number;
};

export function VerdictBanner({ symbol, name, sector, verdict, confidence, riskRating }: Props) {
  const s = verdictStyle(verdict);
  const Icon = s.icon;
  const RiskIcon = riskRating <= 2 ? ShieldCheck : ShieldAlert;
  const riskColor = riskRating <= 2
    ? "text-accent-greenSoft"
    : riskRating >= 4 ? "text-accent-redSoft" : "text-accent-amber";
  const riskLabel = riskRating <= 2 ? "Low" : riskRating >= 4 ? "High" : "Moderate";

  return (
    <div className={cn(
      "card relative overflow-hidden border-l-[3px]",
      s.border, s.glow,
    )}>
      <div className={cn("absolute inset-0 bg-gradient-to-br pointer-events-none", s.bg)} />
      <div className="relative p-6 flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="text-3xl font-semibold tracking-tight">{symbol}</h2>
            {sector && <span className="badge-zinc">{sector}</span>}
          </div>
          {name && <p className="text-text-secondary mt-1.5 text-sm">{name}</p>}

          <div className="flex items-center gap-2 mt-4 pt-4 border-t border-bg-divider">
            <RiskIcon size={13} className={riskColor} strokeWidth={2.4} />
            <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">Risk</span>
            <span className={cn("text-[12px] font-semibold tabular-nums", riskColor)}>
              {riskRating}/5 · {riskLabel}
            </span>
          </div>
        </div>

        <div className="text-right shrink-0 flex flex-col items-end gap-2">
          <div className={cn(
            "w-12 h-12 rounded-xl grid place-items-center ring-1 ring-inset ring-white/5",
            s.iconBg,
          )}>
            <Icon size={22} className={s.accent} strokeWidth={2.4} />
          </div>
          <div>
            <div className={cn("text-2xl sm:text-3xl font-semibold tracking-tight", s.accent)}>
              {s.label}
            </div>
            <div className="text-[11px] text-text-muted mt-0.5">
              {confidence} confidence
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
