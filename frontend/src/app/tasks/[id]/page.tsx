"use client";

export const runtime = "edge";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PipelineRail } from "@/components/pipeline/PipelineRail";
import { LogPanel } from "@/components/console/LogPanel";
import { api } from "@/lib/api";
import type { AgentResult, PipelineStep, Task, TaskStatus } from "@/lib/types";
import type { LogEntry, PipelineEvent } from "@/lib/events";
import { formatDate } from "@/lib/utils";
import type { ParsedEvent, ReconnectInterval } from "eventsource-parser";

const STATUS_VARIANT: Record<TaskStatus, "default" | "success" | "warning" | "error"> = {
  queued: "default",
  running: "warning",
  reworking: "warning",
  completed: "success",
  failed: "error"
};

const STEP_MAP: Record<string, PipelineStep> = {
  COMPLEXITY_CHECK: "complexity",
  PATTERN_MATCH: "pattern",
  EXPERIENCE_RECALL: "experience",
  TEAM_ASSEMBLY: "team",
  PROMPT_INJECTION: "prompt",
  PARALLEL_EXECUTION: "execute",
  VERIFIER: "verify",
  QUALITY_GATE: "quality_gate",
  FIX_REVALIDATE: "fix",
  SYNTHESIZER: "synthesize",
  POST_TASK_REFLECTION: "reflect"
};

function shadeForMsg(msg: string, type?: string): 0 | 1 | 2 | 3 | 4 {
  if (type === "error") return 4;
  const low = msg.toLowerCase();
  if (low.includes("complete") || low.includes("ok") || low.includes("pass")) return 0;
  if (low.includes("invoke") || low.includes("start")) return 1;
  if (low.includes("warn") || low.includes("retry")) return 2;
  if (low.includes("init") || low.includes("load") || low.includes("await")) return 3;
  return 0;
}

