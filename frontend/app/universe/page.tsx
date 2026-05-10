"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Network,
  ChevronRight,
  ChevronDown,
  Search,
  Globe,
  Building2,
  Layers,
  Database,
  Info,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { universeApi } from "@/lib/api/endpoints";
import type { Tier, UniverseStock } from "@/lib/api/types";
import { cn } from "@/lib/utils";

// ── styling helpers ───────────────────────────────────────────────

const TIER_TONE: Record<
  Tier,
  { badge: string; text: string; label: string; ring: string }
> = {
  A: {
    badge: "badge-amber",
    text: "text-accent-amber",
    label: "Tier A — Spine",
    ring: "ring-accent-amber/40",
  },
  B: {
    badge: "badge-blue",
    text: "text-accent-blue",
    label: "Tier B — Liquid",
    ring: "ring-accent-blue/40",
  },
  C: {
    badge: "badge-zinc",
    text: "text-text-secondary",
    label: "Tier C — Mid",
    ring: "ring-bg-borderHi/40",
  },
  D: {
    badge: "badge-zinc",
    text: "text-text-muted",
    label: "Tier D — Long-tail",
    ring: "ring-bg-border/40",
  },
};

const SECTOR_ACCENT: Record<string, string> = {
  Technology: "text-accent-violet",
  "Communication Services": "text-accent-pink",
  "Consumer Cyclical": "text-accent-amber",
  "Consumer Defensive": "text-accent-green",
  Healthcare: "text-accent-cyan",
  "Financial Services": "text-accent-blue",
  Energy: "text-accent-amber",
  Industrials: "text-accent-violet",
  "Basic Materials": "text-text-secondary",
  "Real Estate": "text-accent-cyan",
  Utilities: "text-accent-green",
};

