"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Wallet, Building2, UserCircle2, Landmark, ArrowUp, ArrowDown, Layers } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatCurrency } from "@/lib/utils";

type Props = { symbol: string };
type Tab = "institutional" | "insider" | "congress";

const TABS: { key: Tab; label: string; icon: typeof Building2 }[] = [
  { key: "institutional", label: "Institutional", icon: Building2 },
  { key: "insider",       label: "Insider",       icon: UserCircle2 },
  { key: "congress",      label: "Congress",      icon: Landmark },
];

function partyChip(party?: string | null) {
  const p = (party || "").toLowerCase();
  if (p.startsWith("d")) return "bg-accent-blue/15 text-accent-blue border-accent-blue/30";
  if (p.startsWith("r")) return "bg-accent-red/15 text-accent-redSoft border-accent-red/30";
  return "bg-bg-card2 text-text-muted border-bg-borderHi";
}

function txnTone(tx?: string | null) {
  const t = (tx || "").toLowerCase();
  if (t.includes("buy") || t.includes("purchase") || t === "p") return { color: "text-accent-greenSoft", Icon: ArrowUp };
  if (t.includes("sell") || t.includes("sale") || t === "s")    return { color: "text-accent-redSoft", Icon: ArrowDown };
  return { color: "text-text-muted", Icon: Layers };
}

