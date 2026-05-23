"use client";

import { usePatentEvents } from "@/lib/hooks/use-patent-events";

function sourceLabel(srcs: string[]): string {
  const labels: Record<string, string> = {
    fda_orange_book: "FDA Orange Book",
    itc_edis: "ITC EDIS",
    sec_8k: "SEC 8-K",
  };
  return srcs.map((s) => labels[s] ?? s).join(" · ");
}

export function PatentEventsCard({ ticker }: { ticker: string }) {
  const { data, isLoading, error } = usePatentEvents(ticker);

  if (isLoading) return null;
  if (error || !data) return null;

  if (data.facts.length === 0) {
    return (
      <section className="card-subtle p-6 opacity-60">
        <h3 className="text-lg font-semibold mb-1">Patent Events</h3>
        <p className="text-sm text-text-secondary mb-2">{data.headline}</p>
        <p className="text-xs text-text-secondary italic">
          Consolidates FDA Orange Book patent-cliff dates, ITC §337 status, and material 8-K IP events (license deals, infringement outcomes). Empty when nothing material is happening — common for non-pharma tickers without recent IP-related filings.
        </p>
      </section>
    );
  }

  const borderClass =
    data.severity === "high"
      ? "border-l-4 border-red-500"
      : data.severity === "med"
      ? "border-l-4 border-yellow-500"
      : "";

  return (
    <section className={`card-subtle p-6 ${borderClass}`}>
      <h3 className="text-lg font-semibold mb-1">Patent Events</h3>
      <p className="text-sm text-text-secondary mb-4">{data.headline}</p>

      <ul className="space-y-2 text-sm">
        {data.facts.map((f, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="text-text-secondary">•</span>
            <span>
              {f.source_url ? (
                <a
                  href={f.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:underline"
                >
                  {f.text}
                </a>
              ) : (
                f.text
              )}
            </span>
          </li>
        ))}
      </ul>

      {data.implications && data.implications.length > 0 && (
        <div className="mt-3 text-xs text-text-secondary">
          <span className="font-medium">Implications: </span>
          {data.implications.join(" · ")}
        </div>
      )}

      <p className="text-xs text-text-secondary mt-3">
        Sources: {sourceLabel(data.sources_used)} · As of{" "}
        {new Date(data.as_of).toLocaleDateString()}
      </p>
    </section>
  );
}