function fmtCap(n: number | null): string {
  if (n == null) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toFixed(0)}`;
}

function tierBadge(t: Tier) {
  const tone = TIER_TONE[t];
  return (
    <span className={cn("badge text-[10px] tabular-nums px-1.5 py-0.5", tone.badge)}>
      {t}
    </span>
  );
}

// ── grouping logic ────────────────────────────────────────────────

type IndustryGroup = {
  industry: string;
  sector: string;
  stocks: UniverseStock[];
};

type SectorGroup = {
  sector: string;
  industries: IndustryGroup[];
  stockCount: number;
  tierCounts: Record<Tier, number>;
};

function groupBySector(stocks: UniverseStock[]): SectorGroup[] {
  // For multi-tag stocks (conglomerates), use only the primary industry to
  // avoid double-counting. Fallback: first industry in the list.
  const byKey = new Map<string, IndustryGroup>();

  for (const s of stocks) {
    const primary = s.industries.find((i) => i.is_primary) || s.industries[0];
    const industry = primary?.code || "Unclassified";
    const sector = primary?.sector || "Unclassified";
    const key = `${sector}::${industry}`;
    if (!byKey.has(key)) {
      byKey.set(key, { industry, sector, stocks: [] });
    }
    byKey.get(key)!.stocks.push(s);
  }

  // Aggregate to sector level.
  const sectorMap = new Map<string, SectorGroup>();
  for (const ig of byKey.values()) {
    if (!sectorMap.has(ig.sector)) {
      sectorMap.set(ig.sector, {
        sector: ig.sector,
        industries: [],
        stockCount: 0,
        tierCounts: { A: 0, B: 0, C: 0, D: 0 },
      });
    }
    const sg = sectorMap.get(ig.sector)!;
    sg.industries.push(ig);
    sg.stockCount += ig.stocks.length;
    for (const s of ig.stocks) {
      sg.tierCounts[s.tier] += 1;
    }
  }

  // Sort industries within sectors by member count desc, sectors by total desc.
  const sectors = Array.from(sectorMap.values());
  for (const s of sectors) {
    s.industries.sort((a, b) => b.stocks.length - a.stocks.length);
    for (const ig of s.industries) {
      ig.stocks.sort((a, b) => {
        const tierOrder = { A: 0, B: 1, C: 2, D: 3 };
        if (tierOrder[a.tier] !== tierOrder[b.tier]) return tierOrder[a.tier] - tierOrder[b.tier];
        return (b.market_cap ?? 0) - (a.market_cap ?? 0);
      });
    }
  }
  sectors.sort((a, b) => b.stockCount - a.stockCount);
  return sectors;
}

// ── components ────────────────────────────────────────────────────

function StockChip({ s }: { s: UniverseStock }) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-1 bg-bg-card2",
        "ring-1 ring-inset",
        TIER_TONE[s.tier].ring,
        "hover:bg-bg-card transition-colors cursor-default"
      )}
      title={`${s.name ?? s.symbol} • ${s.exchange ?? ""}${s.country ? " · " + s.country : ""} • mcap ${fmtCap(s.market_cap)}`}
    >
      {tierBadge(s.tier)}
      <span className="font-mono text-[12px] font-semibold tabular-nums">
        {s.symbol}
      </span>
      <span className="text-[10px] text-text-muted hidden md:inline">
        {fmtCap(s.market_cap)}
      </span>
    </div>
  );
}

function IndustryRow({ ig }: { ig: IndustryGroup }) {
  const [open, setOpen] = useState(false);
  const tierCounts = useMemo(() => {
    const c = { A: 0, B: 0, C: 0, D: 0 };
    for (const s of ig.stocks) c[s.tier] += 1;
    return c;
  }, [ig]);

  return (
    <div className="border-l-2 border-bg-border ml-2 pl-3">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 py-1.5 text-left hover:text-text-primary transition-colors"
      >
        {open ? (
          <ChevronDown size={12} className="text-text-muted shrink-0" />
        ) : (
          <ChevronRight size={12} className="text-text-muted shrink-0" />
        )}
        <Layers size={12} className="text-text-secondary shrink-0" />
        <span className="text-[13px] text-text-secondary">{ig.industry}</span>
        <span className="text-[10px] text-text-muted ml-auto tabular-nums">
          {ig.stocks.length} {ig.stocks.length === 1 ? "stock" : "stocks"}
        </span>
        <div className="flex items-center gap-1">
          {(["A", "B", "C", "D"] as Tier[]).map((t) =>
            tierCounts[t] > 0 ? (
              <span
                key={t}
                className={cn(
                  "text-[9px] tabular-nums px-1 rounded",
                  TIER_TONE[t].badge
                )}
              >
                {t}:{tierCounts[t]}
              </span>
            ) : null
          )}
        </div>
      </button>
      {open && (
        <div className="flex flex-wrap gap-1.5 pb-3 pl-5">
          {ig.stocks.map((s) => (
            <StockChip key={s.symbol} s={s} />
          ))}
        </div>
      )}
    </div>
  );
}

function SectorCard({
  group,
  totalStocks,
}: {
  group: SectorGroup;
  totalStocks: number;
}) {
  const [open, setOpen] = useState(true);
  const accent = SECTOR_ACCENT[group.sector] ?? "text-text-secondary";
  const widthPct = totalStocks > 0 ? (group.stockCount / totalStocks) * 100 : 0;

  return (
    <div className="card p-4">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 text-left"
      >
        {open ? (
          <ChevronDown size={14} className={accent} />
        ) : (
          <ChevronRight size={14} className={accent} />
        )}
        <Building2 size={14} className={accent} strokeWidth={2.4} />
        <h3 className={cn("text-[14px] font-semibold tracking-tight", accent)}>
          {group.sector}
        </h3>
        <div className="ml-auto flex items-center gap-3">
          <div className="text-[11px] text-text-muted tabular-nums">
            {group.stockCount} {group.stockCount === 1 ? "stock" : "stocks"} · {group.industries.length} industries
          </div>
          <div className="flex items-center gap-1">
            {(["A", "B", "C", "D"] as Tier[]).map((t) =>
              group.tierCounts[t] > 0 ? (
                <span
                  key={t}
                  className={cn(
                    "text-[9px] tabular-nums px-1.5 py-0.5 rounded",
                    TIER_TONE[t].badge
                  )}
                >
                  {t}:{group.tierCounts[t]}
                </span>
              ) : null
            )}
          </div>
        </div>
      </button>

      {/* share-of-universe bar */}
      <div className="mt-2 h-[3px] bg-bg-border rounded-full overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            "bg-gradient-to-r from-accent-violet via-accent-blue to-accent-pink",
            "opacity-50"
          )}
          style={{ width: `${widthPct.toFixed(2)}%` }}
        />
      </div>

      {open && (
        <div className="mt-3 space-y-1">
          {group.industries.map((ig) => (
            <IndustryRow key={ig.industry} ig={ig} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── page ──────────────────────────────────────────────────────────

export default function UniversePage() {
  const [activeTiers, setActiveTiers] = useState<Set<Tier>>(
    new Set(["A", "B", "C", "D"])
  );
  const [search, setSearch] = useState("");

  const tierParam = useMemo(() => Array.from(activeTiers).sort().join(","), [activeTiers]);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["universe", tierParam],
    queryFn: () => universeApi.list({ tier: tierParam, limit: 5000 }),
    staleTime: 60_000,
  });

  const filteredStocks = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toUpperCase();
    if (!q) return data.stocks;
    return data.stocks.filter(
      (s) =>
        s.symbol.includes(q) ||
        (s.name ?? "").toUpperCase().includes(q) ||
        s.industries.some((i) => i.code.toUpperCase().includes(q))
    );
  }, [data, search]);

  const sectors = useMemo(() => groupBySector(filteredStocks), [filteredStocks]);

  function toggleTier(t: Tier) {
    setActiveTiers((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      // Don't allow zero — at least one tier must be active
      if (next.size === 0) next.add(t);
      return next;
    });
  }

  return (
    <div>
      <PageHeader
        icon={Network}
        title="Universe"
        subtitle="Knowledge-graph universe — sector → industry → stocks, tier-aware."
        accent="text-accent-violet"
        iconBg="bg-accent-violet/10"
      />

      {/* Stats strip */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mb-4">
          <div className="card p-3">
            <div className="text-[10px] uppercase tracking-wider text-text-muted">Total</div>
            <div className="text-xl font-semibold tabular-nums">{data.counts.total}</div>
            <div className="text-[10px] text-text-muted">stocks</div>
          </div>
          {(["A", "B", "C", "D"] as Tier[]).map((t) => {
            const tone = TIER_TONE[t];
            return (
              <div key={t} className="card p-3">
                <div className="text-[10px] uppercase tracking-wider text-text-muted">
                  {tone.label.split(" — ")[0]}
                </div>
                <div className={cn("text-xl font-semibold tabular-nums", tone.text)}>
                  {data.counts[t]}
                </div>
                <div className="text-[10px] text-text-muted">{tone.label.split(" — ")[1]}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* Filters bar */}
      <div className="card p-3 mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 flex-1 min-w-[200px]">
          <Search size={14} className="text-text-muted" />
          <input
            type="text"
            placeholder="Search ticker, name, or industry…"
            className="bg-transparent border-none outline-none text-[13px] flex-1 placeholder:text-text-muted"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-1">
          <span className="text-[10px] uppercase tracking-wider text-text-muted mr-2">
            Tiers
          </span>
          {(["A", "B", "C", "D"] as Tier[]).map((t) => {
            const active = activeTiers.has(t);
            return (
              <button
                key={t}
                onClick={() => toggleTier(t)}
                className={cn(
                  "badge text-[10px] tabular-nums px-2 py-0.5 transition-opacity",
                  TIER_TONE[t].badge,
                  active ? "opacity-100" : "opacity-30 hover:opacity-60"
                )}
              >
                {t}
              </button>
            );
          })}
        </div>
      </div>

      {/* Forthcoming-features banner */}
      <div className="card p-3 mb-4 flex items-start gap-2 border-l-[3px] border-l-accent-violet/40">
        <Info size={14} className="text-accent-violet shrink-0 mt-0.5" />
        <div className="text-[12px] text-text-secondary leading-relaxed">
          <span className="font-semibold text-text-primary">Hierarchy view</span> · Today this
          shows the <code className="font-mono text-accent-violet">stocks_universe</code> grouped
          by sector → industry. Force-directed graph with peer + supply-chain edges arrives
          after weeks 3-4 of the prototype (see{" "}
          <code className="font-mono text-text-muted">PROTOTYPE_PLAN.md</code>).
        </div>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[120px] w-full" />
          ))}
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="card p-4 border-l-[3px] border-l-accent-red/70">
          <div className="text-[13px] text-accent-redSoft">
            Failed to fetch universe. Make sure the API is running on :8000 and{" "}
            <code className="font-mono">load_tier_a()</code> has been called at least once.
          </div>
        </div>
      )}

      {/* Empty */}
      {data && filteredStocks.length === 0 && (
        <div className="card p-8 grid place-items-center text-center">
          <Database size={28} className="text-text-muted mb-3" />
          <div className="text-[14px] font-medium">No stocks match these filters</div>
          <div className="text-[12px] text-text-muted mt-1">
            Try clearing the search box or enabling more tiers.
          </div>
        </div>
      )}

      {/* Filtered count line */}
      {data && filteredStocks.length > 0 && search && (
        <div className="text-[11px] text-text-muted mb-3 flex items-center gap-1.5">
          <Globe size={11} />
          {filteredStocks.length} of {data.counts.total} stocks match{" "}
          <span className="font-mono text-accent-violet">{search}</span>
        </div>
      )}

      {/* Sector cards */}
      {data && sectors.length > 0 && (
        <div className="space-y-3">
          {sectors.map((sg) => (
            <SectorCard key={sg.sector} group={sg} totalStocks={data.counts.total} />
          ))}
        </div>
      )}
    </div>
  );
}
