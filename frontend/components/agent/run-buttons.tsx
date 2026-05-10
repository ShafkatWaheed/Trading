"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Play, Loader2, Network, AlertTriangle, StopCircle, PlayCircle } from "lucide-react";
import { agentApi } from "@/lib/api/endpoints";
import type { MultiAgentResult, AgentCycleResult } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type Props = {
  rmPicks: number;
  minScore: number;
  isRunning?: boolean;
  onMultiResult?: (r: MultiAgentResult | null) => void;
  onSingleResult?: (r: AgentCycleResult | null) => void;
  overdue?: boolean;
};

export function RunButtons({ rmPicks, minScore, isRunning, onMultiResult, onSingleResult, overdue }: Props) {
  const qc = useQueryClient();

  const singleMutation = useMutation({
    mutationFn: () => agentApi.runSingle(),
    onSuccess: (r) => {
      onSingleResult?.(r);
      qc.invalidateQueries({ queryKey: ["agent"] });
      qc.invalidateQueries({ queryKey: ["portfolio"] });
    },
  });

  const multiMutation = useMutation({
    mutationFn: () => agentApi.runMulti({ rm_picks: rmPicks, min_score: minScore }),
    onSuccess: (r) => {
      onMultiResult?.(r);
      qc.invalidateQueries({ queryKey: ["agent"] });
    },
  });

  const stopMutation = useMutation({
    mutationFn: () => agentApi.stop(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agent"] }),
  });
  const resumeMutation = useMutation({
    mutationFn: () => agentApi.resume(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agent"] }),
  });

  const busy = singleMutation.isPending || multiMutation.isPending;

  return (
    <div>
      {overdue && (
        <div className="card p-3 mb-3 border-l-4 border-accent-amber/50 bg-accent-amber/5 flex items-center gap-2">
          <AlertTriangle size={14} className="text-accent-amber shrink-0" />
          <p className="text-xs text-accent-amber">
            Agent is overdue for a scheduled cycle. Click <span className="font-semibold">Single Agent Cycle</span> to run now.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <button
          onClick={() => singleMutation.mutate()}
          disabled={busy}
          className="card p-4 hover:bg-bg-card2 border-l-4 border-accent-blue/40 disabled:opacity-50 transition-colors text-left"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-accent-blue/10 grid place-items-center">
              {singleMutation.isPending ? (
                <Loader2 size={18} className="animate-spin text-accent-blue" />
              ) : (
                <Play size={18} className="text-accent-blue" />
              )}
            </div>
            <div>
              <div className="text-sm font-bold">Single Agent Cycle</div>
              <div className="text-xs text-text-muted">Run the unified TradingAgent once</div>
            </div>
          </div>
        </button>

        <button
          onClick={() => multiMutation.mutate()}
          disabled={busy}
          className="card p-4 hover:bg-bg-card2 border-l-4 border-accent-pink/40 disabled:opacity-50 transition-colors text-left"
        >
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-accent-pink/10 grid place-items-center">
              {multiMutation.isPending ? (
                <Loader2 size={18} className="animate-spin text-accent-pink" />
              ) : (
                <Network size={18} className="text-accent-pink" />
              )}
            </div>
            <div>
              <div className="text-sm font-bold">Multi-Agent Cycle</div>
              <div className="text-xs text-text-muted">8 agents + Risk Manager → final picks</div>
            </div>
          </div>
        </button>

        {isRunning ? (
          <button
            onClick={() => stopMutation.mutate()}
            disabled={stopMutation.isPending}
            className="card p-4 hover:bg-bg-card2 border-l-4 border-accent-red/40 disabled:opacity-50 transition-colors text-left"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-accent-red/10 grid place-items-center">
                {stopMutation.isPending ? (
                  <Loader2 size={18} className="animate-spin text-accent-redSoft" />
                ) : (
                  <StopCircle size={18} className="text-accent-redSoft" />
                )}
              </div>
              <div>
                <div className="text-sm font-bold">Stop Agent</div>
                <div className="text-xs text-text-muted">Pause scheduled cycles</div>
              </div>
            </div>
          </button>
        ) : (
          <button
            onClick={() => resumeMutation.mutate()}
            disabled={resumeMutation.isPending}
            className="card p-4 hover:bg-bg-card2 border-l-4 border-accent-green/40 disabled:opacity-50 transition-colors text-left"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-accent-green/10 grid place-items-center">
                {resumeMutation.isPending ? (
                  <Loader2 size={18} className="animate-spin text-accent-greenSoft" />
                ) : (
                  <PlayCircle size={18} className="text-accent-greenSoft" />
                )}
              </div>
              <div>
                <div className="text-sm font-bold">Resume Agent</div>
                <div className="text-xs text-text-muted">Re-enable scheduled cycles</div>
              </div>
            </div>
          </button>
        )}
      </div>

      {singleMutation.data?.error && (
        <p className="text-xs text-accent-redSoft mt-2">{singleMutation.data.error}</p>
      )}
      {multiMutation.data?.error && (
        <p className="text-xs text-accent-redSoft mt-2">{multiMutation.data.error}</p>
      )}
      {singleMutation.data?.ok && (
        <p className="text-xs text-accent-greenSoft mt-2">
          ✓ {singleMutation.data.trades_executed} trade{singleMutation.data.trades_executed === 1 ? "" : "s"} executed
        </p>
      )}
    </div>
  );
}
