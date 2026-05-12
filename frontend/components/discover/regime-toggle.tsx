"use client";

import { useQuery } from "@tanstack/react-query";
import { Gauge } from "lucide-react";
import { marketApi } from "@/lib/api/endpoints";
import type { OpportunityCard, SubScores } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type Tone = "bullish" | "cautious_bullish" | "cautious" | "neutral" | "defensive";

// Weights per regime — they sum to 1. Default (neutral) gives an even quarter to each sub-score.
const WEIGHTS: Record<Tone, SubScores> = {
  bullish:          { volume: 0.20, price: 0.40, flow: 0.30, risk_reward: 0.10 },
  cautious_bullish: { volume: 0.20, price: 0.30, flow: 0.30, risk_reward: 0.20 },
  cautious:         { volume: 0.20, price: 0.20, flow: 0.20, risk_reward: 0.40 },
  defensive:        { volume: 0.15, price: 0.10, flow: 0.15, risk_reward: 0.60 },
  neutral:          { volume: 0.25, price: 0.25, flow: 0.25, risk_reward: 0.25 },
};

/** Compute a regime-adjusted score from the existing sub-scores. The original
 * `score` is on 0..100 from the backend's own weighting; we recompute on the
 * same scale using regime weights. */
export function regimeAdjustedScore(op: OpportunityCard, tone: Tone): number {
  const w = WEIGHTS[tone] ?? WEIGHTS.neutral;
  const s = op.sub_scores ?? { volume: 0, price: 0, flow: 0, risk_reward: 0 };
  const wsum = w.volume + w.price + w.flow + w.risk_reward;
  const blended =
    (s.volume * w.volume + s.price * w.price + s.flow * w.flow + s.risk_reward * w.risk_reward) / wsum;
  // sub_scores are 0..1; scale to 0..100
  return Math.round(blended * 100);
}

export function useMarketTone(): Tone {
  const { data } = useQuery({
    queryKey: ["market-takeaway"],
    queryFn: () => marketApi.takeaway(),
    staleTime: 10 * 60 * 1000,
  });
  return (data?.tone as Tone) || "neutral";
}

export function RegimeToggle({ enabled, onToggle }: { enabled: boolean; onToggle: (v: boolean) => void }) {
  const tone = useMarketTone();
  const label =
    tone === "bullish" || tone === "cautious_bullish" ? "Risk-On" :
    tone === "defensive" ? "Defensive" :
    tone === "cautious" ? "Cautious" :
    "Neutral";

  const dotColor =
    tone === "bullish" || tone === "cautious_bullish" ? "bg-accent-greenSoft" :
    tone === "defensive" ? "bg-accent-redSoft" :
    tone === "cautious" ? "bg-accent-amber" :
    "bg-text-dim";

  return (
    <button
      onClick={() => onToggle(!enabled)}
      title={
        enabled
          ? "Sub-scores are being re-weighted based on current market regime"
          : "Click to bias scoring toward the current market regime"
      }
      className={cn(
        "inline-flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[11px] font-medium border transition-colors",
        enabled
          ? "bg-accent-violet/10 text-accent-violet border-accent-violet/40"
          : "bg-bg-base text-text-secondary border-bg-border hover:border-bg-borderHi hover:text-text-primary"
      )}
    >
      <Gauge size={11} strokeWidth={2.4} />
      Adjust for regime
      <span className="flex items-center gap-1 pl-1 border-l border-current/30">
        <span className={cn("w-1.5 h-1.5 rounded-full", dotColor)} />
        <span className="text-[10px] uppercase tracking-wider">{label}</span>
      </span>
    </button>
  );
}