export default function TaskDetailPage() {
  const params = useParams();
  const id = params?.id as string;

  const [task, setTask] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState<PipelineStep | undefined>(undefined);
  const [outputs, setOutputs] = useState<AgentResult[]>([]);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [finalReport, setFinalReport] = useState<string | null>(null);
  const [events, setEvents] = useState<PipelineEvent[]>([]);

  useEffect(() => {
    if (!id) return;

    let cancelled = false;

    const pushLog = (entry: LogEntry) => {
      setLogEntries((prev) => [...prev, entry]);
    };

    const appendEvent = (ev: PipelineEvent) => {
      setEvents((prev) => [...prev, ev]);
    };

    const onEvent = (event: ParsedEvent | ReconnectInterval) => {
      if (cancelled) return;
      if (event.type === "reconnect-interval") return;
      if (event.type !== "event") return;
      const rawData = event.data ?? "{}";
      let parsed: any = {};
      try {
        parsed = JSON.parse(rawData);
      } catch {
        parsed = { message: String(rawData) };
      }
      const type: PipelineEvent["type"] =
        (parsed.type as PipelineEvent["type"]) ||
        (event.event === "error" ? "error" : "info");
      const timestamp = parsed.timestamp || new Date().toISOString();
      const stepRaw = parsed.step || parsed.currentStep;
      const step = stepRaw
        ? STEP_MAP[String(stepRaw).toUpperCase()] ||
          (String(stepRaw).toLowerCase() as PipelineStep)
        : undefined;
      const message = parsed.message || parsed.msg || event.event || "";

      if (type === "step_complete" || type === "step_start") {
        if (step) setCurrentStep(step);
        pushLog({
          time: timestamp.slice(11, 19),
          step: type === "step_complete" ? "STEP.DONE" : "STEP.BGN",
          agent: "ORCH",
          msg: `${type} ${step || message || "unknown"}`,
          shade: type === "step_complete" ? 0 : 1
        });
      } else if (type === "agent_output") {
        const out = parsed.output as AgentResult | undefined;
        if (out) {
          const head = (v: unknown) =>
            typeof v === "string"
              ? v.slice(0, 40)
              : typeof v === "object" && v !== null
                ? JSON.stringify(v).slice(0, 40)
                : String(v ?? "").slice(0, 40);
          const len = (v: unknown) =>
            typeof v === "string"
              ? v.length
              : typeof v === "object" && v !== null
                ? JSON.stringify(v).length
                : String(v ?? "").length;
          setOutputs((prev) => {
            const exists = prev.some(
              (p) =>
                p.agent_role === out.agent_role &&
                head(p.output) === head(out.output)
            );
            if (exists) return prev;
            return [...prev, out];
          });
          pushLog({
            time: timestamp.slice(11, 19),
            step: "OUTPUT",
            agent: String(out.agent_role).slice(0, 12).toUpperCase(),
            msg: `agent_output confidence=${(out.confidence * 100).toFixed(0)}% chars=${len(out.output)}`,
            shade: 0
          });
        }
      } else if (type === "pipeline_complete") {
        setFinalReport(parsed.finalReport || parsed.final_report || message || "Pipeline complete.");
        pushLog({
          time: timestamp.slice(11, 19),
          step: "DONE",
          agent: "SYSTEM",
          msg: `pipeline_complete outputs=${outputs.length}`,
          shade: 0
        });
      } else if (type === "error") {
        const errMsg = parsed.error || message || "Unknown streaming error";
        setError(errMsg);
        pushLog({
          time: timestamp.slice(11, 19),
          step: "ERR",
          agent: "SYSTEM",
          msg: `error: ${errMsg}`,
          shade: 4
        });
      } else {
        pushLog({
          time: timestamp.slice(11, 19),
          step: "INFO",
          agent: parsed.agent ? String(parsed.agent).slice(0, 12).toUpperCase() : "SYSTEM",
          msg: message || "(no message)",
          shade: shadeForMsg(message || "", type)
        });
      }

      appendEvent({
        type,
        step,
        timestamp,
        message,
        output: parsed.output,
        finalReport: parsed.finalReport || parsed.final_report,
        error: parsed.error
      });
    };

    api.getTask(id).then(setTask).catch((e) => setError(e.message));

    let cleanup: (() => void) | null = null;
    try {
      cleanup = api.streamTask(id, onEvent);
    } catch (streamErr) {
      console.error("[streamTask init]", streamErr);
    }

    const iv = setInterval(() => {
      if (cancelled) return;
      api.getTask(id)
        .then((t) => {
          setTask(t);
          if (t.currentStep) setCurrentStep(t.currentStep);
          if (t.outputs && t.outputs.length > 0) {
            setOutputs((prev) => {
              if (prev.length >= t.outputs!.length) return prev;
              return t.outputs!;
            });
          }
          if ((t.status === "completed" || t.status === "failed") && !finalReport) {
            setFinalReport(t.status === "completed" ? "Task completed successfully." : "Task failed.");
          }
        })
        .catch();
    }, 3000);

    pushLog({
      time: new Date().toISOString().slice(11, 19),
      step: "STREAM",
      agent: "SYSTEM",
      msg: `connecting stream for task ${id}`,
      shade: 3
    });

    return () => {
      cancelled = true;
      clearInterval(iv);
      if (cleanup) cleanup();
    };
  }, [id]);

  const mergedOutputs = useMemo<AgentResult[]>(() => {
    const list = outputs;
    if (task?.outputs && task.outputs.length > list.length) {
      return task.outputs;
    }
    return list;
  }, [outputs, task?.outputs]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link
          href="/tasks"
          className="text-xs text-matrix-dim hover:text-matrix tracking-widest"
        >
          ← BACK TO TASKS
        </Link>
      </div>

      {error && (
        <Card>
          <CardContent className="pt-6 text-red-400">
            ERROR: {error}
          </CardContent>
        </Card>
      )}

      {task && (
        <>
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="text-xs text-matrix-dim tracking-widest mb-2">
                    TASK ID
                  </div>
                  <div className="text-lg font-mono glow-text tracking-wider">
                    {task.id}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <Badge variant={STATUS_VARIANT[task.status]}>
                    {task.status.toUpperCase()}
                  </Badge>
                  <div className="text-[10px] text-matrix-dim tracking-widest">
                    CREATED: {formatDate(task.createdAt)}
                  </div>
                  {finalReport && (
                    <Badge variant="success" className="mt-1">FINALIZED</Badge>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-xs text-matrix-dim tracking-widest mb-2">
                DESCRIPTION
              </div>
              <div className="text-sm leading-relaxed bg-black/40 border border-matrix/20 rounded p-4">
                {task.description}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm tracking-widest">
                11-STEP PIPELINE PROGRESS
              </CardTitle>
            </CardHeader>
            <CardContent>
              <PipelineRail currentStep={currentStep} events={events} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm tracking-widest">
                EXECUTION LOG
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              <LogPanel entries={logEntries} />
            </CardContent>
          </Card>

          {finalReport && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm tracking-widest">FINAL REPORT</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="text-xs text-matrix/90 whitespace-pre-wrap leading-relaxed bg-black/40 border border-matrix/20 rounded p-4">
                  {finalReport}
                </pre>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-sm tracking-widest">
                AGENT OUTPUTS · {mergedOutputs.length}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {mergedOutputs.length === 0 ? (
                <div className="text-xs text-matrix-dim text-center py-8">
                  NO OUTPUTS YET · PIPELINE IN PROGRESS
                </div>
              ) : (
                mergedOutputs.map((o, i) => (
                  <div
                    key={i}
                    className="border border-matrix/30 rounded p-4 bg-black/40"
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className="text-sm font-bold tracking-wider">
                        {String(o.agent_role).toUpperCase().replace(/_/g, " ")}
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="text-xs text-matrix-dim">
                          CONFIDENCE: {(o.confidence * 100).toFixed(1)}%
                        </div>
                        <div className="w-24 h-1.5 bg-matrix/10 rounded overflow-hidden">
                          <div
                            className="h-full bg-matrix shadow-matrix-glow"
                            style={{ width: `${Math.min(100, o.confidence * 100)}%` }}
                          />
                        </div>
                      </div>
                    </div>
                    <pre className="text-xs text-matrix/90 whitespace-pre-wrap leading-relaxed max-h-[420px] overflow-auto">
                      {typeof o.output === "string"
                        ? o.output
                        : typeof o.output === "object" && o.output !== null
                          ? JSON.stringify(o.output, null, 2)
                          : String(o.output ?? "")}
                    </pre>
                    {o.errors && o.errors.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-matrix/20 text-red-400 text-xs">
                        ERRORS: {o.errors.join(" · ")}
                      </div>
                    )}
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
