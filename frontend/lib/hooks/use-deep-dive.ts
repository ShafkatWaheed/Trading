"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { stocksApi } from "@/lib/api/endpoints";
import type { DeepDive } from "@/lib/api/types";

/**
 * Fetches the deep-dive bundle (one network call) and primes the React Query
 * cache for each child query (bubble-score, peer-valuation, analyst-consensus,
 * benchmarks) so child components see hits immediately on first render.
 *
 * Returns the deep_dive payload directly so existing callers don't change.
 */
export function useDeepDive(
  ticker: string,
  opts?: { period?: string; signal_filter?: string; account_size?: number; risk_pct?: number }
) {
  const qc = useQueryClient();
  const symbol = ticker.toUpperCase();
  const period = opts?.period ?? "3M";

  return useQuery<DeepDive>({
    queryKey: ["deepDive", symbol, opts ?? {}],
    queryFn: async () => {
      const bundle = await stocksApi.deepDiveBundle(ticker, opts);

      // Prime child caches with exact keys/staleTimes the components use.
      if (bundle.bubble_score) {
        qc.setQueryData(["bubble-score", symbol], bundle.bubble_score);
      }
      if (bundle.peer_valuation) {
        qc.setQueryData(["peer-valuation", symbol], bundle.peer_valuation);
      }
      if (bundle.analyst_consensus) {
        qc.setQueryData(["analyst-consensus", symbol], bundle.analyst_consensus);
      }
      if (bundle.benchmarks) {
        qc.setQueryData(["benchmarks", symbol, period], bundle.benchmarks);
      }

      return bundle.deep_dive;
    },
    enabled: !!ticker,
    staleTime: 15 * 60 * 1000,
    // yfinance hits transient "Invalid Crumb" 401s a few times per session
    // when Yahoo rotates its anti-bot crumb cache. One retry with a short
    // backoff is usually enough to ride through.
    retry: 1,
    retryDelay: (attempt) => Math.min(2000 * 2 ** attempt, 8000),
  });
}
