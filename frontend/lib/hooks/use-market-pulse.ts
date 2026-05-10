"use client";

import { useQuery } from "@tanstack/react-query";
import { marketApi } from "@/lib/api/endpoints";

export function useMarketPulse(period: string = "1M") {
  return useQuery({
    queryKey: ["market", "pulse", period],
    queryFn: () => marketApi.pulse(period),
    staleTime: 5 * 60 * 1000,
  });
}
