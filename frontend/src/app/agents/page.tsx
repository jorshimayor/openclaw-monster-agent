"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription
} from "@/components/ui/dialog";
import { agentPresentation, type AgentResult } from "@/lib/types";
import type { AgentDetail, AgentSummary } from "@/lib/api";
import { api } from "@/lib/api";
import { Cpu, Zap, Shield, Lightbulb, BookOpen, GraduationCap, Trophy, Network } from "lucide-react";

/** Keyed by the backend's AgentRole values. Unknown roles fall back to Cpu. */
const ICONS: Record<string, typeof Cpu> = {
  ORCHESTRATOR: Network,
  CONTENT_WEB2: Zap,
  CONTENT_WEB3: Shield,
  SECURITY: Shield,
  KNOWLEDGE: Lightbulb,
  EDITOR: BookOpen,
  STUDY: GraduationCap,
  FOOTBALL: Trophy,
  PERSONAL_ASSISTANT: Cpu
};

const iconFor = (role: string) => ICONS[role] ?? Cpu;

const DEFAULT_PROMPTS: Record<string, string> = {
  ORCHESTRATOR:
    "Design a 7-step plan for building a Web3 DeFi dApp dashboard that displays real-time yield farming APYs across 5 chains.",
  CONTENT_WEB2:
    "Write a 3-paragraph technical blog intro about realtime collaborative editors using CRDTs.",
  CONTENT_WEB3:
    "Draft an audit summary for a new Uniswap V4 hook that implements TWAMM orders.",
  SECURITY:
    "Audit the following Solidity snippet for reentrancy, integer overflow, and access control issues:\n\nfunction withdraw(uint256 a) external {\n  require(balances[msg.sender] >= a);\n  (bool ok,) = msg.sender.call{value: a}('');\n  require(ok);\n  balances[msg.sender] -= a;\n}",
  KNOWLEDGE:
    "Extract reusable strategies, pitfalls, and entities from the following text:\n\nWhen auditing DeFi lending protocols, always verify oracle freshness using latestRoundData. Relying on timestamp without checking updatedAt caused the 2023 Venus exploit. Re-validate interest rate models against extreme market conditions.",
  EDITOR:
    "Review this technical article outline and suggest 3 concrete improvements for clarity, narrative flow, and developer usefulness.",
  STUDY:
    "Design a 4-week study plan for learning ZK circuits starting from zero: include circuits, arithmetic, Circom, and a final project building a private voting proof.",
  FOOTBALL:
    "Analyze a 4-3-3 vs 4-2-3-1 tactical matchup: identify strengths, weaknesses, key matchups, and recommend 3 in-game adjustments for a team trailing 1-0 in the 60th minute."
};

interface InvokeState {
  role: string;
  result: AgentResult | null;
  invoking: boolean;
  error: string | null;
}

