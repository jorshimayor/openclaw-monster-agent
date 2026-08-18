"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { useIsHydrated } from "@/lib/hydration";
import type { PipelineStep } from "@/lib/types";
import type { PipelineEvent } from "@/lib/events";

const STEPS: { key: PipelineStep; n: number; label: string }[] = [
  { key: "complexity", n: 1, label: "COMPLEXITY" },
  { key: "pattern", n: 2, label: "PATTERN" },
  { key: "experience", n: 3, label: "EXPERIENCE" },
  { key: "team", n: 4, label: "TEAM" },
  { key: "prompt", n: 5, label: "PROMPT" },
  { key: "execute", n: 6, label: "EXECUTE" },
  { key: "verify", n: 7, label: "VERIFY" },
  { key: "quality_gate", n: 8, label: "GATE" },
  { key: "fix", n: 9, label: "FIX" },
  { key: "synthesize", n: 10, label: "SYNTHESIZE" },
  { key: "reflect", n: 11, label: "REFLECT" }
];

interface PipelineRailProps {
  currentStep?: PipelineStep;
  events?: PipelineEvent[];
}

export function PipelineRail({ currentStep, events }: PipelineRailProps) {
  const hydrated = useIsHydrated();
  const currentIdx = currentStep
    ? STEPS.findIndex((s) => s.key === currentStep)
    : -1;

  const stepInfo = useMemo(() => {
    const info: Record<string, { count: number; last: string | null }> = {};
    if (events && events.length > 0) {
      for (const step of STEPS) info[step.key] = { count: 0, last: null };
      for (const ev of events) {
        if (!ev.step) continue;
        const slot = info[ev.step];
        if (!slot) continue;
        slot.count += 1;
        slot.last = ev.timestamp;
      }
    }
    return info;
  }, [events]);

  const formatTs = (iso: string | null) => {
    if (!iso) return "no events yet";
    if (!hydrated) return iso.slice(0, 19).replace("T", " ");
    try {
      const d = new Date(iso);
      return d.toLocaleString();
    } catch {
      return iso;
    }
  };

  return (
    <div className="overflow-x-auto pb-2">
      <div className="flex items-center min-w-max py-2 px-1">
        {STEPS.map((s, idx) => {
          const isDone = currentIdx >= 0 && idx < currentIdx;
          const isActive = idx === currentIdx;
          const isPending = currentIdx < 0 || idx > currentIdx;
          const meta = stepInfo[s.key];
          const eventCount = meta?.count ?? 0;
          const lastUpdate = meta?.last ?? null;
          const showBadge = eventCount > 0;

          return (
            <div key={s.key} className="flex items-center">
              <div
                className="flex flex-col items-center w-[84px] relative"
                title={`Step ${s.n}: ${s.label} · ${eventCount} event(s) · last: ${formatTs(lastUpdate)}`}
              >
                <div className="relative">
                  <div
                    className={cn(
                      "w-10 h-10 rounded-full flex items-center justify-center text-xs font-mono border-2 transition-all",
                      isDone &&
                        "bg-matrix text-bg border-matrix shadow-matrix-glow",
                      isActive &&
                        "bg-matrix/15 text-matrix border-matrix shadow-matrix-glow animate-pulse-matrix",
                      isPending &&
                        "bg-bg-panel text-matrix-dim/50 border-matrix/20"
                    )}
                  >
                    {isDone ? "✓" : s.n}
                  </div>
                  {showBadge && (
                    <span
                      className={cn(
                        "absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full text-[9px] font-mono flex items-center justify-center border",
                        isDone
                          ? "bg-matrix text-bg border-matrix-dim"
                          : isActive
                          ? "bg-matrix/80 text-bg border-matrix"
                          : "bg-matrix/20 text-matrix border-matrix/40"
                      )}
                      title={`${eventCount} pipeline event(s) · last updated ${formatTs(lastUpdate)}`}
                    >
                      {eventCount > 99 ? "99+" : eventCount}
                    </span>
                  )}
                </div>
                <div
                  className={cn(
                    "text-[9px] tracking-widest mt-2 text-center max-w-[80px] leading-tight",
                    isDone && "text-matrix",
                    isActive && "text-matrix glow-text",
                    isPending && "text-matrix-dim/60"
                  )}
                >
                  {s.label}
                </div>
                {lastUpdate && (
                  <div
                    className={cn(
                      "text-[8px] tracking-wider mt-1 max-w-[80px] leading-tight truncate",
                      isDone ? "text-matrix/70" : "text-matrix-dim/50"
                    )}
                    title={formatTs(lastUpdate)}
                    suppressHydrationWarning
                  >
                    {hydrated
                      ? new Date(lastUpdate).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit"
                        })
                      : lastUpdate.slice(11, 19)}
                  </div>
                )}
              </div>
              {idx < STEPS.length - 1 && (
                <div
                  className={cn(
                    "w-6 h-0.5 mb-6",
                    isDone ? "bg-matrix shadow-matrix-glow" : "bg-matrix/20"
                  )}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
