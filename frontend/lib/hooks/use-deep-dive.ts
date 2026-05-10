"use client";

import { useQuery } from "@tanstack/react-query";
import { stocksApi } from "@/lib/api/endpoints";

export function useDeepDive(
  ticker: string,
  opts?: { period?: string; signal_filter?: string; account_size?: number; risk_pct?: number }
) {
  return useQuery({
    queryKey: ["deepDive", ticker.toUpperCase(), opts ?? {}],
    queryFn: () => stocksApi.deepDive(ticker, opts),
    enabled: !!ticker,
    staleTime: 15 * 60 * 1000,
    retry: 0,
  });
}
