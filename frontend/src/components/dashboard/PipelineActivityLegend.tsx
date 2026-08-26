"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { PipelineStep, Task } from "@/lib/types";
import { cn } from "@/lib/utils";

const STEPS: { n: number; key: PipelineStep; label: string }[] = [
  { n: 1, key: "complexity", label: "COMPLEXITY" },
  { n: 2, key: "pattern", label: "PATTERN" },
  { n: 3, key: "experience", label: "EXPERIENCE" },
  { n: 4, key: "team", label: "TEAM" },
  { n: 5, key: "prompt", label: "PROMPT" },
  { n: 6, key: "execute", label: "EXECUTE" },
  { n: 7, key: "verify", label: "VERIFY" },
  { n: 8, key: "quality_gate", label: "GATE" },
  { n: 9, key: "fix", label: "FIX" },
  { n: 10, key: "synthesize", label: "SYNTHESIZE" },
  { n: 11, key: "reflect", label: "REFLECT" }
];

/**
 * Occupancy of the 11-step pipeline right now: which steps have live tasks
 * sitting in them. It used to say "ALL NODES STANDBY" unconditionally,
 * whether the pipeline was empty or running eight tasks.
 */
export default function PipelineActivityLegend() {
  const [tasks, setTasks] = useState<Task[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api
        .listTasks()
        .then((rows) => !cancelled && setTasks(rows))
        .catch(() => !cancelled && setTasks([]));
    load();
    const id = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const live = (tasks ?? []).filter(
    (t) => t.status === "running" || t.status === "reworking"
  );
  const occupancy = new Map<string, number>();
  for (const t of live) {
    if (t.currentStep) {
      occupancy.set(t.currentStep, (occupancy.get(t.currentStep) ?? 0) + 1);
    }
  }

  const headline =
    tasks === null
      ? "LOADING…"
      : live.length === 0
      ? "ALL NODES IDLE"
      : `${live.length} TASK${live.length === 1 ? "" : "S"} IN FLIGHT`;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm tracking-widest flex items-center justify-between">
          <span>11-STEP PIPELINE</span>
          <span
            className={cn(
              "text-[10px] font-normal",
              live.length > 0 ? "text-matrix glow-text" : "text-matrix-dim"
            )}
          >
            {headline}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-4">
          {STEPS.map((s, idx) => {
            const count = occupancy.get(s.key) ?? 0;
            const active = count > 0;
            return (
              <div key={s.key} className="flex items-center">
                <div className="flex flex-col items-center">
                  <div className="relative">
                    <div
                      className={cn(
                        "w-9 h-9 rounded-full border flex items-center justify-center text-xs font-mono transition-all",
                        active
                          ? "border-matrix bg-matrix/15 text-matrix shadow-matrix-glow animate-pulse-matrix"
                          : "border-matrix/20 bg-bg text-matrix-dim"
                      )}
                      title={
                        active
                          ? `${count} task(s) at step ${s.n}: ${s.label}`
                          : `Step ${s.n}: ${s.label} — idle`
                      }
                    >
                      {s.n}
                    </div>
                    {count > 1 && (
                      <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full text-[9px] font-mono flex items-center justify-center bg-matrix text-bg border border-matrix-dim">
                        {count}
                      </span>
                    )}
                  </div>
                  <div
                    className={cn(
                      "text-[9px] tracking-widest mt-1.5 max-w-[72px] text-center",
                      active ? "text-matrix" : "text-matrix-dim/80"
                    )}
                  >
                    {s.label}
                  </div>
                </div>
                {idx < STEPS.length - 1 && (
                  <div className="w-3 h-px bg-matrix/20 mx-1 mb-5" />
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
