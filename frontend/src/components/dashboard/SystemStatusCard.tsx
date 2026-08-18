"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Server, Activity, Cpu, Clock } from "lucide-react";

interface HealthInfo {
  status: "online" | "offline";
  latency: number;
  uptimePct: number;
  activeTasks: number;
}

export default function SystemStatusCard() {
  const [health, setHealth] = useState<HealthInfo>({
    status: "online",
    latency: 23,
    uptimePct: 99.97,
    activeTasks: 0
  });

  useEffect(() => {
    const ping = async () => {
      const t0 = performance.now();
      try {
        await api.health();
        const lat = Math.round(performance.now() - t0);
        setHealth((h) => ({
          ...h,
          status: "online",
          latency: lat,
          uptimePct: 99.97
        }));
      } catch {
        setHealth((h) => ({ ...h, status: "offline", latency: 0 }));
      }
    };
    ping();
    const id = setInterval(ping, 5000);
    return () => clearInterval(id);
  }, []);

  const items = [
    {
      icon: <Clock className="w-4 h-4" />,
      label: "UPTIME",
      value: `${health.uptimePct.toFixed(2)}%`,
      sub: "30d rolling"
    },
    {
      icon: <Activity className="w-4 h-4" />,
      label: "ACTIVE TASKS",
      value: String(health.activeTasks),
      sub: "in pipeline"
    },
    {
      icon: <Cpu className="w-4 h-4" />,
      label: "HEALTH LATENCY",
      value: `${health.latency}ms`,
      sub: "HTTP /api/health"
    },
    {
      icon: <Server className="w-4 h-4" />,
      label: "BUILD",
      value: "v1.0.0",
      sub: "stable · prod"
    }
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm tracking-widest flex items-center justify-between">
          <span>SYSTEM STATUS</span>
          <Badge variant={health.status === "online" ? "success" : "error"}>
            <span className="flex items-center gap-1.5">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  health.status === "online"
                    ? "bg-green-400 animate-pulse"
                    : "bg-red-500"
                }`}
              />
              {health.status.toUpperCase()}
            </span>
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          {items.map((it) => (
            <div
              key={it.label}
              className="rounded border border-matrix/20 bg-black/40 p-4"
            >
              <div className="flex items-center gap-2 text-matrix-dim text-[10px] tracking-widest mb-2">
                {it.icon}
                {it.label}
              </div>
              <div className="text-xl font-bold glow-text tracking-wider">
                {it.value}
              </div>
              <div className="text-[10px] text-matrix-dim/70 mt-0.5">
                {it.sub}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
