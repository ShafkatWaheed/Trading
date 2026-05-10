"use client";

import Link from "next/link";
import type { MultiAgentResult } from "@/lib/api/types";
import { Network, ArrowDown } from "lucide-react";
import { cn } from "@/lib/utils";

const AGENT_META: Record<string, { icon: string; color: string; label: string }> = {
  momentum:    { icon: "🚀", color: "text-accent-greenSoft", label: "Momentum" },
  value:       { icon: "📊", color: "text-accent-blue",      label: "Value" },
  contrarian:  { icon: "🔄", color: "text-accent-amber",     label: "Contrarian" },
  macro:       { icon: "🌍", color: "text-accent-violet",    label: "Macro" },
  disruption:  { icon: "🔗", color: "text-accent-violet",    label: "Disruption" },
  insider:     { icon: "🕵️", color: "text-accent-cyan",      label: "Insider" },
  options:     { icon: "📡", color: "text-accent-pink",      label: "Options" },
  flow:        { icon: "💧", color: "text-accent-blue",      label: "Flow" },
};

export function MultiAgentTree({ result }: { result: MultiAgentResult }) {
  if (!result.ok) {
    return (
      <div className="card p-4 border-l-4 border-accent-red/40">
        <p className="text-accent-redSoft text-sm">{result.error || "Multi-agent run failed"}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-accent-violet font-bold">
        <Network size={14} />
        Multi-Agent Pipeline
      </div>

      {/* Market Pulse node */}
      <div className="card p-4 border-l-4 border-accent-blue/40">
        <div className="text-xs uppercase tracking-wider text-accent-blue font-bold mb-1">Market Pulse</div>
        {result.macro_context && (
          <p className="text-xs text-text-secondary">{result.macro_context}</p>
        )}
        {result.sectors_analyzed.length > 0 && (
          <p className="text-[11px] text-text-muted mt-1">
            Inflowing sectors: {result.sectors_analyzed.join(" · ")}
          </p>
        )}
      </div>

      <ArrowDown className="mx-auto text-text-muted" size={16} />

      {/* 8 Agent picks */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {Object.entries(result.agent_picks).map(([agentKey, picks]) => {
          const meta = AGENT_META[agentKey] || { icon: "🤖", color: "text-text-secondary", label: agentKey };
          return (
            <div key={agentKey} className="card p-3">
              <div className="flex items-center gap-1.5 mb-2 pb-2 border-b border-bg-border">
                <span>{meta.icon}</span>
                <span className={cn("text-xs font-bold", meta.color)}>{meta.label}</span>
                <span className="text-[10px] text-text-muted ml-auto">{picks.length}</span>
              </div>
              {picks.length === 0 ? (
                <p className="text-[11px] text-text-muted">No picks</p>
              ) : (
                <ul className="space-y-1.5">
                  {picks.map((p, i) => (
                    <li key={i}>
                      <Link
                        href={`/deep-dive/${p.symbol}`}
                        className="flex items-center justify-between text-xs hover:bg-bg-card2 rounded p-1 -m-1 transition-colors"
                      >
                        <div className="font-mono font-semibold">{p.symbol}</div>
                        <div className="flex items-center gap-2">
                          {p.sector && (
                            <span className="text-[10px] text-text-muted truncate max-w-20">{p.sector}</span>
                          )}
                          <span className="tabular-nums text-text-muted">{p.score.toFixed(0)}</span>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>

      <ArrowDown className="mx-auto text-text-muted" size={16} />

      {/* Risk Manager + Final portfolio */}
      <div className="card p-5 border-l-4 border-accent-red/40 bg-accent-red/5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xl">🛡</span>
          <h3 className="text-sm font-bold text-accent-redSoft">Risk Manager · Final Portfolio</h3>
          <span className="badge bg-accent-red/10 text-accent-redSoft border-accent-red/30 text-[10px] ml-auto">
            {result.final_portfolio.length} picks
          </span>
        </div>

        {result.risk_manager_reasoning && (
          <p className="text-xs text-text-secondary mb-3 italic leading-relaxed">
            {result.risk_manager_reasoning.length > 280
              ? result.risk_manager_reasoning.slice(0, 280) + "…"
              : result.risk_manager_reasoning}
          </p>
        )}

        {result.final_portfolio.length === 0 ? (
          <p className="text-xs text-text-muted">No picks made it through Risk Manager veto.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {result.final_portfolio.map((p, i) => {
              const meta = p.agent ? AGENT_META[p.agent] : null;
              return (
                <Link
                  key={i}
                  href={`/deep-dive/${p.symbol}`}
                  className="card p-3 hover:bg-bg-card2 transition-colors flex items-center justify-between gap-2"
                >
                  <div className="min-w-0">
                    <div className="font-mono font-bold text-sm">{p.symbol}</div>
                    {meta && (
                      <div className={cn("text-[10px] uppercase tracking-wider", meta.color)}>
                        {meta.icon} {meta.label}
                      </div>
                    )}
                  </div>
                  <div className="tabular-nums font-semibold text-accent-greenSoft text-sm">
                    {p.score.toFixed(0)}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
