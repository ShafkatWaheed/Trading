"use client";

import { useQuery } from "@tanstack/react-query";
import { marketApi } from "@/lib/api/endpoints";

export function useEconomicCalendar() {
  return useQuery({
    queryKey: ["market", "calendar"],
    queryFn: () => marketApi.calendar(60, 12),
    staleTime: 30 * 60 * 1000,    // 30 min
  });
}

export function useGeopoliticalEvents() {
  return useQuery({
    queryKey: ["market", "geopolitical"],
    queryFn: () => marketApi.geopolitical(),
    staleTime: 60 * 60 * 1000,    // 1 hour (cached server-side too)
    retry: 0,
  });
}

export function useDisruptionThemes() {
  return useQuery({
    queryKey: ["market", "disruption"],
    queryFn: () => marketApi.disruption(),
    staleTime: 60 * 60 * 1000,
    retry: 0,
  });
}
