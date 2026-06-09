"use client";

/**
 * Per-feature staleness banner.
 *
 * Drop into the top of any page:
 *   <FreshnessBanner feature="predictions" />
 *
 * Shows nothing when data is fresh. Renders an amber warning card with
 * the reason ("scores last computed 53h ago") when stale. Auto-refetches
 * every 5 min so banners update without a page reload.
 *
 * Backed by GET /freshness/feature/{name}.
 */

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { api } from "@/lib/api/endpoints";


type FeatureFreshness = {
  stale: boolean;
  last_updated: string | null;
  age_minutes: number | null;
  reason: string | null;
};


export function FreshnessBanner({ feature }: { feature: string }) {
  const q = useQuery<FeatureFreshness>({
    queryKey: ["feature-freshness", feature],
    queryFn: () => api.get<FeatureFreshness>(`/freshness/feature/${feature}`),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });

  if (!q.data || !q.data.stale) return null;

  const ageHrs = q.data.age_minutes != null ? Math.floor(q.data.age_minutes / 60) : null;

  return (
    <div className="card p-3 mb-4 border-l-4 border-accent-amber/60 bg-accent-amber/5 flex items-start gap-3">
      <AlertTriangle size={14} className="text-accent-amber mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-[12px] font-semibold text-accent-amber">
          Stale data warning
        </div>
        <div className="text-[11px] text-text-secondary mt-0.5">
          {q.data.reason ?? "Underlying data is older than expected."}
          {ageHrs != null && ` (${ageHrs}h since last update)`}
        </div>
      </div>
    </div>
  );
}
