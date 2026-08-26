"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, type AgentSummary } from "@/lib/api";
import { agentPresentation } from "@/lib/types";

export default function AgentRosterCard() {
  const [agents, setAgents] = useState<AgentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api
        .listAgents()
        .then((rows) => {
          if (cancelled) return;
          setAgents(rows);
          setError(null);
        })
        .catch((e: Error) => {
          if (cancelled) return;
          setAgents([]);
          setError(e.message);
        });
    load();
    const id = setInterval(load, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const ready = (agents ?? []).filter((a) => a.status === "READY").length;
  const total = agents?.length ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm tracking-widest flex items-center justify-between">
          <span>AGENT ROSTER</span>
          <span className="text-[10px] text-matrix-dim font-normal">
            {agents === null ? "LOADING…" : `${ready} / ${total} READY`}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="py-3 px-2">
        {error && (
          <div className="px-4 py-6 text-xs text-danger">
            ROSTER UNAVAILABLE · {error}
          </div>
        )}
        {!error && agents !== null && agents.length === 0 && (
          <div className="px-4 py-6 text-xs text-matrix-dim">
            NO AGENTS REPORTED BY THE BACKEND
          </div>
        )}
        <div className="divide-y divide-bg-border/60">
          {(agents ?? []).map((a) => {
            const p = agentPresentation(a.role);
            const isReady = a.status === "READY";
            return (
              <div
                key={a.role}
                className="flex items-center justify-between px-4 py-2.5 hover:bg-matrix/5 transition-colors rounded"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 shrink-0 rounded border border-matrix/20 bg-matrix/5 flex items-center justify-center text-base">
                    {p.emoji}
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">
                      {p.displayName}
                    </div>
                    <div
                      className="text-[10px] text-matrix-dim tracking-widest truncate"
                      title={a.model_profile}
                    >
                      {a.model_profile} · {a.tool_allowlist.length} TOOLS
                    </div>
                  </div>
                </div>
                <Badge variant={isReady ? "success" : "warning"} className="gap-1.5 shrink-0">
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      isReady ? "bg-success animate-pulse" : "bg-warning"
                    }`}
                  />
                  {a.status}
                </Badge>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
