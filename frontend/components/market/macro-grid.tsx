"use client";

import type { MacroMetric } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";

export function MacroGrid({ metrics, loading }: { metrics?: MacroMetric[]; loading?: boolean }) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
    );
  }

  if (!metrics || metrics.length === 0) {
    return <div className="text-text-muted text-sm">No macro data available.</div>;
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      {metrics.map((m) => (
        <div key={m.name} className="card p-4">
          <div className="text-xs uppercase tracking-wider text-text-muted">{m.name}</div>
          <div className="text-xl font-semibold mt-1.5 tabular-nums">{m.value}</div>
        </div>
      ))}
    </div>
  );
}
