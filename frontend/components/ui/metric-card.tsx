"use client";

import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

type Tone = "green" | "red" | "amber" | "blue" | "violet" | "cyan" | "pink" | "neutral";

const TONE: Record<Tone, string> = {
  green:   "text-accent-greenSoft",
  red:     "text-accent-redSoft",
  amber:   "text-accent-amber",
  blue:    "text-accent-blue",
  violet:  "text-accent-violet",
  cyan:    "text-accent-cyan",
  pink:    "text-accent-pink",
  neutral: "text-text-primary",
};

type Props = {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
  align?: "left" | "center";
  size?: "sm" | "md" | "lg";
  className?: string;
};

const SIZES: Record<NonNullable<Props["size"]>, { value: string; label: string }> = {
  sm: { value: "text-base", label: "text-[10px]" },
  md: { value: "text-xl", label: "text-[10px]" },
  lg: { value: "text-2xl", label: "text-[11px]" },
};

export function MetricCard({
  label,
  value,
  hint,
  tone = "neutral",
  icon,
  align = "left",
  size = "md",
  className,
}: Props) {
  const valueTone = TONE[tone];
  const sz = SIZES[size];
  const center = align === "center";

  return (
    <div className={cn(
      "card p-4 transition-colors hover:border-bg-borderHi",
      center && "text-center",
      className,
    )}>
      <div className={cn(
        "flex items-center gap-1.5",
        center && "justify-center",
        sz.label, "uppercase tracking-wider text-text-muted font-medium",
      )}>
        {icon && <span className="opacity-80">{icon}</span>}
        <span>{label}</span>
      </div>
      <div className={cn(
        "font-semibold tabular-nums tracking-tight mt-1",
        sz.value, valueTone,
      )}>
        {value}
      </div>
      {hint != null && (
        <div className="text-[10px] text-text-muted mt-1 leading-snug">{hint}</div>
      )}
    </div>
  );
}
