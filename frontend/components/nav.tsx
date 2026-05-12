"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  Activity, Compass, Search, BarChart3, Bot, Bell, Network, Newspaper,
  Radio, Eye, ChevronDown,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { alertsApi } from "@/lib/api/endpoints";
import { TickerSearchInput } from "@/components/ui/ticker-search-input";

const PRIMARY = [
  { href: "/",          label: "Market",    icon: Activity },
  { href: "/discover",  label: "Discover",  icon: Compass },
  { href: "/deep-dive", label: "Deep Dive", icon: Search },
  { href: "/prove-it",  label: "Prove It",  icon: BarChart3 },
  { href: "/agent",     label: "AI Agent",  icon: Bot },
];

const SECONDARY = [
  { href: "/universe",        label: "Universe",       icon: Network,   blurb: "Tracked stock universe" },
  { href: "/news-impact",     label: "News Impact",    icon: Newspaper, blurb: "Cross-stock news propagation" },
  { href: "/edge-freshness",  label: "Edge Freshness", icon: Eye,       blurb: "Data freshness queue" },
  { href: "/data-sources",    label: "Data Sources",   icon: Radio,     blurb: "Connected feeds + rate limits" },
];

function useMarketStatus(): { open: boolean; label: string } {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(t);
  }, []);
  // NYSE: Mon-Fri, 09:30–16:00 ET
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(now);
  const map: Record<string, string> = {};
  for (const p of fmt) map[p.type] = p.value;
  const weekday = map.weekday;
  const h = parseInt(map.hour ?? "0", 10);
  const m = parseInt(map.minute ?? "0", 10);
  const minutes = h * 60 + m;
  const isWeekday = !["Sat", "Sun"].includes(weekday);
  const open = isWeekday && minutes >= 9 * 60 + 30 && minutes < 16 * 60;
  return { open, label: open ? "MARKET OPEN" : "MARKET CLOSED" };
}

function MarketStatusPill() {
  const { open, label } = useMarketStatus();
  return (
    <div
      className={cn(
        "hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-[10px] font-semibold uppercase tracking-wider",
        open
          ? "border-accent-green/30 bg-accent-green/5 text-accent-greenSoft"
          : "border-bg-borderHi bg-bg-card text-text-muted"
      )}
      title="NYSE regular hours · 9:30–16:00 ET"
    >
      <span className={cn("w-1.5 h-1.5 rounded-full", open ? "bg-accent-green animate-pulse" : "bg-text-dim")} />
      {label}
    </div>
  );
}

function BrandMark() {
  return (
    <Link href="/" className="flex items-center gap-2.5 group shrink-0" aria-label="Trading — home">
      <svg
        width="26" height="26" viewBox="0 0 26 26"
        className="text-accent-blue group-hover:text-accent-violet transition-colors"
        aria-hidden
      >
        <defs>
          <linearGradient id="brandGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%"   stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>
        <rect x="1" y="1" width="24" height="24" rx="6" fill="url(#brandGrad)" opacity="0.18" />
        <rect x="1" y="1" width="24" height="24" rx="6" stroke="url(#brandGrad)" strokeWidth="1.5" fill="none" />
        {/* Candle chart glyph */}
        <rect x="6"  y="14" width="2.5" height="6"  rx="0.5" fill="currentColor" />
        <line x1="7.25" y1="11" x2="7.25" y2="22"  stroke="currentColor" strokeWidth="0.6" />
        <rect x="11" y="8"  width="2.5" height="10" rx="0.5" fill="currentColor" />
        <line x1="12.25" y1="6" x2="12.25" y2="20" stroke="currentColor" strokeWidth="0.6" />
        <rect x="16" y="11" width="2.5" height="7"  rx="0.5" fill="currentColor" />
        <line x1="17.25" y1="9" x2="17.25" y2="21"  stroke="currentColor" strokeWidth="0.6" />
      </svg>
      <span className="hidden sm:inline text-text-primary font-semibold tracking-tight">
        Trading<span className="text-accent-blue">.</span>
      </span>
    </Link>
  );
}

