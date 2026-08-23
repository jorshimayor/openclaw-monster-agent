"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { McpServerStatus } from "@/lib/types";
import { Github, BookOpen, FolderKanban, MessageSquare, Hash } from "lucide-react";
import { useIsHydrated } from "@/lib/hydration";

interface IntegrationRow extends McpServerStatus {
  icon: React.ReactNode;
  displayName: string;
}

const INITIAL: IntegrationRow[] = [
  {
    name: "github-mcp",
    displayName: "GitHub",
    icon: <Github className="w-5 h-5" />,
    status: "healthy",
    toolsAvailable: 14,
    lastProbe: undefined
  },
  {
    name: "notion-mcp",
    displayName: "Notion",
    icon: <BookOpen className="w-5 h-5" />,
    status: "healthy",
    toolsAvailable: 9,
    lastProbe: undefined
  },
  {
    name: "google-workspace-mcp",
    displayName: "Google Workspace",
    icon: <FolderKanban className="w-5 h-5" />,
    status: "degraded",
    toolsAvailable: 11,
    lastProbe: undefined
  },
  {
    name: "slack-mcp",
    displayName: "Slack",
    icon: <MessageSquare className="w-5 h-5" />,
    status: "healthy",
    toolsAvailable: 7,
    lastProbe: undefined
  },
  {
    name: "hashnode-mcp",
    displayName: "Hashnode",
    icon: <Hash className="w-5 h-5" />,
    status: "down",
    toolsAvailable: 4,
    lastProbe: undefined
  }
];

const STATUS_VARIANT: Record<
  McpServerStatus["status"],
  "success" | "warning" | "error"
> = {
  healthy: "success",
  degraded: "warning",
  down: "error"
};

export default function IntegrationsPage() {
  const hydrated = useIsHydrated();
  const [servers, setServers] = useState<IntegrationRow[]>(INITIAL);
  const [probing, setProbing] = useState<string | null>(null);

  const probe = async (name: string) => {
    setProbing(name);
    await new Promise((r) => setTimeout(r, 900));
    setServers((prev) =>
      prev.map((s) =>
        s.name === name
          ? { ...s, lastProbe: new Date().toISOString() }
          : s
      )
    );
    setProbing(null);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-wider glow-text">
          ⟨ INTEGRATIONS · MCP SERVERS ⟩
        </h1>
        <p className="text-xs text-matrix-dim mt-1 tracking-widest">
          MODEL CONTEXT PROTOCOL · EXTERNAL TOOL CONNECTIVITY
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {servers.map((s) => (
          <Card key={s.name}>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-11 h-11 rounded border border-matrix/30 bg-matrix/5 flex items-center justify-center shadow-matrix-glow/30">
                    {s.icon}
                  </div>
                  <div>
                    <div className="font-bold tracking-wider">{s.displayName}</div>
                    <div className="text-[10px] text-matrix-dim tracking-widest mt-0.5">
                      {s.name}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`w-2.5 h-2.5 rounded-full ${
                      s.status === "healthy"
                        ? "bg-matrix animate-pulse"
                        : s.status === "degraded"
                        ? "bg-warning animate-pulse"
                        : "bg-danger"
                    }`}
                  />
                  <Badge variant={STATUS_VARIANT[s.status]}>
                    {s.status.toUpperCase()}
                  </Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <div className="bg-bg/50 border border-matrix/20 rounded p-3 space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-matrix-dim tracking-wider">SERVER</span>
                  <span className="font-mono">{s.name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-matrix-dim tracking-wider">TOOLS</span>
                  <span>{s.toolsAvailable} AVAILABLE</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-matrix-dim tracking-wider">LAST PROBE</span>
                  <span>
                    {s.lastProbe
                      ? hydrated
                        ? new Date(s.lastProbe).toISOString().slice(11, 19) + " UTC"
                        : "—"
                      : "N/A"}
                  </span>
                </div>
              </div>
              <Button
                variant="matrix"
                size="sm"
                className="w-full"
                disabled={probing === s.name}
                onClick={() => probe(s.name)}
              >
                {probing === s.name ? "PROBING..." : "◉ PROBE SERVER"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
