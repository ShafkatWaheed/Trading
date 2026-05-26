import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} />;
}

/** Mirrors the shape of MetricCard so loading state has the same footprint
 * as the real thing — no layout shift when data arrives. */
export function MetricCardSkeleton({
  align = "left",
  className,
}: {
  align?: "left" | "center";
  className?: string;
}) {
  return (
    <div className={cn("card p-4", align === "center" && "text-center", className)}>
      <div className={cn("flex items-center gap-1.5", align === "center" && "justify-center")}>
        <Skeleton className="h-3 w-20" />
      </div>
      <Skeleton className="h-7 w-24 mt-2 mx-auto" />
      <Skeleton className="h-3 w-32 mt-2 mx-auto" />
    </div>
  );
}

/** N MetricCardSkeletons in a responsive grid — matches KpiGrid layout. */
export function KpiGridSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {Array.from({ length: count }).map((_, i) => (
        <MetricCardSkeleton key={i} align="center" />
      ))}
    </div>
  );
}

/** Skeleton row that mimics a list item — small avatar/icon + title + meta line. */
export function ListItemSkeleton() {
  return (
    <div className="card p-3 flex items-start gap-3">
      <Skeleton className="h-8 w-8 rounded-md shrink-0" />
      <div className="flex-1 min-w-0 space-y-2">
        <Skeleton className="h-3.5 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </div>
  );
}

/** N ListItemSkeletons stacked — useful for news feeds, alert lists, etc. */
export function ListSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <ListItemSkeleton key={i} />
      ))}
    </div>
  );
}
