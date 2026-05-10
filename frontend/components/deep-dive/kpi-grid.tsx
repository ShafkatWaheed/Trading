"use client";

import type { DeepDive } from "@/lib/api/types";
import { MetricCard } from "@/components/ui/metric-card";
import { TrendingUp, TrendingDown, Shield, Activity, MessageSquare } from "lucide-react";

function confTone(conf: string): "green" | "amber" | "red" | "neutral" {
  const c = conf.toLowerCase();
  if (c.includes("high")) return "green";
  if (c.includes("low")) return "red";
  return "amber";
}

function riskTone(rating: number): "green" | "amber" | "red" {
  if (rating <= 2) return "green";
  if (rating >= 4) return "red";
  return "amber";
}

function sentTone(score: number | null | undefined): "green" | "amber" | "red" | "neutral" {
  if (score == null) return "neutral";
  if (score > 0.3) return "green";
  if (score < -0.3) return "red";
  return "amber";
}

export function KpiGridDeepDive({ data }: { data: DeepDive }) {
  const periodChg = data.period_change?.change_pct ?? 0;
  const positive = periodChg > 0;
  const negative = periodChg < 0;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <MetricCard
        align="center"
        label="Price"
        icon={positive ? <TrendingUp size={11} className="text-accent-greenSoft" /> : negative ? <TrendingDown size={11} className="text-accent-redSoft" /> : null}
        value={data.price != null ? `$${data.price.toFixed(2)}` : "—"}
        hint={
          data.period_change && periodChg !== 0
            ? `${positive ? "↑" : negative ? "↓" : ""} ${periodChg >= 0 ? "+" : ""}${periodChg.toFixed(1)}% over ${data.period}`
            : "Last close"
        }
      />
      <MetricCard
        align="center"
        label="Confidence"
        icon={<Activity size={11} />}
        value={data.confidence}
        tone={confTone(data.confidence)}
        hint="Signal alignment"
      />
      <MetricCard
        align="center"
        label="Risk Level"
        icon={<Shield size={11} />}
        value={`${data.risk_rating}/5`}
        tone={riskTone(data.risk_rating)}
        hint={`${data.risk_label} risk`}
      />
      <MetricCard
        align="center"
        label="Sentiment"
        icon={<MessageSquare size={11} />}
        value={
          data.sentiment_score != null
            ? `${data.sentiment_score > 0 ? "+" : ""}${data.sentiment_score.toFixed(2)}`
            : "—"
        }
        tone={sentTone(data.sentiment_score)}
        hint="News mood"
      />
    </div>
  );
}
