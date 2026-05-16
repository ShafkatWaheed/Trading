"use client";

import { useQuery } from "@tanstack/react-query";
import { stocksApi } from "@/lib/api/endpoints";
import type { StockInformation } from "@/lib/api/types";

export function useBacklog(ticker: string) {
  return useQuery<StockInformation>({
    queryKey: ["backlog", ticker],
    queryFn: () => stocksApi.backlog(ticker),
    staleTime: 24 * 60 * 60 * 1000, // 24h
    enabled: Boolean(ticker),
  });
}
