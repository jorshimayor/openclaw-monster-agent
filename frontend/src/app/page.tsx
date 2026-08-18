"use client";

import { useEffect, useState } from "react";
import SystemStatusCard from "@/components/dashboard/SystemStatusCard";
import AgentRosterCard from "@/components/dashboard/AgentRosterCard";
import PipelineActivityLegend from "@/components/dashboard/PipelineActivityLegend";
import RecentKnowledgeCard from "@/components/dashboard/RecentKnowledgeCard";
import { api } from "@/lib/api";

export default function DashboardPage() {
  const [, setPing] = useState<number>(0);

  useEffect(() => {
    const id = setInterval(() => {
      api.health().then(() => setPing(Date.now())).catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-wider glow-text">
          ⟨ COMMAND CENTER · DASHBOARD ⟩
        </h1>
        <p className="text-xs text-matrix-dim mt-1 tracking-widest">
          REAL-TIME MULTI-AGENT ORCHESTRATION OVERVIEW
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SystemStatusCard />
        <AgentRosterCard />
        <PipelineActivityLegend />
        <RecentKnowledgeCard />
      </div>
    </div>
  );
}
