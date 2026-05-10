"use client";

import { useState } from "react";
import { ChevronDown, Code, Activity, MessageSquare, Target } from "lucide-react";
import type { AiDecision } from "@/lib/api/types";
import { cn, formatPercent } from "@/lib/utils";

const AGENT_ICON: Record<string, string> = {
  momentum: "🚀",
  value: "📊",
  contrarian: "🔄",
  macro: "🌍",
  disruption: "🔗",
  insider: "🕵️",
  flow: "💧",
};

const AGENT_LABEL: Record<string, string> = {
  momentum: "Momentum",
  value: "Value",
  contrarian: "Contrarian",
  macro: "Macro",
  disruption: "Disruption",
  insider: "Insider Shadow",
  flow: "Flow Tracker",
};

function decisionTone(d: AiDecision["decision"]) {
  if (d === "BUY") return { bg: "bg-accent-green/10", text: "text-accent-greenSoft", border: "border-accent-green/40" };
  if (d === "SELL") return { bg: "bg-accent-red/10", text: "text-accent-redSoft", border: "border-accent-red/40" };
  return { bg: "bg-bg-card", text: "text-text-secondary", border: "border-bg-border" };
}

function actionTone(a: AiDecision["action"]) {
  if (a === "OPEN") return "border-l-accent-green/60 bg-accent-green/5";
  if (a === "CLOSE") return "border-l-accent-red/60 bg-accent-red/5";
  return "border-l-bg-border";
}

function regimeTone(r?: string | null) {
  if (!r) return "text-text-muted";
  if (r.toLowerCase().includes("bull")) return "text-accent-greenSoft";
  if (r.toLowerCase().includes("bear")) return "text-accent-redSoft";
  if (r.toLowerCase().includes("consolid")) return "text-accent-amber";
  return "text-text-secondary";
}

function sentimentTone(s?: string | null) {
  if (!s) return "text-text-muted";
  if (s === "Bullish") return "text-accent-greenSoft";
  if (s === "Bearish") return "text-accent-redSoft";
  return "text-accent-amber";
}

