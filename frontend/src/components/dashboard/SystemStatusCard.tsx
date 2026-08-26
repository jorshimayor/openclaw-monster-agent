"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Server, Activity, Cpu, Database } from "lucide-react";

interface HealthInfo {
  status: "online" | "offline" | "unknown";
  latency: number | null;
  activeTasks: number | null;
  version: string | null;
  dbEngine: boolean | null;
  mcpRunning: number | null;
  mcpConfigured: number | null;
}

const INITIAL: HealthInfo = {
  status: "unknown",
  latency: null,
  activeTasks: null,
  version: null,
  dbEngine: null,
  mcpRunning: null,
  mcpConfigured: null
};

/**
 * Everything here is measured, not asserted. The card previously showed a
 * hardcoded "99.97% uptime / 23ms / v1.0.0" that stayed green while the
 * backend was down — anything this component cannot verify now renders as "—".
 */
export default function SystemStatusCard() {
  const [health, setHealth] = useState<HealthInfo>(INITIAL);

  useEffect(() => {
    let cancelled = false;

    const ping = async () => {
      const t0 = performance.now();
      let latency: number | null = null;
      let version: string | null = null;
      try {
        const h = await api.health();
        latency = Math.round(performance.now() - t0);
        version = typeof h?.version === "string" ? h.version : null;
      } catch {
        if (!cancelled) setHealth({ ...INITIAL, status: "offline" });
        return;
      }

      // Secondary reads are allowed to fail without flipping the card to
      // offline — the health probe already answered.
      const [diag, tasks] = await Promise.all([
        api.healthDiag().catch(() => null),
        api.listTasks().catch(() => null)
      ]);

      if (cancelled) return;
      setHealth({
        status: "online",
        latency,
        version,
        activeTasks: tasks
          ? tasks.filter((t) => t.status === "running" || t.status === "queued").length
          : null,
        dbEngine: diag ? Boolean(diag?.database?.engine_initialized) : null,
        mcpRunning: diag ? (diag?.mcp_servers?.running?.length ?? null) : null,
        mcpConfigured: diag ? (diag?.mcp_servers?.configured?.length ?? null) : null
      });
    };

    ping();
    const id = setInterval(ping, 10000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const dash = (v: unknown) => (v === null || v === undefined ? "—" : String(v));

  const items = [
    {
      icon: <Cpu className="w-4 h-4" />,
      label: "HEALTH LATENCY",
      value: health.latency === null ? "—" : `${health.latency}ms`,
      sub: "GET /api/health"
    },
    {
      icon: <Activity className="w-4 h-4" />,
      label: "ACTIVE TASKS",
      value: dash(health.activeTasks),
      sub: "queued + running"
    },
    {
      icon: <Database className="w-4 h-4" />,
      label: "DATABASE",
      value:
        health.dbEngine === null ? "—" : health.dbEngine ? "CONNECTED" : "OFFLINE",
      sub: "async engine"
    },
    {
      icon: <Server className="w-4 h-4" />,
      label: "MCP SERVERS",
      value:
        health.mcpRunning === null || health.mcpConfigured === null
          ? "—"
          : `${health.mcpRunning} / ${health.mcpConfigured}`,
      sub: health.version ? `api v${health.version}` : "running / configured"
    }
  ];

  const badgeVariant =
    health.status === "online" ? "success" : health.status === "offline" ? "error" : "warning";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm tracking-widest flex items-center justify-between">
          <span>SYSTEM STATUS</span>
          <Badge variant={badgeVariant}>
            <span className="flex items-center gap-1.5">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  health.status === "online"
                    ? "bg-success animate-pulse"
                    : health.status === "offline"
                    ? "bg-danger"
                    : "bg-warning animate-pulse"
                }`}
              />
              {health.status === "unknown" ? "CHECKING" : health.status.toUpperCase()}
            </span>
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          {items.map((it) => (
            <div
              key={it.label}
              className="rounded border border-matrix/20 bg-bg/50 p-4"
            >
              <div className="flex items-center gap-2 text-matrix-dim text-[10px] tracking-widest mb-2">
                {it.icon}
                {it.label}
              </div>
              <div className="text-xl font-bold glow-text tracking-wider">
                {it.value}
              </div>
              <div className="text-[10px] text-matrix-dim/70 mt-0.5">{it.sub}</div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
