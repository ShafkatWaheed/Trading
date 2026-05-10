"use client";

import { type LucideIcon } from "lucide-react";
import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "violet" | "amber" | "blue" | "cyan" | "green" | "pink";

const TONE: Record<Tone, { bg: string; text: string }> = {
  neutral: { bg: "bg-bg-card2",       text: "text-text-muted" },
  violet:  { bg: "bg-accent-violet/10", text: "text-accent-violet" },
  amber:   { bg: "bg-accent-amber/10",  text: "text-accent-amber" },
  blue:    { bg: "bg-accent-blue/10",   text: "text-accent-blue" },
  cyan:    { bg: "bg-accent-cyan/10",   text: "text-accent-cyan" },
  green:   { bg: "bg-accent-green/10",  text: "text-accent-greenSoft" },
  pink:    { bg: "bg-accent-pink/10",   text: "text-accent-pink" },
};

type Props = {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  tone?: Tone;
  className?: string;
};

export function EmptyState({ icon: Icon, title, description, action, tone = "neutral", className }: Props) {
  const t = TONE[tone];
  return (
    <div className={cn("card p-10 text-center flex flex-col items-center gap-3", className)}>
      <div className={cn("w-12 h-12 rounded-2xl grid place-items-center ring-1 ring-inset ring-white/5", t.bg)}>
        <Icon size={20} className={t.text} strokeWidth={2} />
      </div>
      <div>
        <p className="text-sm font-semibold text-text-primary">{title}</p>
        {description && (
          <p className="text-text-muted text-xs mt-1.5 max-w-md mx-auto leading-relaxed">
            {description}
          </p>
        )}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
