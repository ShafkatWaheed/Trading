import { type HTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

export const Card = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("card p-6", className)} {...props} />
  )
);
Card.displayName = "Card";

export function CardHeader({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("flex items-center justify-between gap-3 mb-4 pb-4 border-b border-bg-divider", className)}>
      {children}
    </div>
  );
}

export function CardTitle({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <h3 className={cn("text-sm font-semibold tracking-tight text-text-primary", className)}>
      {children}
    </h3>
  );
}

export function CardDescription({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("text-text-secondary text-xs mt-1", className)}>{children}</p>;
}

/** Visual section header inside a page (not a card). */
export function SectionHeading({
  title,
  hint,
  trailing,
  className,
}: {
  title: string;
  hint?: string;
  trailing?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-end justify-between gap-3 mb-3 flex-wrap", className)}>
      <div>
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-secondary">
          {title}
        </h2>
        {hint && <p className="text-[11px] text-text-muted mt-0.5">{hint}</p>}
      </div>
      {trailing}
    </div>
  );
}
