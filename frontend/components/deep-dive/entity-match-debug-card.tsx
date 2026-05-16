"use client";

import { useEntityMatches } from "@/lib/hooks/use-entity-matches";

function methodBadge(method: string, confidence: number) {
  if (method === "no_match")
    return (
      <span className="px-1.5 py-0.5 text-xs rounded bg-red-100 text-red-800">
        no match
      </span>
    );
  if (method.startsWith("exact_"))
    return (
      <span className="px-1.5 py-0.5 text-xs rounded bg-green-100 text-green-800">
        {method} · {confidence.toFixed(2)}
      </span>
    );
  if (method === "fuzzy") {
    const tone =
      confidence >= 0.95
        ? "bg-green-100 text-green-800"
        : confidence >= 0.9
        ? "bg-yellow-100 text-yellow-800"
        : "bg-orange-100 text-orange-800";
    return (
      <span className={`px-1.5 py-0.5 text-xs rounded ${tone}`}>
        fuzzy · {confidence.toFixed(2)}
      </span>
    );
  }
  return (
    <span className="px-1.5 py-0.5 text-xs rounded bg-gray-100 text-gray-700">
      {method}
    </span>
  );
}

export function EntityMatchDebugCard({ ticker }: { ticker: string }) {
  const { data, isLoading, error } = useEntityMatches(ticker);

  if (isLoading) return null;
  if (error || !data || data.matches.length === 0) return null;

  return (
    <section className="card-muted p-6">
      <h3 className="text-lg font-semibold mb-1">Entity Match Debug</h3>
      <p className="text-xs text-text-secondary mb-4">
        How each data source resolved free-text names to{" "}
        <strong>{ticker}</strong>. Useful for auditing fuzzy matches and
        ruling out misattribution.
      </p>
      <ul className="space-y-4 text-sm">
        {data.matches.map((m, i) => (
          <li key={i} className="border-l-2 border-bg-border pl-3">
            <div className="flex items-center justify-between mb-1">
              <span className="font-medium">{m.source}</span>
              {methodBadge(m.method, m.confidence)}
            </div>
            <div className="text-xs text-text-secondary">
              Input: <span className="font-mono">&quot;{m.input_name}&quot;</span>
              {m.matched_alias && (
                <>
                  {" → "}
                  <span className="font-mono">&quot;{m.matched_alias}&quot;</span>
                </>
              )}
            </div>
            {m.rejected.length > 0 && (
              <details className="mt-1">
                <summary className="text-xs cursor-pointer text-text-secondary hover:text-text-primary">
                  {m.rejected.length} alternative
                  {m.rejected.length === 1 ? "" : "s"} considered
                </summary>
                <ul className="mt-1 ml-3 space-y-0.5 text-xs font-mono text-text-secondary">
                  {m.rejected.map((r, j) => (
                    <li key={j}>
                      {r.ticker.padEnd(6)} &quot;{r.alias_name}&quot; · score=
                      {r.score.toFixed(3)}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
