"use client";

import { useExecChanges } from "@/lib/hooks/use-exec-changes";

export function ExecChangesCard({ ticker }: { ticker: string }) {
  const { data, isLoading, error } = useExecChanges(ticker);

  if (isLoading) return null;
  if (error || !data) return null;
  if (data.facts.length === 0) return null;

  const borderClass =
    data.severity === "high"
      ? "border-l-4 border-red-500"
      : data.severity === "med"
        ? "border-l-4 border-yellow-500"
        : "";

  return (
    <section className={`card-subtle p-6 ${borderClass}`}>
      <h3 className="text-lg font-semibold mb-1">Executive Changes</h3>
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
        Source: SEC 8-K Item 5.02 · As of {new Date(data.as_of).toLocaleDateString()}
      </p>
    </section>
  );
}
