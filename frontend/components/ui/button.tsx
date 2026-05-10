"use client";

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Tone = "blue" | "amber" | "violet" | "cyan" | "green" | "red" | "pink" | "neutral";
type Variant = "solid" | "outline" | "ghost";
type Size = "xs" | "sm" | "md" | "lg";

const TONE: Record<Tone, { solid: string; outline: string; ghost: string }> = {
  blue: {
    solid:   "bg-accent-blue/15 text-accent-blue border-accent-blue/40 hover:bg-accent-blue/25 hover:border-accent-blue/60",
    outline: "bg-bg-surface text-accent-blue border-accent-blue/30 hover:border-accent-blue/60 hover:bg-accent-blue/10",
    ghost:   "text-accent-blue hover:bg-accent-blue/10 border-transparent",
  },
  amber: {
    solid:   "bg-accent-amber/15 text-accent-amber border-accent-amber/40 hover:bg-accent-amber/25 hover:border-accent-amber/60",
    outline: "bg-bg-surface text-accent-amber border-accent-amber/30 hover:border-accent-amber/60 hover:bg-accent-amber/10",
    ghost:   "text-accent-amber hover:bg-accent-amber/10 border-transparent",
  },
  violet: {
    solid:   "bg-accent-violet/15 text-accent-violet border-accent-violet/40 hover:bg-accent-violet/25 hover:border-accent-violet/60",
    outline: "bg-bg-surface text-accent-violet border-accent-violet/30 hover:border-accent-violet/60 hover:bg-accent-violet/10",
    ghost:   "text-accent-violet hover:bg-accent-violet/10 border-transparent",
  },
  cyan: {
    solid:   "bg-accent-cyan/15 text-accent-cyan border-accent-cyan/40 hover:bg-accent-cyan/25 hover:border-accent-cyan/60",
    outline: "bg-bg-surface text-accent-cyan border-accent-cyan/30 hover:border-accent-cyan/60 hover:bg-accent-cyan/10",
    ghost:   "text-accent-cyan hover:bg-accent-cyan/10 border-transparent",
  },
  green: {
    solid:   "bg-accent-green/15 text-accent-greenSoft border-accent-green/40 hover:bg-accent-green/25 hover:border-accent-green/60",
    outline: "bg-bg-surface text-accent-greenSoft border-accent-green/30 hover:border-accent-green/60 hover:bg-accent-green/10",
    ghost:   "text-accent-greenSoft hover:bg-accent-green/10 border-transparent",
  },
  red: {
    solid:   "bg-accent-red/15 text-accent-redSoft border-accent-red/40 hover:bg-accent-red/25 hover:border-accent-red/60",
    outline: "bg-bg-surface text-accent-redSoft border-accent-red/30 hover:border-accent-red/60 hover:bg-accent-red/10",
    ghost:   "text-accent-redSoft hover:bg-accent-red/10 border-transparent",
  },
  pink: {
    solid:   "bg-accent-pink/15 text-accent-pink border-accent-pink/40 hover:bg-accent-pink/25 hover:border-accent-pink/60",
    outline: "bg-bg-surface text-accent-pink border-accent-pink/30 hover:border-accent-pink/60 hover:bg-accent-pink/10",
    ghost:   "text-accent-pink hover:bg-accent-pink/10 border-transparent",
  },
  neutral: {
    solid:   "bg-bg-card2 text-text-primary border-bg-borderHi hover:bg-bg-card3",
    outline: "bg-bg-surface text-text-secondary border-bg-border hover:border-bg-borderHi hover:text-text-primary",
    ghost:   "text-text-secondary hover:bg-bg-card hover:text-text-primary border-transparent",
  },
};

const SIZE: Record<Size, string> = {
  xs: "h-7 px-2.5 text-[11px] gap-1",
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-9 px-3.5 text-[13px] gap-2",
  lg: "h-11 px-5 text-sm gap-2",
};

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: Tone;
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ tone = "neutral", variant = "outline", size = "md", loading, leftIcon, rightIcon, className, children, disabled, ...rest }, ref) => {
    const toneStyles = TONE[tone][variant];
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          "inline-flex items-center justify-center font-medium rounded-md border transition-all duration-150 ease-out-expo whitespace-nowrap select-none",
          "active:scale-[0.98]",
          "disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100",
          SIZE[size],
          toneStyles,
          className,
        )}
        {...rest}
      >
        {loading ? <Loader2 size={14} className="animate-spin" /> : leftIcon}
        {children}
        {!loading && rightIcon}
      </button>
    );
  },
);
Button.displayName = "Button";
