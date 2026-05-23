"use client";

import { useBacklog } from "@/lib/hooks/use-backlog";

export function BacklogCard({ ticker }: { ticker: string }) {
  const { data, isLoading, error } = useBacklog(ticker);

  if (isLoading) return null;
  if (error || !data) return null;

  if (data.facts.length === 0) {
    return (
      <section className="card-subtle p-6 opacity-60">
        <h3 className="text-lg font-semibold mb-1">Government Contracts</h3>
        <p className="text-sm text-text-secondary mb-2">{data.headline}</p>
        <p className="text-xs text-text-secondary italic">
          Surfaces federal contract awards from USAspending. Empty when the ticker has no SAM.gov UEI seeded or no recent awards — most non-defense/non-IT companies.
        </p>
      </section>
    );
  }

  return (
    <section className="card-subtle p-6">
      <h3 className="text-lg font-semibold mb-1">Government Contracts</h3>
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
        Source: USAspending · As of {new Date(data.as_of).toLocaleDateString()}
      </p>
    </section>
  );
}
