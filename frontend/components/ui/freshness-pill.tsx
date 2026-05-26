"use client";

import { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";

/** Tiny "Updated 12s ago" pill. Auto-refreshes every 30s. Tints amber when
 *  data is older than `staleAfterMin` minutes, red beyond `veryStaleAfterMin`. */
export function FreshnessPill({
  iso,
  staleAfterMin = 10,
  veryStaleAfterMin = 60,
  className,
}: {
  iso?: string | null;
  staleAfterMin?: number;
  veryStaleAfterMin?: number;
  className?: string;
}) {
  const [, force] = useState(0);

  useEffect(() => {
    if (!iso) return;
    const id = setInterval(() => force((n) => n + 1), 30_000);
    return () => clearInterval(id);
  }, [iso]);

  if (!iso) return null;

  const date = new Date(iso);
  const ageMin = (Date.now() - date.getTime()) / 60_000;
  const tone =
    ageMin >= veryStaleAfterMin
      ? "text-accent-redSoft border-accent-red/30 bg-accent-red/5"
      : ageMin >= staleAfterMin
      ? "text-accent-amber border-accent-amber/30 bg-accent-amber/5"
      : "text-text-muted border-bg-border bg-bg-card/50";

  return (
    <span
      title={date.toLocaleString()}
      className={cn(
        "inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-md border tabular-nums",
        tone,
        className,
      )}
    >
      <Clock size={9} className="opacity-70" />
      {formatRelativeTime(iso)}
    </span>
  );
}
