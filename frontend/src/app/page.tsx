import SystemStatusCard from "@/components/dashboard/SystemStatusCard";
import CommitmentsCard from "@/components/dashboard/CommitmentsCard";
import AgentRosterCard from "@/components/dashboard/AgentRosterCard";
import PipelineActivityLegend from "@/components/dashboard/PipelineActivityLegend";
import RecentKnowledgeCard from "@/components/dashboard/RecentKnowledgeCard";

/** Each card owns its own polling — the page-level heartbeat that used to live
 *  here pinged /api/health every 5s and threw the result away. */
export default function DashboardPage() {
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
        <CommitmentsCard />
        <AgentRosterCard />
        <PipelineActivityLegend />
        <RecentKnowledgeCard />
      </div>
    </div>
  );
}
