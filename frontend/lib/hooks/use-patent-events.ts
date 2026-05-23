import { useQuery } from "@tanstack/react-query";
import { stocksApi } from "@/lib/api/endpoints";

export function usePatentEvents(ticker: string) {
  return useQuery({
    queryKey: ["patent-events", ticker],
    queryFn: () => stocksApi.patentEvents(ticker),
    staleTime: 24 * 60 * 60 * 1000, // 24h — Orange Book cache is weekly anyway
    enabled: Boolean(ticker),
  });
}
