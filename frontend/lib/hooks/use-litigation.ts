"use client";

import { useQuery } from "@tanstack/react-query";
import { stocksApi } from "@/lib/api/endpoints";
import type { StockInformation } from "@/lib/api/types";

export function useLitigation(ticker: string) {
  return useQuery<StockInformation>({
    queryKey: ["litigation", ticker],
    queryFn: () => stocksApi.litigation(ticker),
    staleTime: 24 * 60 * 60 * 1000, // 24h
    enabled: Boolean(ticker),
  });
}
