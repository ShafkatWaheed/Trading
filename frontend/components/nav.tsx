"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Activity, Compass, Search, BarChart3, Bot, Bell, Radio, Network, Newspaper, Eye } from "lucide-react";
import { cn } from "@/lib/utils";
import { alertsApi } from "@/lib/api/endpoints";

const ITEMS = [
  { href: "/",                label: "Market Pulse",   icon: Activity,  accent: "text-accent-blue" },
  { href: "/discover",        label: "Discover",       icon: Compass,   accent: "text-accent-amber" },
  { href: "/deep-dive",       label: "Deep Dive",      icon: Search,    accent: "text-accent-violet" },
  { href: "/prove-it",        label: "Prove It",       icon: BarChart3, accent: "text-accent-cyan" },
  { href: "/agent",           label: "AI Agent",       icon: Bot,       accent: "text-accent-pink" },
  { href: "/universe",        label: "Universe",       icon: Network,   accent: "text-accent-violet" },
  { href: "/news-impact",     label: "News Impact",    icon: Newspaper, accent: "text-accent-cyan" },
  { href: "/edge-freshness",  label: "Edge Freshness", icon: Eye,       accent: "text-accent-cyan" },
  { href: "/data-sources",    label: "Data Sources",   icon: Radio,     accent: "text-accent-violet" },
];

export function Nav() {
  const pathname = usePathname();
  const { data: alerts } = useQuery({
    queryKey: ["alerts", "summary"],
    queryFn: () => alertsApi.summary(),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });
  const alertActive = pathname.startsWith("/alerts");
  const alertCount = alerts?.last_24h ?? 0;
  const alertCritical = (alerts?.critical ?? 0) > 0;

  return (
    <header className="sticky top-0 z-50 backdrop-blur-xl bg-bg-base/70 border-b border-bg-border">
      <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-6">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2.5 group shrink-0">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-accent-blue via-accent-violet to-accent-pink grid place-items-center text-white text-[11px] font-bold tracking-tight shadow-lg shadow-accent-blue/20 group-hover:shadow-accent-violet/30 transition-shadow">
            T
          </div>
          <span className="hidden sm:flex items-baseline gap-1">
            <span className="text-text-primary font-semibold tracking-tight text-sm">Trading</span>
            <span className="text-text-dim text-[10px] font-medium uppercase tracking-wider">Beta</span>
          </span>
        </Link>

        {/* Nav items */}
        <nav className="flex items-center gap-0.5 text-sm overflow-x-auto flex-1">
          {ITEMS.map((item) => {
            const Icon = item.icon;
            const active =
              pathname === item.href ||
              (item.href !== "/" && pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "relative px-3 py-1.5 rounded-md flex items-center gap-2 transition-all duration-150 whitespace-nowrap text-[13px]",
                  active
                    ? "text-text-primary"
                    : "text-text-secondary hover:text-text-primary"
                )}
              >
                <Icon size={14} className={cn("transition-colors", active ? item.accent : "")} strokeWidth={active ? 2.4 : 2} />
                <span className="hidden md:inline font-medium">{item.label}</span>
                {active && (
                  <span className="absolute inset-x-2 -bottom-px h-px bg-gradient-to-r from-transparent via-current to-transparent opacity-60" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Alerts bell */}
        <Link
          href="/alerts"
          className={cn(
            "relative px-2.5 py-1.5 rounded-md flex items-center gap-2 transition-all whitespace-nowrap",
            alertActive
              ? "bg-bg-card2 text-text-primary border border-bg-borderHi"
              : "text-text-secondary hover:text-text-primary hover:bg-bg-card/60"
          )}
        >
          <Bell size={14} className={cn(alertActive ? "text-accent-amber" : "")} strokeWidth={alertActive ? 2.4 : 2} />
          <span className="hidden md:inline text-[13px] font-medium">Alerts</span>
          {alertCount > 0 && (
            <span
              className={cn(
                "absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-bold tabular-nums grid place-items-center ring-2 ring-bg-base",
                alertCritical
                  ? "bg-accent-red text-white animate-pulse"
                  : "bg-accent-amber text-black"
              )}
            >
              {alertCount > 99 ? "99+" : alertCount}
            </span>
          )}
        </Link>
      </div>
    </header>
  );
}
