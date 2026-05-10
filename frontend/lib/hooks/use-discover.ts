"use client";

import { useQuery } from "@tanstack/react-query";
import { discoverApi } from "@/lib/api/endpoints";

export function useDiscover(opts?: { min_score?: number; limit?: number; sector?: string }) {
  return useQuery({
    queryKey: ["discover", opts ?? {}],
    queryFn: () => discoverApi.list(opts),
    staleTime: 5 * 60 * 1000,
  });
}
