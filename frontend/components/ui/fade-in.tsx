"use client";

import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

type Props = {
  children: ReactNode;
  /** Index in a stagger sequence — multiplied by `step` ms. */
  delay?: number;
  /** ms between staggered children (default 40ms). */
  step?: number;
  /** "in" = subtle 4px fade, "rise" = stronger 10px lift. */
  variant?: "in" | "rise";
  className?: string;
};

export function FadeIn({
  children,
  delay = 0,
  step = 40,
  variant = "in",
  className,
}: Props) {
  return (
    <div
      className={cn(variant === "rise" ? "animate-rise" : "animate-in", className)}
      style={delay > 0 ? { animationDelay: `${delay * step}ms` } : undefined}
    >
      {children}
    </div>
  );
}
