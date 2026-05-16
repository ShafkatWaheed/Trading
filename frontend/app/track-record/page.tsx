"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { LineChart, Loader2, PlayCircle } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { SectionHeader } from "@/components/deep-dive/section-header";
import { AccuracySummary } from "@/components/track-record/accuracy-summary";
import { FeatureComparison } from "@/components/track-record/feature-comparison";
import { TopWinsLosses } from "@/components/track-record/top-wins-losses";
import { DecisionsLog } from "@/components/track-record/decisions-log";
import { trackRecordApi } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";

const WINDOWS: { value: number; label: string }[] = [
  { value: 30,   label: "30D" },
  { value: 90,   label: "90D" },
  { value: 365,  label: "1Y" },
  { value: 3650, label: "All" },
];

export default function TrackRecordPage() {
  const [days, setDays] = useState<number>(90);

  const evalMutation = useMutation({
    mutationFn: () => trackRecordApi.evaluateNow(),
  });

  return (
    <div>
      <PageHeader
        icon={LineChart}
        title="AI Track Record"
        subtitle="Is the AI actually right? Every Recommendation, AI Analyst, and Bubble Score verdict gets graded against real price moves after its prediction window passes."
        accent="text-accent-blue"
        iconBg="bg-accent-blue/10"
        trailing={
          <button
            onClick={() => evalMutation.mutate()}
            disabled={evalMutation.isPending}
            title="Grade any matured decisions right now (the daily cron runs at 5:15 PM ET automatically)."
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors",
              "bg-bg-card hover:bg-bg-card2 border border-bg-borderHi text-text-secondary hover:text-text-primary",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            {evalMutation.isPending
              ? <Loader2 size={13} className="animate-spin" />
              : <PlayCircle size={13} />}
            Evaluate now
          </button>
        }
      />

      {evalMutation.isSuccess && evalMutation.data && (
        <div className="mb-5 text-[12px] text-text-secondary bg-bg-card2/60 border border-bg-border rounded-md p-3 leading-relaxed">
          <strong className="text-text-primary">Evaluator ran:</strong>{" "}
          {evalMutation.data.evaluated} graded · {evalMutation.data.correct} correct ·{" "}
          {evalMutation.data.skipped_pending} still pending · {evalMutation.data.skipped_no_price} skipped (no price)
        </div>
      )}
      {evalMutation.isError && (
        <div className="mb-5 text-[12px] text-accent-redSoft bg-accent-red/5 border border-accent-red/30 rounded-md p-3">
          Evaluator failed: {(evalMutation.error as Error).message}
        </div>
      )}

      <div className="flex items-center gap-2 mb-6">
        <span className="text-[11px] uppercase tracking-wider text-text-muted">Window:</span>
        {WINDOWS.map((w) => (
          <button
            key={w.value}
            onClick={() => setDays(w.value)}
            className={cn(
              "px-2.5 py-1 rounded text-[12px] font-medium tabular-nums transition-colors",
              days === w.value
                ? "bg-bg-card2 text-text-primary"
                : "text-text-muted hover:text-text-secondary hover:bg-bg-card/60",
            )}
          >
            {w.label}
          </button>
        ))}
      </div>

      <div className="space-y-6">
        <SectionHeader index={1} label="Overall" subtitle="how often is the AI right · what's the average payoff" />
        <AccuracySummary days={days} />

        <SectionHeader index={2} label="By feature" subtitle="Recommendation vs. AI Analyst vs. Bubble Score" />
        <FeatureComparison days={days} />

        <SectionHeader index={3} label="Top wins & misses" subtitle="biggest moves where the AI was right vs. wrong" />
        <TopWinsLosses days={days} />

        <SectionHeader index={4} label="Decisions log" subtitle="raw record of every AI verdict — click to expand" />
        <DecisionsLog />
      </div>
    </div>
  );
}
