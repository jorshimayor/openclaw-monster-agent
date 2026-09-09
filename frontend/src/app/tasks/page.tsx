"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { Task } from "@/lib/types";
import { formatDate, truncate } from "@/lib/utils";

const PAGE_SIZE = 20;

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
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Task | null>(null);

  const reload = useCallback(() => {
    api
      .listTasks(page * PAGE_SIZE, PAGE_SIZE)
      .then(setTasks)
      .catch(() => {});
    api.countTasks().then(setTotal).catch(() => {});
  }, [page]);

  useEffect(() => {
    reload();
    const id = setInterval(reload, 5000);
    return () => clearInterval(id);
  }, [reload]);

  const remove = async (task: Task) => {
    setDeleting(task.id);
    try {
      await api.deleteTask(task.id);
      setConfirmDelete(null);
      reload();
    } finally {
      setDeleting(null);
    }
  };

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim()) return;
    setLoading(true);
    try {
      await api.submitTask(description.trim());
      setDescription("");
      setPage(0);
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
              className="w-full h-32 bg-bg/50 border border-matrix/30 rounded p-4 text-sm focus:border-matrix focus:outline-none focus:shadow-matrix-glow placeholder:text-matrix-dim/50 resize-none"
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
            <span>ACTIVE &amp; HISTORICAL TASKS</span>
            <span className="text-xs text-matrix-dim">
              {total > 0
                ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} OF ${total}`
                : `${tasks.length} TOTAL`}
            </span>
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
                  <th className="text-right px-6 py-3 font-normal tracking-widest">ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {tasks.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center text-matrix-dim">
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
                      <td className="px-6 py-4 text-matrix-dim" suppressHydrationWarning>
                        {formatDate(t.createdAt)}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button
                          type="button"
                          onClick={() => setConfirmDelete(t)}
                          disabled={deleting === t.id}
                          className="text-matrix-dim hover:text-danger transition-colors disabled:opacity-40"
                          title="Delete this task and any commitments it filed"
                        >
                          {deleting === t.id ? "…" : "🗑"}
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          {pageCount > 1 && (
            <div className="flex items-center justify-between px-6 py-3 border-t border-bg-border text-xs">
              <Button
                variant="ghost"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                ← PREV
              </Button>
              <span className="text-matrix-dim tracking-widest">
                PAGE {page + 1} / {pageCount}
              </span>
              <Button
                variant="ghost"
                size="sm"
                disabled={page + 1 >= pageCount}
                onClick={() => setPage((p) => p + 1)}
              >
                NEXT →
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <Card className="max-w-md w-full">
            <CardHeader>
              <CardTitle className="text-sm tracking-widest text-danger">
                DELETE TASK?
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-xs text-matrix/90 leading-relaxed">
                {truncate(confirmDelete.description, 160)}
              </p>
              <p className="text-[11px] text-matrix-dim leading-relaxed">
                This also deletes any commitments this task put on your hook, so
                you stop being reminded about work whose origin is gone. It
                cannot be undone.
              </p>
              <div className="flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(null)}>
                  CANCEL
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={deleting === confirmDelete.id}
                  onClick={() => remove(confirmDelete)}
                >
                  {deleting === confirmDelete.id ? "DELETING…" : "DELETE"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
