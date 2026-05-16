"use client";

import { Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  onClick: () => void;
  isFetching?: boolean;
  size?: "sm" | "md";
  className?: string;
  title?: string;
};

/**
 * Tiny shared refresh icon button. Reused across cards so the affordance
 * looks identical wherever it appears.
 */
export function RefreshButton({ onClick, isFetching, size = "sm", className, title = "Refresh" }: Props) {
  const px = size === "md" ? 13 : 11;
  return (
    <button
      onClick={onClick}
      disabled={isFetching}
      title={title}
      aria-label={title}
      className={cn(
        "text-text-muted hover:text-text-primary flex items-center disabled:opacity-40 transition-colors",
        className,
      )}
    >
      {isFetching
        ? <Loader2 size={px} className="animate-spin" />
        : <RefreshCw size={px} />}
    </button>
  );
}
