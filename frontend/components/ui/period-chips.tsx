"use client";

import { cn } from "@/lib/utils";

export const PERIODS = ["1D", "1W", "1M", "3M", "6M", "1Y"];

type Tone = "blue" | "amber" | "violet" | "cyan" | "green" | "red" | "pink";

type Props = {
  value: string;
  onChange: (period: string) => void;
  periods?: string[];
  accent?: Tone;
  size?: "sm" | "md";
};

const ACCENT: Record<Tone, { active: string; activeBorder: string }> = {
  blue:   { active: "text-accent-blue bg-accent-blue/15",      activeBorder: "border-accent-blue/40" },
  amber:  { active: "text-accent-amber bg-accent-amber/15",    activeBorder: "border-accent-amber/40" },
  violet: { active: "text-accent-violet bg-accent-violet/15",  activeBorder: "border-accent-violet/40" },
  cyan:   { active: "text-accent-cyan bg-accent-cyan/15",      activeBorder: "border-accent-cyan/40" },
  green:  { active: "text-accent-greenSoft bg-accent-green/15",activeBorder: "border-accent-green/40" },
  red:    { active: "text-accent-redSoft bg-accent-red/15",    activeBorder: "border-accent-red/40" },
  pink:   { active: "text-accent-pink bg-accent-pink/15",      activeBorder: "border-accent-pink/40" },
};

export function PeriodChips({ value, onChange, periods = PERIODS, accent = "blue", size = "md" }: Props) {
  const tone = ACCENT[accent];
  const pad = size === "sm" ? "h-6 px-2 text-[10px]" : "h-7 px-2.5 text-[11px]";
  return (
    <div className="inline-flex items-center gap-0.5 p-0.5 bg-bg-base border border-bg-border rounded-md">
      {periods.map((p) => (
        <button
          key={p}
          onClick={() => onChange(p)}
          className={cn(
            "rounded-[4px] font-mono font-semibold transition-all duration-150",
            pad,
            value === p
              ? cn(tone.active, tone.activeBorder, "border")
              : "text-text-muted hover:text-text-primary hover:bg-bg-card border border-transparent",
          )}
        >
          {p}
        </button>
      ))}
    </div>
  );
}
