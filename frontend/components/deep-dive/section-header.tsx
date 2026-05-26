"use client";

import { cn } from "@/lib/utils";

type Accent = "blue" | "green" | "red" | "amber";

type Props = {
  index: number;
  label: string;
  subtitle?: string;
  id?: string;
  /** Color owned by this section — paints the number chip + divider tint. */
  accent?: Accent;
};

const ACCENT_TOKEN: Record<Accent, { chip: string; line: string; text: string }> = {
  blue: {
    chip: "border-accent-blue/40 bg-accent-blue/10",
    line: "bg-gradient-to-r from-accent-blue/40 via-bg-border to-transparent",
    text: "text-accent-blueSoft",
  },
  green: {
    chip: "border-accent-green/40 bg-accent-green/10",
    line: "bg-gradient-to-r from-accent-green/40 via-bg-border to-transparent",
    text: "text-accent-greenSoft",
  },
  red: {
    chip: "border-accent-red/40 bg-accent-red/10",
    line: "bg-gradient-to-r from-accent-red/40 via-bg-border to-transparent",
    text: "text-accent-redSoft",
  },
  amber: {
    chip: "border-accent-amber/40 bg-accent-amber/10",
    line: "bg-gradient-to-r from-accent-amber/40 via-bg-border to-transparent",
    text: "text-accent-amber",
  },
};

export function SectionHeader({ index, label, subtitle, id, accent }: Props) {
  const tone = accent ? ACCENT_TOKEN[accent] : null;

  return (
    <div id={id} className="flex items-center gap-3 pt-3 scroll-mt-28">
      <span
        className={cn(
          "font-mono text-[11px] tabular-nums shrink-0 px-2 py-0.5 rounded border",
          tone ? cn(tone.chip, tone.text) : "border-bg-borderHi bg-bg-base text-text-muted",
        )}
      >
        {String(index).padStart(2, "0")}
      </span>
      <div className="flex items-baseline gap-3 flex-wrap min-w-0">
        <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-text-primary">
          {label}
        </h2>
        {subtitle && (
          <span className="text-[11px] text-text-muted normal-case tracking-normal">
            {subtitle}
          </span>
        )}
      </div>
      <div className={cn("flex-1 h-px", tone ? tone.line : "bg-bg-border")} />
    </div>
  );
}