function NavLink({ href, label, icon: Icon, active }: {
  href: string; label: string; icon: typeof Activity; active: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "relative px-3 py-1.5 rounded-md flex items-center gap-2 transition-colors text-[13px] font-medium whitespace-nowrap",
        active
          ? "text-text-primary bg-bg-card2"
          : "text-text-secondary hover:text-text-primary hover:bg-bg-card/60"
      )}
    >
      <Icon size={14} strokeWidth={active ? 2.4 : 1.8} className={active ? "text-accent-blue" : ""} />
      <span>{label}</span>
      {active && (
        <span className="absolute inset-x-2 -bottom-px h-px bg-accent-blue" />
      )}
    </Link>
  );
}

function MorePopover({ pathname }: { pathname: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const anyActive = SECONDARY.some(
    (s) => pathname === s.href || pathname.startsWith(s.href + "/")
  );

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className={cn(
          "px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-colors text-[13px] font-medium whitespace-nowrap",
          anyActive
            ? "text-text-primary bg-bg-card2"
            : "text-text-secondary hover:text-text-primary hover:bg-bg-card/60"
        )}
      >
        More
        <ChevronDown size={12} className={cn("transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 top-[calc(100%+6px)] w-72 bg-bg-card border border-bg-borderHi rounded-lg shadow-2xl shadow-black/60 backdrop-blur-xl p-1.5 z-50"
        >
          {SECONDARY.map((s) => {
            const Icon = s.icon;
            const active = pathname === s.href || pathname.startsWith(s.href + "/");
            return (
              <Link
                key={s.href}
                href={s.href}
                onClick={() => setOpen(false)}
                role="menuitem"
                className={cn(
                  "flex items-start gap-3 px-3 py-2.5 rounded-md transition-colors",
                  active ? "bg-bg-card2" : "hover:bg-bg-card2/70"
                )}
              >
                <Icon size={16} className={cn("mt-0.5 shrink-0", active ? "text-accent-blue" : "text-text-muted")} strokeWidth={1.8} />
                <div className="min-w-0">
                  <div className={cn("text-[13px] font-medium", active ? "text-text-primary" : "text-text-secondary")}>{s.label}</div>
                  <div className="text-[11px] text-text-muted leading-snug mt-0.5">{s.blurb}</div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function Nav() {
  const pathname = usePathname();
  const router = useRouter();
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
    <header className="sticky top-0 z-40 backdrop-blur-xl bg-bg-base/80 border-b border-bg-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center gap-3 md:gap-5">
        <BrandMark />

        <div className="hidden md:block h-5 w-px bg-bg-borderHi" />

        <div className="flex items-center gap-0.5 flex-1 min-w-0">
          <nav className="flex items-center gap-0.5 overflow-x-auto scrollbar-none min-w-0">
            {PRIMARY.map((item) => {
              const active =
                pathname === item.href ||
                (item.href !== "/" && pathname.startsWith(item.href));
              return (
                <NavLink key={item.href} {...item} active={active} />
              );
            })}
          </nav>
          <MorePopover pathname={pathname} />
        </div>

        <div className="hidden md:block w-48 lg:w-64 shrink-0">
          <TickerSearchInput
            onPick={(sym) => router.push(`/deep-dive/${sym}`)}
            placeholder="Search ticker…"
            compact
            clearOnPick
          />
        </div>

        <MarketStatusPill />

        <Link
          href="/alerts"
          aria-label={`Alerts${alertCount ? ` (${alertCount})` : ""}`}
          className={cn(
            "relative shrink-0 w-9 h-9 rounded-md grid place-items-center transition-colors",
            alertActive
              ? "bg-bg-card2 text-text-primary"
              : "text-text-secondary hover:text-text-primary hover:bg-bg-card/60"
          )}
        >
          <Bell size={16} strokeWidth={alertActive ? 2.4 : 1.8} className={alertActive ? "text-accent-amber" : ""} />
          {alertCount > 0 && (
            <span
              className={cn(
                "absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-bold tabular-nums grid place-items-center ring-2 ring-bg-base",
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
