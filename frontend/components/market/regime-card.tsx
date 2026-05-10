"use client";

import { TrendingUp, AlertTriangle, Activity } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  regime: string;
  explanation: string;
};

function regimeStyle(regime: string) {
  const r = regime.toLowerCase();
  if (r.includes("recession")) {
    return {
      icon: AlertTriangle,
      accent: "text-accent-red",
      iconBg: "bg-accent-red/10",
      stripe: "from-accent-red/40 via-accent-red/10 to-transparent",
      glow: "card-glow-amber",
      label: "Recession Warning",
    };
  }
  if (r.includes("volatil")) {
    return {
      icon: AlertTriangle,
      accent: "text-accent-amber",
      iconBg: "bg-accent-amber/10",
      stripe: "from-accent-amber/40 via-accent-amber/10 to-transparent",
      glow: "card-glow-amber",
      label: "High Volatility",
    };
  }
  return {
    icon: Activity,
    accent: "text-accent-blue",
    iconBg: "bg-accent-blue/10",
    stripe: "from-accent-blue/40 via-accent-blue/10 to-transparent",
    glow: "card-glow-blue",
    label: "Stable Conditions",
  };
}

export function RegimeCard({ regime, explanation }: Props) {
  const s = regimeStyle(regime);
  const Icon = s.icon;
  return (
    <div className={cn("relative card overflow-hidden", s.glow)}>
      {/* Top accent stripe */}
      <div className={cn("absolute inset-x-0 top-0 h-px bg-gradient-to-r", s.stripe)} />

      <div className="p-6 flex items-start gap-4">
        <div className={cn(
          "w-11 h-11 rounded-xl grid place-items-center shrink-0 ring-1 ring-inset ring-white/5",
          s.iconBg,
        )}>
          <Icon size={20} className={s.accent} strokeWidth={2.2} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-[0.12em] text-text-muted font-semibold mb-1">
            Market Regime · {s.label}
          </div>
          <h2 className="text-xl font-semibold tracking-tight text-text-primary">{regime}</h2>
          <p className="text-text-secondary text-[13px] mt-2 leading-relaxed">
            {explanation}
          </p>
        </div>
      </div>
    </div>
  );
}