export default function AgentsPage() {
  // The roster itself comes from the backend; this page no longer asserts
  // which agents exist or that all of them are online.
  const [agents, setAgents] = useState<AgentSummary[] | null>(null);
  const [rosterError, setRosterError] = useState<string | null>(null);
  const [health, setHealth] = useState<Record<string, AgentDetail | null>>({});
  const [healthLoading, setHealthLoading] = useState(true);

  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [modalPrompt, setModalPrompt] = useState("");
  const [modalOpen, setModalOpen] = useState(false);

  const [invokeState, setInvokeState] = useState<InvokeState | null>(null);

  useEffect(() => {
    let cancelled = false;
    setHealthLoading(true);
    (async () => {
      let roster: AgentSummary[] = [];
      try {
        roster = await api.listAgents();
        if (!cancelled) {
          setAgents(roster);
          setRosterError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setAgents([]);
          setRosterError((e as Error).message);
          setHealthLoading(false);
        }
        return;
      }
      const details = await Promise.all(
        roster.map((a) => api.getAgent(a.role).catch(() => null))
      );
      if (cancelled) return;
      setHealth(Object.fromEntries(roster.map((a, i) => [a.role, details[i]])));
      setHealthLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const openInvokeModal = useCallback((role: string) => {
    setSelectedRole(role);
    setModalPrompt(DEFAULT_PROMPTS[role] ?? "");
    setInvokeState({ role, result: null, invoking: false, error: null });
    setModalOpen(true);
  }, []);

  const submitInvoke = useCallback(async () => {
    if (!selectedRole || !modalPrompt.trim()) return;
    setInvokeState((prev) =>
      prev && prev.role === selectedRole
        ? { ...prev, invoking: true, error: null, result: null }
        : prev
    );
    try {
      const res = await api.invokeAgent(selectedRole, { prompt: modalPrompt.trim() });
      setInvokeState((prev) =>
        prev && prev.role === selectedRole
          ? { ...prev, invoking: false, result: res, error: null }
          : prev
      );
    } catch (e: any) {
      setInvokeState((prev) =>
        prev && prev.role === selectedRole
          ? {
              ...prev,
              invoking: false,
              result: null,
              error: e?.message || "Agent invocation failed"
            }
          : prev
      );
    }
  }, [selectedRole, modalPrompt]);

  const confidencePct = (c: number): number => {
    const n = Number(c);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(100, Math.round(n * 100)));
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-wider glow-text">
          ⟨ AGENT CONTROL PANEL ⟩
        </h1>
        <p className="text-xs text-matrix-dim mt-1 tracking-widest">
          {agents === null
            ? "LOADING ROSTER…"
            : `${agents.length} AGENT${agents.length === 1 ? "" : "S"} · LIVE FROM /api/agents · ONE-CLICK INVOKE`}
        </p>
      </div>

      {rosterError && (
        <Card>
          <CardContent className="py-6 text-xs text-danger">
            AGENT ROSTER UNAVAILABLE · {rosterError}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {(agents ?? []).map((a) => {
          const Icon = iconFor(a.role);
          const p = agentPresentation(a.role);
          const h = health[a.role];
          const healthy = h?.healthy ?? false;
          return (
            <Card key={a.role} className="group hover:border-matrix/40 transition-colors">
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-lg bg-matrix/10 border border-matrix/20 flex items-center justify-center text-matrix shrink-0 group-hover:shadow-matrix-glow transition-shadow">
                      <Icon className="w-5 h-5" />
                    </div>
                    <div className="min-w-0">
                      <CardTitle className="text-sm tracking-wider">
                        {p.displayName}
                      </CardTitle>
                      <CardDescription className="text-[10px] tracking-widest mt-1">
                        {a.role} · {a.model_profile}
                      </CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge
                      variant={healthy ? "success" : "warning"}
                      className="text-[9px] font-mono tracking-wider"
                    >
                      {healthLoading
                        ? "…"
                        : healthy
                        ? "ONLINE"
                        : "UNKNOWN"}
                    </Badge>
                    {h?.last_run && (
                      <span
                        className="text-[9px] text-matrix-dim tracking-widest font-mono"
                        title={`Last run: ${h.last_run}`}
                      >
                        LR
                      </span>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-xs text-matrix/80 leading-relaxed min-h-[3rem]">
                  {a.description}
                </p>
                <div className="flex flex-wrap gap-1.5 mb-3">
                  {p.tags.slice(0, 4).map((t) => (
                    <span
                      key={t}
                      className="text-[9px] px-2 py-0.5 rounded bg-matrix/5 border border-matrix/10 text-matrix-dim tracking-widest font-mono"
                    >
                      {t}
                    </span>
                  ))}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => openInvokeModal(a.role)}
                  className="w-full text-xs tracking-wider group-hover:shadow-matrix-glow"
                >
                  <Zap className="w-3.5 h-3.5 mr-2" />
                  INVOKE TEST
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Dialog
        open={modalOpen}
        onOpenChange={(open) => {
          if (!open) {
            setModalOpen(false);
            setSelectedRole(null);
            setInvokeState(null);
          } else {
            setModalOpen(true);
          }
        }}
      >
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="tracking-wider glow-text flex items-center gap-2">
              {selectedRole && (
                <>
                  {(() => {
                    const Icon = iconFor(selectedRole);
                    return <Icon className="w-5 h-5 text-matrix" />;
                  })()}
                  INVOKE{" "}
                  <span className="text-matrix-dim text-xs tracking-widest font-mono ml-1">
                    {agentPresentation(selectedRole).displayName}
                  </span>
                </>
              )}
            </DialogTitle>
            <DialogDescription className="text-[10px] tracking-widest">
              SUBMIT PROMPT · AGENT RETURNS STRUCTURED RESULT
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto space-y-4 pr-1">
            <div className="space-y-2">
              <label className="text-[10px] tracking-widest text-matrix-dim">
                PROMPT / CONTEXT
              </label>
              <textarea
                value={modalPrompt}
                onChange={(e) => setModalPrompt(e.target.value)}
                disabled={invokeState?.invoking}
                rows={8}
                className="w-full bg-bg/50 border border-matrix/30 rounded p-3 text-sm focus:border-matrix focus:outline-none focus:shadow-matrix-glow placeholder:text-matrix-dim/50 font-mono resize-y disabled:opacity-60"
                placeholder="Enter prompt or context object to pass to agent.invoke(context)"
              />
            </div>

            {invokeState?.error && (
              <div className="border border-danger/30 bg-danger/10 rounded p-3 text-xs text-danger tracking-wider">
                ⚠ {invokeState.error}
              </div>
            )}

            {invokeState?.result && (
              <div className="space-y-3 border-t border-matrix/15 pt-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Badge variant="success" className="text-[10px] tracking-wider font-mono">
                      STATUS: {String(invokeState.result.status).toUpperCase()}
                    </Badge>
                    <Badge variant="default" className="text-[10px] tracking-wider font-mono">
                      LATENCY {String(invokeState.result.metadata?.latency_ms ?? "?")} MS
                    </Badge>
                  </div>
                  <div className="flex-1 min-w-[180px] max-w-[280px]">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[10px] tracking-widest text-matrix-dim font-mono">
                        CONFIDENCE
                      </span>
                      <span className="text-[11px] font-mono text-matrix tracking-wider">
                        {confidencePct(invokeState.result.confidence)}%
                      </span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-matrix/10 border border-matrix/20 overflow-hidden">
                      <div
                        className={`h-full transition-all duration-500 ${
                          confidencePct(invokeState.result.confidence) >= 70
                            ? "bg-matrix shadow-matrix-glow"
                            : confidencePct(invokeState.result.confidence) >= 40
                            ? "bg-matrix/70"
                            : "bg-danger/80"
                        }`}
                        style={{
                          width: `${confidencePct(invokeState.result.confidence)}%`
                        }}
                      />
                    </div>
                  </div>
                </div>

                {invokeState.result.summary && (
                  <div className="bg-matrix/5 border border-matrix/20 rounded p-3">
                    <div className="text-[10px] tracking-widest text-matrix-dim mb-1.5 font-mono">
                      SUMMARY
                    </div>
                    <p className="text-xs text-matrix/90 leading-relaxed whitespace-pre-wrap">
                      {invokeState.result.summary}
                    </p>
                  </div>
                )}

                <div className="bg-bg/50 border border-matrix/20 rounded">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-matrix/10">
                    <div className="text-[10px] tracking-widest text-matrix-dim font-mono">
                      AGENT OUTPUT
                    </div>
                    <div className="flex items-center gap-1.5 text-[9px] tracking-widest text-matrix-dim font-mono">
                      {(invokeState.result.actions?.length ?? 0) > 0 && (
                        <Badge variant="default" className="text-[9px] tracking-widest">
                          {invokeState.result.actions?.length} ACTION
                          {(invokeState.result.actions?.length ?? 0) === 1 ? "" : "S"}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="p-3 max-h-[260px] overflow-y-auto">
                    <pre className="text-[11px] leading-relaxed font-mono text-matrix/90 whitespace-pre-wrap break-words">
                      {typeof invokeState.result.output === "string"
                        ? invokeState.result.output
                        : JSON.stringify(invokeState.result.output, null, 2)}
                    </pre>
                  </div>
                </div>

                {invokeState.result.metadata?.tool_calls &&
                  invokeState.result.metadata.tool_calls.length > 0 && (
                    <div className="bg-matrix/5 border border-matrix/15 rounded p-3 space-y-2">
                      <div className="text-[10px] tracking-widest text-matrix-dim font-mono">
                        MCP TOOL CALLS ATTEMPTED
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {invokeState.result.metadata.tool_calls.map((tc, i) => (
                          <Badge
                            key={i}
                            variant={tc.success ? "success" : "warning"}
                            className="text-[9px] font-mono tracking-wider"
                            title={
                              (typeof tc.error === "string" && tc.error) ||
                              (typeof tc.result === "string" && tc.result) ||
                              String(tc.name ?? "")
                            }
                          >
                            {tc.name}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
              </div>
            )}
          </div>

          <DialogFooter className="flex-col-reverse sm:flex-row gap-2 border-t border-matrix/15 pt-4 mt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setModalOpen(false)}
              disabled={invokeState?.invoking}
              className="w-full sm:w-auto text-xs tracking-wider"
            >
              CLOSE
            </Button>
            <Button
              size="sm"
              onClick={submitInvoke}
              disabled={invokeState?.invoking || !modalPrompt.trim()}
              className="w-full sm:w-auto text-xs tracking-wider"
            >
              <Zap
                className={`w-3.5 h-3.5 mr-2 ${invokeState?.invoking ? "animate-pulse" : ""}`}
              />
              {invokeState?.invoking ? "INVOKING…" : "RUN AGENT"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
