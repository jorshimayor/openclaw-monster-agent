"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError, type CommitmentsHealth } from "@/lib/api";
import type { Commitment } from "@/lib/types";
import { cn } from "@/lib/utils";

function overdueLabel(sec: number): string {
  if (sec <= 0) return "";
  const mins = Math.floor(sec / 60);
  if (mins < 60) return `${mins}m over`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h over`;
  return `${Math.floor(hours / 24)}d over`;
}

function dueLabel(iso: string | null): string {
  if (!iso) return "no due time";
  return iso.slice(0, 16).replace("T", " ") + " UTC";
}

function CloseForm({
  commitment,
  onClosed
}: {
  commitment: Commitment;
  onClosed: () => void;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [rejection, setRejection] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setRejection(null);
    try {
      // Send everything as text; the backend pulls a URL out of it if there is
      // one, and decides whether it counts. One rule, one place.
      await api.completeCommitment(commitment.id, { artifact_text: value });
      setValue("");
      onClosed();
    } catch (e) {
      const err = e as ApiError;
      setRejection(
        err.status === 422 ? err.message : `Could not close: ${err.message}`
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2">
      <textarea
        value={value}
        onChange={(ev) => setValue(ev.target.value)}
        placeholder="Paste the link, or 40+ characters of what you actually made…"
        className="w-full h-20 bg-bg/50 border border-matrix/30 rounded p-3 text-xs focus:border-matrix focus:outline-none focus:shadow-matrix-glow placeholder:text-matrix-dim/50 resize-none"
      />
      {rejection && (
        <div className="text-[11px] text-danger whitespace-pre-wrap border border-danger/40 bg-danger/10 rounded p-2">
          {rejection}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="matrix" size="sm" disabled={busy || !value.trim()}>
          {busy ? "CHECKING…" : "✓ CLOSE WITH ARTIFACT"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={async () => {
            await api.snoozeCommitment(commitment.id, 30).catch(() => {});
            onClosed();
          }}
        >
          😴 SNOOZE 30M
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={async () => {
            await api.nagCommitment(commitment.id).catch(() => {});
            onClosed();
          }}
        >
          📣 POKE ME NOW
        </Button>
        <Button
          type="button"
          size="sm"
          variant="destructive"
          disabled={busy}
          onClick={async () => {
            await api.dropCommitment(commitment.id).catch(() => {});
            onClosed();
          }}
        >
          🗑 DROP
        </Button>
      </div>
    </form>
  );
}

export default function CommitmentsPage() {
  const [open, setOpen] = useState<Commitment[] | null>(null);
  const [closed, setClosed] = useState<Commitment[]>([]);
  const [health, setHealth] = useState<CommitmentsHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newWhen, setNewWhen] = useState("");
  const [adding, setAdding] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [all, h] = await Promise.all([
        api.listCommitments(),
        api.commitmentsHealth().catch(() => null)
      ]);
      setOpen(all.filter((c) => c.status === "open"));
      setClosed(all.filter((c) => c.status !== "open").slice(0, 25));
      setHealth(h);
      setError(null);
    } catch (e) {
      setOpen([]);
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    reload();
    const id = setInterval(reload, 10000);
    return () => clearInterval(id);
  }, [reload]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setAdding(true);
    try {
      const when = newWhen.toLowerCase().split(/[\s,]+/).filter(Boolean);
      const dayWords = [
        "today", "tomorrow", "tonight", "monday", "tuesday", "wednesday",
        "thursday", "friday", "saturday", "sunday"
      ];
      const todWords = ["morning", "afternoon", "evening", "night", "noon"];
      await api.createCommitment({
        title: newTitle.trim(),
        day: when.find((w) => dayWords.includes(w)),
        time_of_day: when.find((w) => todWords.includes(w))
      });
      setNewTitle("");
      setNewWhen("");
      reload();
    } finally {
      setAdding(false);
    }
  };

  const overdue = (open ?? []).filter((c) => c.overdue_sec > 0);
  const upcoming = (open ?? []).filter((c) => c.overdue_sec === 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-wider glow-text">
          ⟨ COMMITMENTS · WHAT YOU OWE ⟩
        </h1>
        <p className="text-xs text-matrix-dim mt-1 tracking-widest">
          THE ASSISTANT CHASES EACH ONE UNTIL AN ARTIFACT CLOSES IT
        </p>
      </div>

      {error && (
        <Card>
          <CardContent className="py-6 text-xs text-danger">
            COMMITMENT LEDGER UNAVAILABLE · {error}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "OVERDUE", value: overdue.length, danger: overdue.length > 0 },
          { label: "UPCOMING", value: upcoming.length, danger: false },
          { label: "CLOSED", value: health?.stats.done ?? 0, danger: false },
          { label: "DROPPED", value: health?.stats.dropped ?? 0, danger: false }
        ].map((s) => (
          <div
            key={s.label}
            className={cn(
              "rounded border bg-bg/50 p-4",
              s.danger ? "border-danger/50" : "border-matrix/20"
            )}
          >
            <div className="text-[10px] text-matrix-dim tracking-widest mb-1.5">
              {s.label}
            </div>
            <div
              className={cn(
                "text-2xl font-bold tracking-wider",
                s.danger ? "text-danger" : "glow-text"
              )}
            >
              {open === null ? "—" : s.value}
            </div>
          </div>
        ))}
      </div>

      {health && (
        <div className="text-[10px] text-matrix-dim tracking-wider flex flex-wrap gap-x-5 gap-y-1">
          <span>
            REMINDER LOOP:{" "}
            <span className={health.nag.worker_alive ? "text-success" : "text-warning"}>
              {health.nag.worker_alive ? "RUNNING" : "CRON-DRIVEN"}
            </span>
          </span>
          <span suppressHydrationWarning>
            LAST CHECK: {health.nag.last_tick?.slice(0, 19).replace("T", " ") ?? "NOT YET"}
          </span>
          <span>
            STORAGE:{" "}
            <span className={health.db_backed ? "text-success" : "text-danger"}>
              {health.db_backed ? "POSTGRES" : "IN-MEMORY (LOST ON RESTART)"}
            </span>
          </span>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm tracking-widest">PUT SOMETHING ON THE HOOK</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={add} className="flex flex-col sm:flex-row gap-3">
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Rewrite the chelsea_bot README for a hiring manager"
              className="flex-1 bg-bg/50 border border-matrix/30 rounded px-3 py-2 text-sm focus:border-matrix focus:outline-none focus:shadow-matrix-glow placeholder:text-matrix-dim/50"
            />
            <input
              value={newWhen}
              onChange={(e) => setNewWhen(e.target.value)}
              placeholder="tomorrow evening"
              className="sm:w-52 bg-bg/50 border border-matrix/30 rounded px-3 py-2 text-sm focus:border-matrix focus:outline-none focus:shadow-matrix-glow placeholder:text-matrix-dim/50"
            />
            <Button type="submit" variant="matrix" disabled={adding || !newTitle.trim()}>
              {adding ? "FILING…" : "⟶ FILE IT"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm tracking-widest flex items-center justify-between">
            <span>OPEN</span>
            <span className="text-xs text-matrix-dim">
              {open === null ? "LOADING…" : `${open.length} TOTAL`}
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {open !== null && open.length === 0 && (
            <div className="px-6 py-12 text-center text-matrix-dim text-xs">
              NOTHING OPEN · YOU'RE CLEAR
            </div>
          )}
          <div className="divide-y divide-bg-border/60">
            {[...overdue, ...upcoming].map((c) => {
              const isOpen = expanded === c.id;
              const late = c.overdue_sec > 0;
              return (
                <div key={c.id} className="px-6 py-4">
                  <button
                    type="button"
                    className="w-full text-left"
                    onClick={() => setExpanded(isOpen ? null : c.id)}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                          <Badge variant={late ? "error" : "default"}>
                            {late ? overdueLabel(c.overdue_sec) : "SCHEDULED"}
                          </Badge>
                          {c.nag_count > 0 && (
                            <Badge variant={c.nag_count >= 4 ? "error" : "warning"}>
                              {c.nag_count} REMINDER{c.nag_count === 1 ? "" : "S"}
                            </Badge>
                          )}
                          {c.snooze_until && <Badge variant="warning">SNOOZED</Badge>}
                        </div>
                        <div className="text-sm">{c.title}</div>
                        {c.detail && (
                          <div className="text-xs text-matrix-dim mt-1">{c.detail}</div>
                        )}
                      </div>
                      <div className="text-[10px] text-matrix-dim tracking-wider text-right shrink-0">
                        <div>{c.short_id}</div>
                        <div className="mt-0.5" suppressHydrationWarning>
                          {dueLabel(c.due_at)}
                        </div>
                        {c.task_id && (
                          <Link
                            href={`/tasks/${c.task_id}`}
                            className="text-matrix hover:underline mt-0.5 inline-block"
                            onClick={(e) => e.stopPropagation()}
                          >
                            from task
                          </Link>
                        )}
                      </div>
                    </div>
                  </button>
                  {isOpen && (
                    <div className="mt-4">
                      <CloseForm commitment={c} onClosed={reload} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {closed.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm tracking-widest">RECENTLY SETTLED</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-bg-border/60">
              {closed.map((c) => (
                <div key={c.id} className="px-6 py-3 flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant={c.status === "done" ? "success" : "error"}>
                        {c.status.toUpperCase()}
                      </Badge>
                      {c.artifact_kind && (
                        <span className="text-[10px] text-matrix-dim tracking-widest">
                          {c.artifact_kind.toUpperCase()} ARTIFACT
                        </span>
                      )}
                    </div>
                    <div className="text-xs truncate">{c.title}</div>
                    {c.artifact_url && (
                      <a
                        href={
                          c.artifact_url.startsWith("http") ? c.artifact_url : undefined
                        }
                        target="_blank"
                        rel="noreferrer noopener"
                        className="text-[11px] text-matrix hover:underline break-all"
                      >
                        {c.artifact_url}
                      </a>
                    )}
                  </div>
                  <div className="text-[10px] text-matrix-dim text-right shrink-0">
                    <div>{c.short_id}</div>
                    <div suppressHydrationWarning>
                      {c.completed_at?.slice(0, 16).replace("T", " ") ?? ""}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
