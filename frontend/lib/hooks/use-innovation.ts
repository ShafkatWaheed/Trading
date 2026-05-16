"use client";

import { useQuery } from "@tanstack/react-query";
import { stocksApi } from "@/lib/api/endpoints";
import type { StockInformation } from "@/lib/api/types";

export function useInnovation(ticker: string) {
  return useQuery<StockInformation>({
    queryKey: ["innovation", ticker],
    queryFn: () => stocksApi.innovation(ticker),
    staleTime: 24 * 60 * 60 * 1000, // 24h
    enabled: Boolean(ticker),
  });
}
