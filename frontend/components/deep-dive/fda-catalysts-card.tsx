"use client";

import { useFdaCatalysts } from "@/lib/hooks/use-fda-catalysts";

export function FdaCatalystsCard({ ticker }: { ticker: string }) {
  const { data, isLoading, error } = useFdaCatalysts(ticker);

  if (isLoading) return null;
  if (error || !data) return null;

  if (data.facts.length === 0) {
    return (
      <section className="card-subtle p-6 opacity-60">
        <h3 className="text-lg font-semibold mb-1">FDA Catalysts</h3>
        <p className="text-sm text-text-secondary mb-2">{data.headline}</p>
        <p className="text-xs text-text-secondary italic">
          Surfaces FDA drug applications + PDUFA dates from openFDA. Empty for non-pharma tickers — common for non-biotech/non-pharma companies.
        </p>
      </section>
    );
  }

  return (
    <section className="card-subtle p-6">
      <h3 className="text-lg font-semibold mb-1">FDA Catalysts</h3>
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
      <p className="text-xs text-text-secondary mt-3">
        Source: openFDA · As of {new Date(data.as_of).toLocaleDateString()}
      </p>
    </section>
  );
}
