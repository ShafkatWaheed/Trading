"use client";

import { useInnovation } from "@/lib/hooks/use-innovation";

export function InnovationCard({ ticker }: { ticker: string }) {
  const { data, isLoading, error } = useInnovation(ticker);

  if (isLoading) return null;
  if (error || !data) return null;
  if (data.facts.length === 0) return null; // Hide when no patent activity

  return (
    <section className="card-subtle p-6">
      <h3 className="text-lg font-semibold mb-1">Innovation</h3>
      <p className="text-sm text-text-secondary mb-4">{data.headline}</p>
      <ul className="space-y-2 text-sm">
        {data.facts.map((f, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="text-text-muted">•</span>
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
      <p className="text-xs text-text-muted mt-3">
        Source: USPTO PatentsView · As of {new Date(data.as_of).toLocaleDateString()}
      </p>
    </section>
  );
}
