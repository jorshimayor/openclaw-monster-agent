import type { AgentResult, PipelineStep } from "./types";

export interface LogEntry {
  time: string;
  step: string;
  agent: string;
  msg: string;
  shade: 0 | 1 | 2 | 3 | 4;
}

export interface PipelineEvent {
  type: "step_complete" | "agent_output" | "pipeline_complete" | "error" | "info" | "step_start";
  step?: PipelineStep;
  timestamp: string;
  message?: string;
  output?: AgentResult;
  finalReport?: string;
  error?: string;
}
