"use client";

import { useQuery } from "@tanstack/react-query";
import { stocksApi } from "@/lib/api/endpoints";
import type { StockInformation } from "@/lib/api/types";

export function useExecChanges(ticker: string) {
  return useQuery<StockInformation>({
    queryKey: ["exec-changes", ticker],
    queryFn: () => stocksApi.execChanges(ticker),
    staleTime: 24 * 60 * 60 * 1000, // 24h
    enabled: Boolean(ticker),
  });
}
