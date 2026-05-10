"use client";

import Link from "next/link";
import type { DisruptionTheme } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

function intensityTone(i: DisruptionTheme["intensity"]) {
  switch (i) {
    case "HIGH":
      return "bg-accent-red/10 text-accent-redSoft border-accent-red/40";
    case "MEDIUM":
      return "bg-accent-amber/10 text-accent-amber border-accent-amber/40";
    case "EMERGING":
    default:
      return "bg-accent-violet/10 text-accent-violet border-accent-violet/40";
  }
}

function ThemeCard({ t }: { t: DisruptionTheme }) {
  return (
    <div className="card p-5 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-2xl">{t.icon}</span>
          <h4 className="text-sm font-semibold truncate">{t.name}</h4>
        </div>
        <span className={cn("badge shrink-0", intensityTone(t.intensity))}>{t.intensity}</span>
      </div>

      {t.headline && (
        <p className="text-xs text-text-secondary leading-relaxed">{t.headline}</p>
      )}

      {t.tickers_benefit.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-accent-greenSoft mb-1.5">
            Beneficiaries
          </div>
          <div className="flex flex-wrap gap-1.5">
            {t.tickers_benefit.map((sym) => (
              <Link
                key={sym}
                href={`/deep-dive/${sym}`}
                className="badge bg-accent-green/10 text-accent-greenSoft border-accent-green/30 hover:bg-accent-green/20 font-mono"
              >
                {sym}
              </Link>
            ))}
          </div>
          {t.sectors_benefit.length > 0 && (
            <div className="text-[11px] text-text-muted mt-1.5">
              {t.sectors_benefit.join(" · ")}
            </div>
          )}
        </div>
      )}

      {t.tickers_risk.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-accent-redSoft mb-1.5">
            At Risk
          </div>
          <div className="flex flex-wrap gap-1.5">
            {t.tickers_risk.map((sym) => (
              <Link
                key={sym}
                href={`/deep-dive/${sym}`}
                className="badge bg-accent-red/10 text-accent-redSoft border-accent-red/30 hover:bg-accent-red/20 font-mono"
              >
                {sym}
              </Link>
            ))}
          </div>
          {t.sectors_risk.length > 0 && (
            <div className="text-[11px] text-text-muted mt-1.5">
              {t.sectors_risk.join(" · ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function DisruptionThemes({ themes, loading }: { themes?: DisruptionTheme[]; loading?: boolean }) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-48" />)}
      </div>
    );
  }

  if (!themes || themes.length === 0) {
    return (
      <div className="card p-5 text-text-muted text-sm flex items-center gap-2">
        <Sparkles size={14} />
        No disruption themes available.
      </div>
    );
  }

  // Intensity summary banner
  const counts = { HIGH: 0, MEDIUM: 0, EMERGING: 0 } as Record<string, number>;
  themes.forEach((t) => { counts[t.intensity] = (counts[t.intensity] || 0) + 1; });

  const dominant = counts.HIGH >= 3 ? "Active" : counts.HIGH >= 1 ? "Moderate" : "Calm";
  const tone =
    dominant === "Active"
      ? { color: "text-accent-redSoft", border: "border-accent-red/40", bg: "bg-accent-red/5", note: "Multiple high-intensity disruption themes — sector winners and losers diverging fast." }
      : dominant === "Moderate"
      ? { color: "text-accent-amber", border: "border-accent-amber/40", bg: "bg-accent-amber/5", note: "Some disruption underway — selective opportunities in beneficiaries." }
      : { color: "text-accent-greenSoft", border: "border-accent-green/40", bg: "bg-accent-green/5", note: "No urgent disruption pressures — broad strategies still work." };

  return (
    <div className="space-y-4">
      <div className={cn("card p-4 border", tone.border, tone.bg, "flex items-center justify-between flex-wrap gap-3")}>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Disruption Intensity</div>
          <div className={cn("text-xl font-bold mt-0.5", tone.color)}>{dominant}</div>
        </div>
        <div className="text-right">
          <div className="text-sm text-text-secondary">{tone.note}</div>
          <div className="text-xs text-text-muted mt-0.5">
            {counts.HIGH} high · {counts.MEDIUM} medium · {counts.EMERGING} emerging
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {themes.map((t, i) => <ThemeCard key={i} t={t} />)}
      </div>
    </div>
  );
}
