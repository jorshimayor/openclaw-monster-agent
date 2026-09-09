"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ChatAction, type ChatMessage } from "@/lib/api";
import type { Commitment } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const ACTION_LABEL: Record<string, string> = {
  approved: "APPROVED",
  dropped: "DROPPED",
  closed: "CLOSED",
  rescheduled: "RESCHEDULED",
  ambiguous_artifact: "NEEDS AN ID",
  nothing_to_reject: "NO CHANGE"
};

/**
 * The conversation attached to a task. The assistant briefs you on what it
 * proposes to chase; nothing starts until you approve it here or on Telegram.
 */
export default function TaskChat({ taskId }: { taskId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [commitments, setCommitments] = useState<Commitment[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [planOpen, setPlanOpen] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.getChat(taskId);
      setMessages(data.messages ?? []);
      setCommitments(data.commitments ?? []);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [taskId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const send = useCallback(
    async (text: string) => {
      const body = text.trim();
      if (!body || busy) return;
      setBusy(true);
      setError(null);
      // Optimistic echo so the thread feels responsive while the model thinks.
      setMessages((m) => [
        ...m,
        {
          id: `local-${Date.now()}`,
          role: "user",
          content: body,
          created_at: new Date().toISOString()
        }
      ]);
      setDraft("");
      try {
        const res = await api.sendChat(taskId, body);
        setCommitments(res.commitments ?? []);
        await load();
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    },
    [busy, load, taskId]
  );

  const proposed = commitments.filter((c) => c.status === "proposed");
  const open = commitments.filter((c) => c.status === "open");

  return (
    <div className="flex flex-col h-[560px] border border-matrix/25 rounded bg-bg/40">
      {proposed.length > 0 && (
        <div className="border-b border-matrix/25 bg-warning/5">
          <div className="px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
            <button
              type="button"
              onClick={() => setPlanOpen((v) => !v)}
              className="text-xs text-matrix/90 hover:text-matrix flex items-center gap-2"
            >
              <span className="text-matrix-dim">{planOpen ? "▾" : "▸"}</span>
              <span>
                <b>{proposed.length}</b> waiting on your go-ahead · nothing is chasing you yet
              </span>
            </button>
            <Button size="sm" variant="matrix" disabled={busy} onClick={() => send("approve")}>
              ✓ APPROVE ALL
            </Button>
          </div>

          {/* The plan itself, inspectable. The brief prose alone never showed
              what each item actually was or when it lands. */}
          {planOpen && (
            <div className="px-4 pb-3 space-y-2">
              {proposed.map((c) => (
                <div
                  key={c.id}
                  className="rounded border border-matrix/20 bg-bg/60 px-3 py-2.5 text-xs"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-matrix/95">{c.title}</div>
                      {c.detail && (
                        <div className="text-[11px] text-matrix-dim mt-1 leading-relaxed">
                          {c.detail}
                        </div>
                      )}
                      <div className="text-[10px] text-matrix-dim tracking-wider mt-1.5">
                        <span className="font-mono">{c.short_id}</span>
                        {" · "}
                        {c.due_at
                          ? new Date(c.due_at).toLocaleString(undefined, {
                              weekday: "short",
                              day: "2-digit",
                              month: "short",
                              hour: "2-digit",
                              minute: "2-digit"
                            })
                          : "no due time"}
                        {c.source === "sheet" && " · from your sheet"}
                      </div>
                    </div>
                    <div className="flex flex-col gap-1 shrink-0">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => send(`approve ${c.short_id}`)}
                        className="text-[10px] tracking-widest px-2 py-1 rounded border border-success/40 text-success hover:bg-success/10 disabled:opacity-40"
                      >
                        APPROVE
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => send(`drop ${c.short_id}`)}
                        className="text-[10px] tracking-widest px-2 py-1 rounded border border-danger/40 text-danger hover:bg-danger/10 disabled:opacity-40"
                      >
                        DROP
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => setDraft(`move ${c.short_id} to tomorrow evening`)}
                        className="text-[10px] tracking-widest px-2 py-1 rounded border border-matrix/30 hover:bg-matrix/10 disabled:opacity-40"
                      >
                        MOVE
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {open.length > 0 && (
        <div className="px-4 py-2 border-b border-matrix/20 text-[11px] text-matrix-dim tracking-wider">
          {open.length} live · being chased until closed with an artifact
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && !error && (
          <div className="text-xs text-matrix-dim text-center py-10">
            NO CONVERSATION YET · ASK ANYTHING ABOUT THIS TASK
          </div>
        )}
        {messages.map((m) => {
          const mine = m.role === "user";
          const actions: ChatAction[] = m.meta?.actions ?? [];
          return (
            <div key={m.id} className={cn("flex", mine ? "justify-end" : "justify-start")}>
              <div
                className={cn(
                  "max-w-[85%] rounded px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap",
                  mine
                    ? "bg-matrix/15 border border-matrix/40 text-matrix"
                    : "bg-bg/70 border border-matrix/20 text-matrix/90"
                )}
              >
                {m.content}
                {actions.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-matrix/15 flex flex-wrap gap-1.5">
                    {actions.map((a, i) => (
                      <Badge
                        key={i}
                        variant={
                          a.type === "closed" || a.type === "approved"
                            ? "success"
                            : a.type === "dropped"
                            ? "error"
                            : "warning"
                        }
                      >
                        {ACTION_LABEL[a.type] ?? a.type.toUpperCase()}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {busy && (
          <div className="text-[11px] text-matrix-dim tracking-widest">THINKING…</div>
        )}
        <div ref={endRef} />
      </div>

      {error && (
        <div className="px-4 py-2 text-[11px] text-danger border-t border-danger/30">{error}</div>
      )}

      <div className="border-t border-matrix/25 p-3 space-y-2">
        <div className="flex flex-wrap gap-1.5">
          {proposed.length > 0 && (
            <button
              type="button"
              onClick={() => send("approve")}
              className="text-[10px] tracking-widest px-2 py-1 rounded border border-matrix/30 hover:bg-matrix/10"
            >
              APPROVE ALL
            </button>
          )}
          {open.length > 0 && (
            <button
              type="button"
              onClick={() => setDraft("Done — here's the proof: ")}
              className="text-[10px] tracking-widest px-2 py-1 rounded border border-matrix/30 hover:bg-matrix/10"
            >
              + ARTIFACT
            </button>
          )}
          <button
            type="button"
            onClick={() => setDraft("Why did you schedule these the way you did?")}
            className="text-[10px] tracking-widest px-2 py-1 rounded border border-matrix/30 hover:bg-matrix/10"
          >
            ASK WHY
          </button>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(draft);
          }}
          className="flex gap-2"
        >
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={busy}
            placeholder="approve · push the README to friday evening · here's the link…"
            className="flex-1 bg-bg/50 border border-matrix/30 rounded px-3 py-2 text-xs focus:border-matrix focus:outline-none placeholder:text-matrix-dim/50 disabled:opacity-60"
          />
          <Button type="submit" size="sm" variant="matrix" disabled={busy || !draft.trim()}>
            SEND
          </Button>
        </form>
      </div>
    </div>
  );
}
