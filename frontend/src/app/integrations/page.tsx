"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { McpServerStatus } from "@/lib/types";
import {
  Github,
  BookOpen,
  FolderKanban,
  MessageSquare,
  Hash,
  Send,
  Plug
} from "lucide-react";

/** Icon + label per known server name. Unknown servers still render — the
 *  backend's SUPPORTED_SERVERS list is the source of truth, not this map. */
const PRESENTATION: Record<string, { label: string; icon: React.ReactNode }> = {
  github: { label: "GitHub", icon: <Github className="w-5 h-5" /> },
  notion: { label: "Notion", icon: <BookOpen className="w-5 h-5" /> },
  google_workspace: {
    label: "Google Workspace",
    icon: <FolderKanban className="w-5 h-5" />
  },
  slack: { label: "Slack", icon: <MessageSquare className="w-5 h-5" /> },
  telegram: { label: "Telegram", icon: <Send className="w-5 h-5" /> },
  hashnode: { label: "Hashnode", icon: <Hash className="w-5 h-5" /> }
};

const STATUS_VARIANT: Record<
  McpServerStatus["status"],
  "success" | "warning" | "error"
> = {
  healthy: "success",
  degraded: "warning",
  down: "error"
};

export default function IntegrationsPage() {
  const [servers, setServers] = useState<McpServerStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [probing, setProbing] = useState<string | null>(null);
  const [probeResult, setProbeResult] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      setServers(await api.mcpDoctor());
      setError(null);
    } catch (e) {
      setServers([]);
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  /** A real round-trip to the server's tools/list, not a setTimeout. */
  const probe = async (name: string) => {
    setProbing(name);
    try {
      const result = await api.mcpProbe(name);
      setProbeResult((prev) => ({
        ...prev,
        [name]: result?.ok
          ? `OK · ${result?.tools_count ?? result?.tools?.length ?? 0} tools`
          : `FAILED · ${String(result?.error ?? "no detail")}`.slice(0, 90)
      }));
    } catch (e) {
      setProbeResult((prev) => ({
        ...prev,
        [name]: `FAILED · ${(e as Error).message}`.slice(0, 90)
      }));
    } finally {
      setProbing(null);
      load();
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-wider glow-text">
          ⟨ INTEGRATIONS · MCP SERVERS ⟩
        </h1>
        <p className="text-xs text-matrix-dim mt-1 tracking-widest">
          MODEL CONTEXT PROTOCOL · LIVE FROM /api/mcp/doctor
        </p>
      </div>

      {error && (
        <Card>
          <CardContent className="py-6 text-xs text-danger">
            MCP DOCTOR UNAVAILABLE · {error}
          </CardContent>
        </Card>
      )}

      {!error && servers !== null && servers.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-xs text-matrix-dim">
            NO MCP SERVERS CONFIGURED
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {(servers ?? []).map((s) => {
          const p = PRESENTATION[s.name] ?? {
            label: s.name,
            icon: <Plug className="w-5 h-5" />
          };
          return (
            <Card key={s.name}>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded border border-matrix/30 bg-matrix/5 flex items-center justify-center">
                      {p.icon}
                    </div>
                    <div>
                      <div className="font-bold tracking-wider">{p.label}</div>
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
                    <span className="text-matrix-dim tracking-wider">TOOLS</span>
                    <span>{s.toolsAvailable} REGISTERED</span>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span className="text-matrix-dim tracking-wider shrink-0">
                      LAST PROBE
                    </span>
                    <span className="truncate" suppressHydrationWarning>
                      {s.lastProbe ? s.lastProbe.slice(0, 19).replace("T", " ") : "NEVER"}
                    </span>
                  </div>
                  {probeResult[s.name] && (
                    <div
                      className={`pt-1.5 border-t border-matrix/10 ${
                        probeResult[s.name].startsWith("OK")
                          ? "text-success"
                          : "text-danger"
                      }`}
                    >
                      {probeResult[s.name]}
                    </div>
                  )}
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
          );
        })}
      </div>
    </div>
  );
}