function fmtUsd(v: number | null | undefined): string {
  if (v == null || v <= 0) return "—";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

export function SmartMoneyCard({ symbol }: Props) {
  const [tab, setTab] = useState<Tab>("institutional");
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["smart-money", symbol],
    queryFn: () => stocksApi.smartMoney(symbol),
    staleTime: 6 * 60 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) {
    return (
      <section className="card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Wallet size={16} className="text-accent-cyan" />
          <h3 className="text-base font-semibold">Smart Money Flow</h3>
        </div>
        <Skeleton className="h-48 w-full" />
      </section>
    );
  }

  if (isError || !data) {
    return (
      <section className="card p-6">
        <div className="flex items-center gap-2 mb-3">
          <Wallet size={16} className="text-accent-cyan" />
          <h3 className="text-base font-semibold">Smart Money Flow</h3>
        </div>
        <p className="text-text-muted text-sm">{(error as Error)?.message || "Unavailable."}</p>
      </section>
    );
  }

  const inst = data.institutional;
  const ins  = data.insider;
  const con  = data.congress;

  // Header signal pills (one per source, color-coded by direction)
  const insiderPill = ins.cluster_buy
    ? { text: "Insider cluster-buy", tone: "bg-accent-green/15 text-accent-greenSoft border-accent-green/40" }
    : ins.total_buys > ins.total_sells
      ? { text: `Insiders ${ins.total_buys}↑ / ${ins.total_sells}↓`, tone: "bg-accent-green/10 text-accent-greenSoft border-accent-green/30" }
      : ins.total_sells > ins.total_buys
        ? { text: `Insiders ${ins.total_buys}↑ / ${ins.total_sells}↓`, tone: "bg-accent-red/10 text-accent-redSoft border-accent-red/30" }
        : { text: `Insiders ${ins.total_trades} trades`, tone: "bg-bg-card2 text-text-muted border-bg-borderHi" };

  const congressPill = con.net_sentiment === "bullish" || con.net_sentiment === "strong_buy" || con.net_sentiment === "buy"
    ? { text: `Politicians ${con.total_buys}↑ / ${con.total_sells}↓`, tone: "bg-accent-green/10 text-accent-greenSoft border-accent-green/30" }
    : con.net_sentiment === "bearish" || con.net_sentiment === "sell" || con.net_sentiment === "strong_sell"
      ? { text: `Politicians ${con.total_buys}↑ / ${con.total_sells}↓`, tone: "bg-accent-red/10 text-accent-redSoft border-accent-red/30" }
      : { text: `Politicians ${con.total_trades} trades`, tone: "bg-bg-card2 text-text-muted border-bg-borderHi" };

  return (
    <section className="card-subtle p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 flex-wrap">
          <Wallet size={16} className="text-accent-cyan" />
          <h3 className="text-base font-semibold">Smart Money Flow</h3>
          {data.from_cache && (
            <span className="text-[10px] uppercase tracking-wider text-text-muted">cached</span>
          )}
        </div>
        <div className="text-[10px] uppercase tracking-wider text-text-muted">
          last 90d insider · 180d congress · latest 13F
        </div>
      </div>

      {/* Top signal strip — at-a-glance pills */}
      <div className="flex items-center gap-2 flex-wrap mb-4">
        <span className={cn("badge text-[10px]", "bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30")}>
          {inst.total_known_holders} institutional holders
        </span>
        <span className={cn("badge text-[10px]", insiderPill.tone)}>{insiderPill.text}</span>
        <span className={cn("badge text-[10px]", congressPill.tone)}>{congressPill.text}</span>
      </div>

      <p className="text-sm text-text-secondary leading-relaxed mb-4 italic">{data.summary}</p>

      {/* Tab strip */}
      <div className="flex gap-1 mb-4 p-1 rounded-lg bg-bg-base border border-bg-border">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "flex-1 px-3 py-1.5 rounded-md text-xs font-medium flex items-center justify-center gap-1.5 transition-colors",
              tab === key
                ? "bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/40"
                : "text-text-secondary hover:text-text-primary"
            )}
          >
            <Icon size={12} />
            {label}
          </button>
        ))}
      </div>

      {/* ── Institutional ─────────────────────────────────────── */}
      {tab === "institutional" && (
        <>
          {inst.error ? (
            <p className="text-text-muted text-sm">{inst.error}</p>
          ) : inst.top_holders.length === 0 ? (
            <p className="text-text-muted text-sm">No institutional holdings tracked yet for {symbol}.</p>
          ) : (
            <div className="overflow-x-auto -mx-2">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-text-muted text-left uppercase tracking-wider border-b border-bg-border">
                    <th className="px-3 py-2">Holder</th>
                    <th className="px-3 py-2 text-right">% Outstanding</th>
                    <th className="px-3 py-2 text-right">Position Value</th>
                    <th className="px-3 py-2 text-right">As of</th>
                  </tr>
                </thead>
                <tbody>
                  {inst.top_holders.slice(0, 10).map((h, i) => (
                    <tr key={i} className="border-b border-bg-divider">
                      <td className="px-3 py-2">
                        <span className="font-medium text-text-primary">{h.name || "—"}</span>
                        {h.type && (
                          <span className="ml-2 text-[10px] text-text-muted uppercase tracking-wider">{h.type}</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {h.pct_outstanding != null ? `${h.pct_outstanding.toFixed(2)}%` : "—"}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmtUsd(h.value_usd)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-text-muted">{h.as_of || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── Insider ──────────────────────────────────────────── */}
      {tab === "insider" && (
        <>
          {ins.error ? (
            <p className="text-text-muted text-sm">{ins.error}</p>
          ) : ins.total_trades === 0 ? (
            <p className="text-text-muted text-sm">No insider transactions in the last 90 days.</p>
          ) : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
                <div className="bg-bg-base rounded-md p-2.5 border border-bg-border">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Buys</div>
                  <div className="text-base font-bold text-accent-greenSoft tabular-nums">{ins.total_buys}</div>
                </div>
                <div className="bg-bg-base rounded-md p-2.5 border border-bg-border">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Sells</div>
                  <div className="text-base font-bold text-accent-redSoft tabular-nums">{ins.total_sells}</div>
                </div>
                <div className="bg-bg-base rounded-md p-2.5 border border-bg-border">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Unique</div>
                  <div className="text-base font-bold tabular-nums">{ins.unique_insiders}</div>
                </div>
                <div className="bg-bg-base rounded-md p-2.5 border border-bg-border">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Net $</div>
                  <div className={cn(
                    "text-base font-bold tabular-nums",
                    (ins.net_value_usd ?? 0) >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft"
                  )}>
                    {(ins.net_value_usd ?? 0) >= 0 ? "+" : ""}{fmtUsd(Math.abs(ins.net_value_usd ?? 0))}
                  </div>
                </div>
              </div>
              {ins.cluster_buy && (
                <div className="bg-accent-green/5 border border-accent-green/30 rounded-md p-3 mb-3">
                  <span className="text-[10px] uppercase tracking-wider font-bold text-accent-greenSoft">Cluster buy detected</span>
                  <span className="text-text-secondary text-xs ml-2">2+ insiders bought within 7 days — historically a strong bullish signal.</span>
                </div>
              )}
              <div className="overflow-x-auto -mx-2">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-text-muted text-left uppercase tracking-wider border-b border-bg-border">
                      <th className="px-3 py-2"></th>
                      <th className="px-3 py-2">Insider</th>
                      <th className="px-3 py-2">Title</th>
                      <th className="px-3 py-2 text-right">Shares</th>
                      <th className="px-3 py-2 text-right">Value</th>
                      <th className="px-3 py-2 text-right">Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ins.recent_trades.slice(0, 8).map((t, i) => {
                      const tone = txnTone(t.transaction);
                      const Icon = tone.Icon;
                      return (
                        <tr key={i} className="border-b border-bg-divider">
                          <td className="px-3 py-2">
                            <Icon size={12} className={tone.color} strokeWidth={2.6} />
                          </td>
                          <td className="px-3 py-2 font-medium">{t.filer}</td>
                          <td className="px-3 py-2 text-text-muted text-[11px]">{t.title || "—"}</td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {t.shares != null ? t.shares.toLocaleString() : "—"}
                          </td>
                          <td className={cn("px-3 py-2 text-right tabular-nums", tone.color)}>
                            {fmtUsd(t.value_usd)}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums text-text-muted">{t.transaction_date || "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      {/* ── Congress ─────────────────────────────────────────── */}
      {tab === "congress" && (
        <>
          {con.error ? (
            <p className="text-text-muted text-sm">{con.error}</p>
          ) : con.total_trades === 0 ? (
            <p className="text-text-muted text-sm">No congressional trades disclosed in the last 180 days.</p>
          ) : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
                <div className="bg-bg-base rounded-md p-2.5 border border-bg-border">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Buys</div>
                  <div className="text-base font-bold text-accent-greenSoft tabular-nums">{con.total_buys}</div>
                </div>
                <div className="bg-bg-base rounded-md p-2.5 border border-bg-border">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Sells</div>
                  <div className="text-base font-bold text-accent-redSoft tabular-nums">{con.total_sells}</div>
                </div>
                <div className="bg-bg-base rounded-md p-2.5 border border-bg-border">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Politicians</div>
                  <div className="text-base font-bold tabular-nums">{con.unique_politicians}</div>
                </div>
                <div className="bg-bg-base rounded-md p-2.5 border border-bg-border">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Net</div>
                  <div className={cn(
                    "text-base font-bold uppercase tracking-wider",
                    (con.net_sentiment.includes("buy") || con.net_sentiment === "bullish") ? "text-accent-greenSoft"
                      : (con.net_sentiment.includes("sell") || con.net_sentiment === "bearish") ? "text-accent-redSoft"
                      : "text-text-muted"
                  )}>
                    {con.net_sentiment}
                  </div>
                </div>
              </div>
              <div className="overflow-x-auto -mx-2">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-text-muted text-left uppercase tracking-wider border-b border-bg-border">
                      <th className="px-3 py-2"></th>
                      <th className="px-3 py-2">Politician</th>
                      <th className="px-3 py-2">Chamber</th>
                      <th className="px-3 py-2 text-right">Amount</th>
                      <th className="px-3 py-2 text-right">Trade Date</th>
                      <th className="px-3 py-2 text-right">Filed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {con.recent_trades.slice(0, 8).map((t, i) => {
                      const tone = txnTone(t.transaction);
                      const Icon = tone.Icon;
                      const lateFile = (t.days_to_file ?? 0) > 45;
                      return (
                        <tr key={i} className="border-b border-bg-divider">
                          <td className="px-3 py-2">
                            <Icon size={12} className={tone.color} strokeWidth={2.6} />
                          </td>
                          <td className="px-3 py-2">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className="font-medium">{t.politician}</span>
                              <span className={cn("badge text-[9px] py-0", partyChip(t.party))}>
                                {(t.party || "?").charAt(0).toUpperCase()}
                              </span>
                              {t.state && <span className="text-[10px] text-text-muted">{t.state}</span>}
                            </div>
                            {t.committees.length > 0 && (
                              <div className="text-[10px] text-text-muted mt-0.5">
                                {t.committees.slice(0, 2).join(" · ")}
                              </div>
                            )}
                          </td>
                          <td className="px-3 py-2 text-text-muted text-[11px]">{t.chamber || "—"}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{t.amount_range || "—"}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-text-muted">{t.trade_date || "—"}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-text-muted">
                            {t.filed_date || "—"}
                            {lateFile && (
                              <span className="ml-1 text-accent-amber text-[9px]" title="Filed >45 days late (STOCK Act violation)">⚠</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="text-[10px] text-text-muted mt-3">
                Source: Capitol Trades. STOCK Act requires 45-day filing — late filers flagged ⚠.
                Disclosures lag the actual trade date by up to 45 days.
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
