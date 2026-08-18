"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { Task } from "@/lib/types";
import { formatDate, truncate } from "@/lib/utils";

const STATUS_VARIANT: Record<Task["status"], "default" | "success" | "warning" | "error"> = {
  queued: "default",
  running: "warning",
  reworking: "warning",
  completed: "success",
  failed: "error"
};

export default function TasksPage() {
  const [description, setDescription] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(() => {
    api.listTasks().then(setTasks).catch(() => {});
  }, []);

  useEffect(() => {
    reload();
    const id = setInterval(reload, 5000);
    return () => clearInterval(id);
  }, [reload]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim()) return;
    setLoading(true);
    try {
      await api.submitTask(description.trim());
      setDescription("");
      reload();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-wider glow-text">⟨ TASK QUEUE ⟩</h1>
        <p className="text-xs text-matrix-dim mt-1 tracking-widest">
          SUBMIT, MONITOR, AND TRACE MULTI-AGENT PIPELINE EXECUTIONS
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm tracking-widest">SUBMIT TASK</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the task... (e.g. 'Research Solana memecoins Q3 2026 and write a Twitter thread')"
              className="w-full h-32 bg-black/40 border border-matrix/30 rounded p-4 text-sm focus:border-matrix focus:outline-none focus:shadow-matrix-glow placeholder:text-matrix-dim/50 resize-none"
            />
            <div className="flex justify-end">
              <Button type="submit" variant="matrix" disabled={loading}>
                {loading ? "QUEUEING..." : "⟶ DISPATCH TO AGENT TEAM"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm tracking-widest flex items-center justify-between">
            <span>ACTIVE & HISTORICAL TASKS</span>
            <span className="text-xs text-matrix-dim">{tasks.length} TOTAL</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-bg-border text-matrix-dim">
                  <th className="text-left px-6 py-3 font-normal tracking-widest">ID</th>
                  <th className="text-left px-6 py-3 font-normal tracking-widest">DESCRIPTION</th>
                  <th className="text-left px-6 py-3 font-normal tracking-widest">STATUS</th>
                  <th className="text-left px-6 py-3 font-normal tracking-widest">CURRENT STEP</th>
                  <th className="text-left px-6 py-3 font-normal tracking-widest">CREATED</th>
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-12 text-center text-matrix-dim">
                      NO TASKS YET · SUBMIT ONE ABOVE TO INITIATE PIPELINE
                    </td>
                  </tr>
                ) : (
                  tasks.map((t) => (
                    <tr
                      key={t.id}
                      className="border-b border-bg-border/50 hover:bg-matrix/5 transition-colors"
                    >
                      <td className="px-6 py-4">
                        <Link
                          href={`/tasks/${t.id}`}
                          className="text-matrix hover:underline"
                        >
                          {t.id.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="px-6 py-4 max-w-md">
                        {truncate(t.description, 80)}
                      </td>
                      <td className="px-6 py-4">
                        <Badge variant={STATUS_VARIANT[t.status]}>{t.status.toUpperCase()}</Badge>
                      </td>
                      <td className="px-6 py-4 text-matrix-dim">
                        {t.currentStep ? t.currentStep.toUpperCase() : "—"}
                      </td>
                      <td className="px-6 py-4 text-matrix-dim">{formatDate(t.createdAt)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
