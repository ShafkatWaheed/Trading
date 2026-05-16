"use client";

import { useQuery } from "@tanstack/react-query";
import { Newspaper, ExternalLink } from "lucide-react";
import { stocksApi } from "@/lib/api/endpoints";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Props = { symbol: string };

function dotClass(s: string): string {
  if (s === "bullish") return "bg-accent-greenSoft";
  if (s === "bearish") return "bg-accent-redSoft";
  return "bg-text-dim";
}

function netToneClass(net: string): string {
  if (net === "bullish") return "text-accent-greenSoft";
  if (net === "bearish") return "text-accent-redSoft";
  if (net === "mixed")   return "text-accent-amber";
  return "text-text-muted";
}

function shortDate(iso?: string | null): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return iso.slice(0, 10);
  }
}

export function NewsFeed({ symbol }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["news-feed", symbol],
    queryFn: () => stocksApi.newsFeed(symbol),
    staleTime: 15 * 60 * 1000,
    enabled: Boolean(symbol),
  });

  if (isLoading) {
    return (
      <section className="card-subtle p-6">
        <div className="flex items-center gap-2 mb-4">
          <Newspaper size={16} className="text-accent-cyan" />
          <h3 className="text-base font-semibold">Recent News</h3>
        </div>
        <Skeleton className="h-44 w-full" />
      </section>
    );
  }

  if (isError || !data) {
    return null;
  }

  const items = data.items || [];

  return (
    <section className="card-subtle p-6">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Newspaper size={16} className="text-accent-cyan" />
          <h3 className="text-base font-semibold">Recent News</h3>
          {data.from_cache && (
            <span className="text-[10px] uppercase tracking-wider text-text-muted">cached</span>
          )}
        </div>
        <div className="flex items-center gap-3 text-[11px]">
          <span className="text-text-muted uppercase tracking-wider">net sentiment</span>
          <span className={cn("font-bold uppercase tracking-wider", netToneClass(data.net_sentiment))}>
            {data.net_sentiment}
          </span>
          <span className="text-text-dim tabular-nums">
            {data.bull_count}↑ · {data.bear_count}↓ · {data.neutral_count}=
          </span>
        </div>
      </div>

      {items.length === 0 ? (
        <p className="text-text-muted text-sm">No recent news found for {symbol}.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((it, i) => (
            <li
              key={i}
              className="flex items-start gap-3 p-2.5 rounded-md hover:bg-bg-base transition-colors"
            >
              <span className={cn("mt-1.5 w-2 h-2 rounded-full shrink-0", dotClass(it.sentiment))} title={it.sentiment} />
              <div className="flex-1 min-w-0">
                <a
                  href={it.url || undefined}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group inline-flex items-start gap-1.5"
                >
                  <span className="text-sm text-text-primary group-hover:text-accent-cyan font-medium leading-snug">
                    {it.title}
                  </span>
                  {it.url && (
                    <ExternalLink size={11} className="text-text-muted group-hover:text-accent-cyan mt-1 shrink-0" />
                  )}
                </a>
                <div className="flex items-center gap-2 mt-1 text-[10px] text-text-muted">
                  {it.source && <span>{it.source}</span>}
                  {it.published && <><span>·</span><span>{shortDate(it.published)}</span></>}
                </div>
                {it.snippet && (
                  <p className="text-xs text-text-secondary mt-1 leading-relaxed line-clamp-2">{it.snippet}</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <p className="text-[10px] text-text-muted mt-3 pt-3 border-t border-bg-border">
        Headlines via Tavily/Exa. Sentiment is rule-based on title + snippet keywords (not LLM).
      </p>
    </section>
  );
}
