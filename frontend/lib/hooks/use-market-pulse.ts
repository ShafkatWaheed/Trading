"use client";

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { marketApi } from "@/lib/api/endpoints";

export function useMarketPulse(period: string = "1M") {
  const q = useQuery({
    queryKey: ["market", "pulse", period],
    queryFn: () => marketApi.pulse(period),
    staleTime: 5 * 60 * 1000,
  });

  // Self-heal a stale-empty cache: if a prior fetch returned no sectors
  // (e.g. the API was down at the time), refetch once when we mount with
  // that empty payload. Backend never legitimately serves zero sectors —
  // empty means upstream was broken. Ref-guarded so we don't loop if it
  // really is broken right now.
  const retriedRef = useRef(false);
  useEffect(() => {
    if (!q.data || q.isFetching) return;
    const empty = !q.data.sectors || q.data.sectors.length === 0;
    if (empty && !retriedRef.current) {
      retriedRef.current = true;
      q.refetch();
    } else if (!empty) {
      retriedRef.current = false;
    }
  }, [q.data, q.isFetching, q.refetch]);

  return q;
}
