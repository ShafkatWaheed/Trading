"use client";

import { useState } from "react";
import type { AgentPersonality, RiskManagerInfo } from "@/lib/api/types";
import { ChevronDown, Shield } from "lucide-react";
import { cn } from "@/lib/utils";

const COLOR_TO_TONE: Record<string, { bg: string; text: string; border: string }> = {
  "#22c55e": { bg: "bg-accent-green/10", text: "text-accent-greenSoft", border: "border-accent-green/30" },
  "#3b82f6": { bg: "bg-accent-blue/10", text: "text-accent-blue", border: "border-accent-blue/30" },
  "#f59e0b": { bg: "bg-accent-amber/10", text: "text-accent-amber", border: "border-accent-amber/30" },
  "#ef4444": { bg: "bg-accent-red/10", text: "text-accent-redSoft", border: "border-accent-red/30" },
  "#8b5cf6": { bg: "bg-accent-violet/10", text: "text-accent-violet", border: "border-accent-violet/30" },
  "#06b6d4": { bg: "bg-accent-cyan/10", text: "text-accent-cyan", border: "border-accent-cyan/30" },
  "#ec4899": { bg: "bg-accent-pink/10", text: "text-accent-pink", border: "border-accent-pink/30" },
};

function tone(color: string) {
  return COLOR_TO_TONE[color] || { bg: "bg-bg-card", text: "text-text-secondary", border: "border-bg-border" };
}

function PersonalityCard({ p }: { p: AgentPersonality }) {
  const [expanded, setExpanded] = useState(false);
  const t = tone(p.color);
  return (
    <div className={cn("card border-l-4 overflow-hidden", t.border)}>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full p-4 text-left hover:bg-bg-card2 transition-colors"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="text-2xl">{p.icon}</span>
            <div className="min-w-0">
              <div className={cn("text-sm font-bold", t.text)}>{p.name}</div>
              <div className="text-[10px] uppercase tracking-wider text-text-muted">
                {p.kind === "data" ? "Data-driven" : "Opinion-based"} · {p.risk_tolerance}
              </div>
            </div>
          </div>
          <ChevronDown size={14} className={cn("text-text-muted transition-transform shrink-0 mt-1", expanded && "rotate-180")} />
        </div>
        <p className="text-xs text-text-secondary mt-2 italic">{p.tagline}</p>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-bg-border pt-3 text-xs space-y-3">
          <p className="text-text-secondary leading-relaxed">{p.philosophy}</p>

          {p.strengths.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-accent-greenSoft mb-1">Strengths</div>
              <ul className="space-y-0.5">
                {p.strengths.map((s) => <li key={s} className="text-text-secondary">+ {s}</li>)}
              </ul>
            </div>
          )}
          {p.weaknesses.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-accent-redSoft mb-1">Weaknesses</div>
              <ul className="space-y-0.5">
                {p.weaknesses.map((s) => <li key={s} className="text-text-secondary">− {s}</li>)}
              </ul>
            </div>
          )}
          {p.prioritizes.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-accent-blue mb-1">Prioritizes</div>
              <div className="flex flex-wrap gap-1">
                {p.prioritizes.map((s) => (
                  <span key={s} className="badge bg-accent-blue/10 text-accent-blue border-accent-blue/30 text-[10px]">{s}</span>
                ))}
              </div>
            </div>
          )}
          {p.avoids.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">Avoids</div>
              <div className="flex flex-wrap gap-1">
                {p.avoids.map((s) => (
                  <span key={s} className="badge bg-bg-base text-text-muted border-bg-border text-[10px]">{s}</span>
                ))}
              </div>
            </div>
          )}
          {p.ideal_market && (
            <div className="text-text-muted">
              <span className="uppercase tracking-wider text-[10px]">Ideal market: </span>
              <span>{p.ideal_market}</span>
            </div>
          )}
          {p.historical_edge && (
            <div className="text-text-muted">
              <span className="uppercase tracking-wider text-[10px]">Historical edge: </span>
              <span>{p.historical_edge}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function PersonalitiesGrid({
  agents,
  riskManager,
}: {
  agents: AgentPersonality[];
  riskManager: RiskManagerInfo;
}) {
  const opinion = agents.filter((a) => a.kind === "opinion");
  const data = agents.filter((a) => a.kind === "data");

  return (
    <div className="space-y-5">
      <section>
        <div className="text-xs uppercase tracking-wider text-accent-amber font-bold mb-1">
          Opinion-Based Agents
        </div>
        <p className="text-[11px] text-text-muted mb-3">
          Analyze charts, fundamentals, and market conditions
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {opinion.map((p) => <PersonalityCard key={p.key} p={p} />)}
        </div>
      </section>

      <section>
        <div className="text-xs uppercase tracking-wider text-accent-cyan font-bold mb-1">
          Data-Driven Agents
        </div>
        <p className="text-[11px] text-text-muted mb-3">
          Read live data feeds — insider trades, options flow, order books, supply chains
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {data.map((p) => <PersonalityCard key={p.key} p={p} />)}
        </div>
      </section>

      <section className="card p-5 border border-accent-red/40 bg-accent-red/5">
        <div className="flex items-start gap-3 mb-3">
          <span className="text-3xl">{riskManager.icon}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-base font-bold">{riskManager.name}</h3>
              <span className="badge bg-accent-red/10 text-accent-redSoft border-accent-red/40 text-[10px] font-bold">
                <Shield size={9} className="inline mr-1" /> VETO POWER
              </span>
            </div>
            <p className="text-xs text-accent-redSoft italic mt-0.5">{riskManager.tagline}</p>
          </div>
        </div>
        <p className="text-xs text-text-secondary leading-relaxed mb-3">
          {riskManager.philosophy}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {riskManager.checks.map((c) => (
            <span key={c} className="badge bg-accent-red/10 text-accent-redSoft border-accent-red/30 text-[10px]">
              {c}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}