export function AiDecisionRow({ d, idx }: { d: AiDecision; idx: number }) {
  const [open, setOpen] = useState(false);
  const dt = decisionTone(d.decision);

  return (
    <div className={cn(
      "rounded-lg border border-bg-border border-l-[3px] overflow-hidden transition-colors",
      actionTone(d.action),
    )}>
      {/* Summary row */}
      <div className="px-3 py-2.5 flex items-center gap-3 text-xs">
        <span className="text-text-dim text-[10px] font-mono w-6 tabular-nums shrink-0">
          #{idx + 1}
        </span>
        <span className="font-mono text-text-secondary tabular-nums w-24 shrink-0">{d.date}</span>
        <span className={cn("badge font-bold w-14 text-center justify-center shrink-0", dt.bg, dt.text, dt.border)}>
          {d.decision}
        </span>
        <span className="text-text-secondary tabular-nums w-20 shrink-0">${d.price.toFixed(2)}</span>

        {d.regime && (
          <span className={cn("text-[10px] uppercase tracking-wider hidden sm:inline-flex items-center gap-1", regimeTone(d.regime))}>
            <Activity size={9} strokeWidth={2.4} /> {d.regime}
          </span>
        )}
        {d.sentiment && (
          <span className={cn("text-[10px] uppercase tracking-wider hidden md:inline-flex items-center gap-1", sentimentTone(d.sentiment))}>
            <MessageSquare size={9} strokeWidth={2.4} /> {d.sentiment}
          </span>
        )}

        <span className="text-[10px] text-text-muted ml-auto uppercase tracking-wider shrink-0">
          {d.action}
        </span>
        {d.pnl_percent != null && (
          <span className={cn(
            "tabular-nums font-semibold shrink-0",
            d.pnl_percent >= 0 ? "text-accent-greenSoft" : "text-accent-redSoft",
          )}>
            {formatPercent(d.pnl_percent)}
          </span>
        )}

        {d.prompt && (
          <button
            onClick={() => setOpen((v) => !v)}
            className="text-text-muted hover:text-text-primary inline-flex items-center gap-1 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded transition-colors hover:bg-bg-card2"
            title="Show full prompt sent to Claude"
          >
            <Code size={10} strokeWidth={2.4} />
            <span className="hidden sm:inline">Prompt</span>
            <ChevronDown size={10} className={cn("transition-transform", open && "rotate-180")} />
          </button>
        )}
      </div>

      {/* Expandable: trade plan + agent votes + prompt */}
      {open && (
        <div className="border-t border-bg-divider bg-bg-base/40 p-3 space-y-3">
          {d.trade_plan && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
              <PlanCell label="Entry" value={`$${d.trade_plan.entry.toFixed(2)}`} />
              <PlanCell label="Stop" value={`$${d.trade_plan.stop.toFixed(2)} (-${d.trade_plan.stop_pct}%)`} tone="text-accent-redSoft" />
              <PlanCell label="Target 1" value={`$${d.trade_plan.target1.toFixed(2)}`} tone="text-accent-greenSoft" />
              <PlanCell label="R/R" value={`${d.trade_plan.rr.toFixed(2)} : 1`} tone="text-accent-blue" icon={<Target size={9} strokeWidth={2.4} />} />
            </div>
          )}

          {d.agent_votes && d.agent_votes.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-base">🤝</span>
                <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
                  Agent Votes — {d.agent_votes.length} agents
                </span>
                <span className="text-[10px] text-text-dim ml-auto">
                  Consensus: <span className={cn(
                    "font-bold",
                    d.decision === "BUY" ? "text-accent-greenSoft"
                      : d.decision === "SELL" ? "text-accent-redSoft"
                      : "text-text-secondary"
                  )}>{d.decision}</span>
                </span>
              </div>
              <div className="space-y-1.5">
                {d.agent_votes.map((v) => {
                  const tone = v.vote === "BUY" ? "border-l-accent-green/60 bg-accent-green/5"
                    : v.vote === "SELL" ? "border-l-accent-red/60 bg-accent-red/5"
                    : "border-l-bg-border bg-bg-card2/40";
                  const voteTone = v.vote === "BUY" ? "text-accent-greenSoft"
                    : v.vote === "SELL" ? "text-accent-redSoft"
                    : "text-text-secondary";
                  const icon = AGENT_ICON[v.agent] || "🤖";
                  const label = AGENT_LABEL[v.agent] || v.agent;
                  return (
                    <div key={v.agent} className={cn("rounded-md border border-bg-divider border-l-[3px] px-3 py-2", tone)}>
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-sm">{icon}</span>
                        <span className="text-xs font-semibold text-text-primary">{label}</span>
                        <span className={cn("ml-auto text-[10px] font-bold tabular-nums", voteTone)}>
                          {v.vote}
                        </span>
                      </div>
                      {v.reason ? (
                        <p className="text-[11px] text-text-secondary leading-snug pl-7">
                          {v.reason}
                        </p>
                      ) : v.raw ? (
                        <p className="text-[11px] text-text-muted leading-snug pl-7 italic font-mono">
                          {v.raw.slice(0, 140)}
                        </p>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {d.prompt && (
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <Code size={11} className="text-accent-pink" strokeWidth={2.4} />
                <span className="text-[10px] uppercase tracking-wider text-text-muted font-semibold">
                  Prompt sent to Claude
                </span>
                <span className="text-[10px] text-text-dim ml-auto tabular-nums">
                  {d.prompt.length} chars
                </span>
              </div>
              <pre className="text-[11px] text-text-secondary leading-relaxed whitespace-pre-wrap bg-bg-base border border-bg-divider rounded-md p-3 overflow-x-auto font-mono max-h-96">
{d.prompt}
              </pre>
            </div>
          )}

          {d.raw_response && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-text-muted font-semibold mb-1">
                Claude's response
              </div>
              <div className="text-[11px] text-text-secondary bg-bg-base border border-bg-divider rounded-md p-2.5 font-mono">
                {d.raw_response}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PlanCell({ label, value, tone, icon }: { label: string; value: string; tone?: string; icon?: React.ReactNode }) {
  return (
    <div className="bg-bg-card2/60 border border-bg-divider rounded-md px-2.5 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-text-muted flex items-center gap-1">
        {icon}
        {label}
      </div>
      <div className={cn("font-semibold tabular-nums mt-0.5", tone || "text-text-primary")}>
        {value}
      </div>
    </div>
  );
}
