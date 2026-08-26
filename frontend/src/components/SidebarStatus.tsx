"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Snapshot {
  api: "online" | "offline" | "checking";
  agentsReady: number | null;
  agentsTotal: number | null;
  queue: number | null;
  overdue: number | null;
}

const INITIAL: Snapshot = {
  api: "checking",
  agentsReady: null,
  agentsTotal: null,
  queue: null,
  overdue: null
};

/**
 * The sidebar's live vitals. This block previously rendered a static
 * "ONLINE · 8/8 · Queue 0" that never changed, including when the backend
 * was unreachable. Anything unknown renders "—".
 */
export default function SidebarStatus() {
  const [snap, setSnap] = useState<Snapshot>(INITIAL);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        await api.health();
      } catch {
        if (!cancelled) setSnap({ ...INITIAL, api: "offline" });
        return;
      }
      const [agents, tasks, commitments] = await Promise.all([
        api.listAgents().catch(() => null),
        api.listTasks().catch(() => null),
        api.listCommitments("open").catch(() => null)
      ]);
      if (cancelled) return;
      setSnap({
        api: "online",
        agentsReady: agents ? agents.filter((a) => a.status === "READY").length : null,
        agentsTotal: agents ? agents.length : null,
        queue: tasks
          ? tasks.filter((t) => t.status === "queued" || t.status === "running").length
          : null,
        overdue: commitments ? commitments.filter((c) => c.overdue_sec > 0).length : null
      });
    };

    poll();
    const id = setInterval(poll, 10000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const dot =
    snap.api === "online"
      ? "bg-matrix animate-pulse"
      : snap.api === "offline"
      ? "bg-danger"
      : "bg-warning animate-pulse";

  return (
    <div className="space-y-1.5 text-xs">
      <div className="flex justify-between">
        <span className="text-matrix-dim">API</span>
        <span className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${dot}`} />
          {snap.api === "checking" ? "CHECKING" : snap.api.toUpperCase()}
        </span>
      </div>
      <div className="flex justify-between">
        <span className="text-matrix-dim">Nodes</span>
        <span>
          {snap.agentsTotal === null ? "—" : `${snap.agentsReady} / ${snap.agentsTotal}`}
        </span>
      </div>
      <div className="flex justify-between">
        <span className="text-matrix-dim">Queue</span>
        <span>{snap.queue === null ? "—" : snap.queue}</span>
      </div>
      <div className="flex justify-between">
        <span className="text-matrix-dim">Overdue</span>
        <span className={snap.overdue ? "text-danger" : undefined}>
          {snap.overdue === null ? "—" : snap.overdue}
        </span>
      </div>
    </div>
  );
}
