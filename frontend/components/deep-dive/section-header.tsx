"use client";

import { cn } from "@/lib/utils";

type Props = {
  index: number;
  label: string;
  subtitle?: string;
  id?: string;
};

export function SectionHeader({ index, label, subtitle, id }: Props) {
  return (
    <div id={id} className="flex items-center gap-3 pt-3 scroll-mt-28">
      <span
        className={cn(
          "font-mono text-[11px] tabular-nums text-text-muted shrink-0",
          "px-2 py-0.5 rounded border border-bg-borderHi bg-bg-base"
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
      <div className="flex-1 h-px bg-bg-border" />
    </div>
  );
}
