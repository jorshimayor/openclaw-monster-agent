"use client";

import { useEffect, useRef } from "react";
import type { LogEntry } from "@/lib/events";
import { useIsHydrated } from "@/lib/hydration";

export interface LogPanelProps {
  entries?: LogEntry[];
}

const PLACEHOLDER_LOGS: LogEntry[] = [
  {
    time: "--:--:--",
    step: "INIT",
    agent: "SYSTEM",
    msg: "log panel loaded · client-side initialization in progress…",
    shade: 3
  }
];

const DEFAULT_LOGS: LogEntry[] = [
  {
    time: new Date().toISOString().slice(11, 19),
    step: "INIT",
    agent: "SYSTEM",
    msg: "log panel initialized · awaiting streaming events",
    shade: 3
  }
];

const SHADE = [
  "text-matrix",
  "text-matrix/90",
  "text-matrix/75",
  "text-matrix-dim",
  "text-matrix-dim/70"
];

export function LogPanel({ entries }: LogPanelProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const hydrated = useIsHydrated();
  const baseData = entries && entries.length > 0 ? entries : DEFAULT_LOGS;
  const data = hydrated ? baseData : PLACEHOLDER_LOGS;

  useEffect(() => {
    if (ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight;
    }
  }, [data]);

  return (
    <div
      ref={ref}
      className="h-[420px] overflow-auto bg-bg/60 border border-matrix/30 rounded p-4 text-xs font-mono leading-relaxed"
    >
      <div className="space-y-0.5">
        {data.map((l, i) => (
          <div key={i} className="flex gap-3 whitespace-pre">
            <span className="text-matrix-dim/70 shrink-0 select-none">
              {l.time}
            </span>
            <span className="text-matrix-dim shrink-0 select-none w-[10ch]">
              [{l.step}]
            </span>
            <span
              className={`shrink-0 w-[12ch] select-none ${
                l.agent === "ORCH"
                  ? "text-matrix"
                  : l.agent === "SYSTEM"
                  ? "text-matrix-dim"
                  : "text-matrix/85"
              }`}
            >
              [{l.agent}]
            </span>
            <span className={SHADE[l.shade] ?? "text-matrix/70"}>{l.msg}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-2 text-matrix-dim/80">
        <span className="inline-block w-2 h-4 bg-matrix/90 animate-pulse" />
        <span className="text-[10px] tracking-widest">LIVE · {data.length} ENTRIES</span>
      </div>
    </div>
  );
}
