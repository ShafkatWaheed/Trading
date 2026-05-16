import { useQuery } from "@tanstack/react-query";
import { stocksApi } from "@/lib/api/endpoints";

export function useEntityMatches(ticker: string) {
  return useQuery({
    queryKey: ["entity-matches", ticker],
    queryFn: () => stocksApi.entityMatches(ticker),
    staleTime: 15 * 60 * 1000, // 15min — debug data, refresh often
    enabled: Boolean(ticker),
  });
}
