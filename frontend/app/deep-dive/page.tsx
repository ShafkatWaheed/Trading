"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Search, ArrowRight, Layers } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { TickerSearchInput } from "@/components/ui/ticker-search-input";

const POPULAR = ["AAPL", "NVDA", "MSFT", "TSLA", "GOOG", "AMZN", "META", "AMD", "PLTR", "LLY"];

export default function DeepDiveLandingPage() {
  const router = useRouter();

  const goTo = (sym: string) => {
    const v = sym.trim().toUpperCase();
    if (v) router.push(`/deep-dive/${encodeURIComponent(v)}`);
  };

  return (
    <div>
      <PageHeader
        icon={Search}
        title="Deep Dive"
        subtitle="Run the full 16-indicator analysis pipeline on a single stock."
        accent="text-accent-violet"
        iconBg="bg-accent-violet/10"
      />

      <Link
        href="/deep-dive/compare"
        className="card card-hover p-4 mb-4 flex items-center justify-between group bg-gradient-to-r from-accent-violet/5 to-bg-card border-l-4 border-accent-violet/40"
      >
        <div className="flex items-center gap-3">
          <Layers size={18} className="text-accent-violet" />
          <div>
            <div className="text-sm font-semibold">Compare Multiple Stocks</div>
            <div className="text-xs text-text-muted">
              Run analysis on up to 6 tickers side by side
            </div>
          </div>
        </div>
        <ArrowRight size={14} className="text-accent-violet group-hover:translate-x-1 transition-transform" />
      </Link>

      <div className="card p-8">
        <TickerSearchInput
          onPick={goTo}
          placeholder="Search ticker, name, or sector (e.g. AAPL, Apple, Technology)"
          tone="violet"
          autoFocus
          clearOnPick={false}
        />

        <div className="mt-6 pt-6 border-t border-bg-border">
          <div className="text-xs uppercase tracking-wider text-text-muted mb-3">Popular</div>
          <div className="flex flex-wrap gap-2">
            {POPULAR.map((t) => (
              <button
                key={t}
                onClick={() => goTo(t)}
                className="bg-bg-base border border-bg-border hover:border-accent-violet/40 hover:text-accent-violet px-3 py-1.5 rounded-md text-xs font-mono transition-colors"
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
