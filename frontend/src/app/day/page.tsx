"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type DayBlock, type DayItem, type DayView } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * The day, on one screen.
 *
 * Two layers, deliberately distinct. The faint labels down the left are your
 * timetable template — the *shape* of the day, read from the sheet. They repeat
 * daily and are not tracked; turning 21 recurring blocks into 21 commitments
 * would mean 21 things nagging you every day.
 *
 * The cards are real commitments: study picks, tasks, reminders, anything you
 * add. Drag one to a new slot and it reschedules. Nothing writes back to the
 * timetable sheet, so the template stays intact.
 *
 * Drag-and-drop is the native HTML5 API rather than a library — one dependency
 * not added, and it degrades to the time picker on touch devices.
 */

const START_HOUR = 5;
const END_HOUR = 23;
const SLOT_MINUTES = 30;

const CATEGORIES = [
  { key: "study", label: "STUDY" },
  { key: "practice", label: "PRACTICE" },
  { key: "build", label: "BUILD" },
  { key: "apply", label: "APPLY" },
  { key: "admin", label: "ADMIN" }
];

const SOURCE_TONE: Record<string, string> = {
  study: "border-l-[var(--theme-accent)]",
  apply: "border-l-warning",
  practice: "border-l-success",
  build: "border-l-matrix",
  sheet: "border-l-matrix-dim",
  reminder: "border-l-warning"
};

function slots(): string[] {
  const out: string[] = [];
  for (let h = START_HOUR; h < END_HOUR; h++) {
    for (let m = 0; m < 60; m += SLOT_MINUTES) {
      out.push(`${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`);
    }
  }
  return out;
}

/** Nearest slot at or before a time, so a 05:45 block lands in the 05:30 row. */
function slotFor(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  if (Number.isNaN(h)) return `${String(START_HOUR).padStart(2, "0")}:00`;
  const floored = Math.floor(m / SLOT_MINUTES) * SLOT_MINUTES;
  const hour = Math.min(Math.max(h, START_HOUR), END_HOUR - 1);
  return `${String(hour).padStart(2, "0")}:${String(floored).padStart(2, "0")}`;
}

function shiftDate(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export default function DayPage() {
  const [date, setDate] = useState<string>("");
  const [day, setDay] = useState<DayView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [addTime, setAddTime] = useState("");
  const [category, setCategory] = useState("study");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [artifact, setArtifact] = useState("");
  const [rejection, setRejection] = useState<string | null>(null);
  const nowRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(
    async (d?: string) => {
      try {
        const view = await api.getDay(d);
        setDay(view);
        setDate(view.date);
        setError(null);
      } catch (e) {
        setError((e as Error).message);
      }
    },
    []
  );

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => date && load(date), 30000);
    return () => clearInterval(id);
  }, [date, load]);

  useEffect(() => {
    nowRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [day?.date]);

  const rows = useMemo(() => {
    const blocks = new Map<string, DayBlock[]>();
    const items = new Map<string, DayItem[]>();
    for (const b of day?.blocks ?? []) {
      const s = slotFor(b.start);
      blocks.set(s, [...(blocks.get(s) ?? []), b]);
    }
    for (const i of day?.items ?? []) {
      const s = slotFor(i.local_time);
      items.set(s, [...(items.get(s) ?? []), i]);
    }
    return slots().map((s) => ({
      slot: s,
      blocks: blocks.get(s) ?? [],
      items: items.get(s) ?? []
    }));
  }, [day]);

  const nowSlot = day ? slotFor(day.now_local) : null;
  const isToday = day?.date === new Date().toISOString().slice(0, 10);

  const drop = async (slot: string) => {
    if (!dragging || !day) return;
    setBusy(true);
    setDragOver(null);
    try {
      await api.moveDayItem(dragging, slot, day.date);
      await load(day.date);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDragging(null);
      setBusy(false);
    }
  };

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !day) return;
    setBusy(true);
    try {
      await api.addDayItem({
        title: title.trim(),
        at_time: addTime || undefined,
        date: day.date,
        category
      });
      setTitle("");
      setAddTime("");
      await load(day.date);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const close = async (item: DayItem) => {
    setBusy(true);
    setRejection(null);
    try {
      await api.completeCommitment(item.short_id, { artifact_text: artifact });
      setArtifact("");
      setExpanded(null);
      await load(day?.date);
    } catch (e) {
      const err = e as ApiError;
      setRejection(err.status === 422 ? err.message : `Could not close: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      await load(day?.date);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const proposed = (day?.items ?? []).filter((i) => i.status === "proposed");

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-wider glow-text">⟨ THE DAY ⟩</h1>
          <p className="text-xs text-matrix-dim mt-1 tracking-widest">
            {day ? `${day.weekday.toUpperCase()} · ${day.date}` : "LOADING…"}
            {day?.block_error && " · TIMETABLE UNAVAILABLE"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={() => load(shiftDate(date, -1))}>
            ← PREV
          </Button>
          <Button size="sm" variant="ghost" onClick={() => load()}>
            TODAY
          </Button>
          <Button size="sm" variant="ghost" onClick={() => load(shiftDate(date, 1))}>
            NEXT →
          </Button>
        </div>
      </div>

      {error && (
        <div className="text-xs text-danger border border-danger/40 bg-danger/10 rounded px-4 py-2.5">
          {error}
        </div>
      )}
      {day?.block_error && (
        <div className="text-[11px] text-matrix-dim border border-matrix/20 rounded px-4 py-2">
          Your timetable shape isn&apos;t showing: {day.block_error}. Items still work.
        </div>
      )}
      {proposed.length > 0 && (
        <div className="flex items-center justify-between gap-3 flex-wrap border border-warning/40 bg-warning/5 rounded px-4 py-2.5">
          <span className="text-xs">
            <b>{proposed.length}</b> waiting on your go-ahead — nothing is chasing you yet
          </span>
          <Button
            size="sm"
            variant="matrix"
            disabled={busy}
            onClick={() =>
              act(async () => {
                for (const p of proposed) await api.approveCommitment(p.short_id);
              })
            }
          >
            ✓ APPROVE ALL
          </Button>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm tracking-widest">ADD TO THIS DAY</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={add} className="flex flex-col lg:flex-row gap-3">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Apply to Zelus Analytics · 2 DSA problems · ship the README"
              className="flex-1 bg-bg/50 border border-matrix/30 rounded px-3 py-2 text-sm focus:border-matrix focus:outline-none placeholder:text-matrix-dim/50"
            />
            <input
              value={addTime}
              onChange={(e) => setAddTime(e.target.value)}
              placeholder="14:30"
              className="lg:w-28 bg-bg/50 border border-matrix/30 rounded px-3 py-2 text-sm focus:border-matrix focus:outline-none placeholder:text-matrix-dim/50"
            />
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="lg:w-32 bg-bg/50 border border-matrix/30 rounded px-3 py-2 text-xs tracking-widest focus:border-matrix focus:outline-none"
            >
              {CATEGORIES.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label}
                </option>
              ))}
            </select>
            <Button type="submit" variant="matrix" disabled={busy || !title.trim()}>
              ⟶ ADD
            </Button>
          </form>
          <p className="text-[10px] text-matrix-dim mt-2 tracking-wider">
            Leave the time blank to drop it at now, then drag it where it belongs.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <div className="divide-y divide-bg-border/40">
            {rows.map((row) => {
              const isNow = isToday && row.slot === nowSlot;
              const isTarget = dragOver === row.slot;
              return (
                <div
                  key={row.slot}
                  ref={isNow ? nowRef : undefined}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(row.slot);
                  }}
                  onDragLeave={() => setDragOver((s) => (s === row.slot ? null : s))}
                  onDrop={() => drop(row.slot)}
                  className={cn(
                    "flex items-stretch gap-3 px-4 py-1.5 min-h-[46px] transition-colors",
                    isNow && "bg-matrix/10",
                    isTarget && "bg-matrix/20 outline outline-1 outline-matrix/50"
                  )}
                >
                  <div className="w-14 shrink-0 pt-1 text-[11px] font-mono text-matrix-dim tabular-nums">
                    {row.slot}
                    {isNow && <div className="text-[9px] text-matrix">now</div>}
                  </div>

                  <div className="w-44 shrink-0 pt-1">
                    {row.blocks.map((b, i) => (
                      <div key={i} className="text-[11px] text-matrix-dim/80 leading-tight">
                        {b.label}
                        {b.duration && (
                          <span className="text-matrix-dim/50"> · {b.duration}</span>
                        )}
                      </div>
                    ))}
                  </div>

                  <div className="flex-1 space-y-1.5">
                    {row.items.map((item) => (
                      <div key={item.id}>
                        <div
                          draggable
                          onDragStart={() => setDragging(item.short_id)}
                          onDragEnd={() => setDragging(null)}
                          onClick={() =>
                            setExpanded(expanded === item.id ? null : item.id)
                          }
                          className={cn(
                            "cursor-grab active:cursor-grabbing rounded border border-matrix/25 border-l-2 bg-bg/70 px-3 py-1.5 text-xs hover:border-matrix/50 transition-colors",
                            SOURCE_TONE[item.source] ?? "border-l-matrix/40",
                            dragging === item.short_id && "opacity-40",
                            item.status === "done" && "opacity-50 line-through",
                            item.overdue_sec > 0 && item.status === "open" && "border-danger/50"
                          )}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <span className="min-w-0">{item.title}</span>
                            <span className="flex items-center gap-1.5 shrink-0">
                              {item.status === "proposed" && (
                                <Badge variant="warning">PROPOSED</Badge>
                              )}
                              {item.status === "open" && item.nag_count > 0 && (
                                <Badge variant={item.nag_count >= 4 ? "error" : "warning"}>
                                  {item.nag_count}×
                                </Badge>
                              )}
                              {item.status === "done" && <Badge variant="success">DONE</Badge>}
                            </span>
                          </div>
                          {item.detail && (
                            <div className="text-[10px] text-matrix-dim mt-0.5 truncate">
                              {item.detail}
                            </div>
                          )}
                        </div>

                        {expanded === item.id && item.status !== "done" && (
                          <div className="mt-1.5 ml-2 space-y-2 border-l border-matrix/20 pl-3">
                            {item.status === "proposed" ? (
                              <div className="flex gap-2">
                                <Button
                                  size="sm"
                                  variant="matrix"
                                  disabled={busy}
                                  onClick={() =>
                                    act(() => api.approveCommitment(item.short_id))
                                  }
                                >
                                  ✓ APPROVE
                                </Button>
                                <Button
                                  size="sm"
                                  variant="destructive"
                                  disabled={busy}
                                  onClick={() => act(() => api.dropCommitment(item.short_id))}
                                >
                                  DROP
                                </Button>
                              </div>
                            ) : (
                              <>
                                <textarea
                                  value={artifact}
                                  onChange={(e) => setArtifact(e.target.value)}
                                  placeholder="Paste the link, or 40+ characters of what you made…"
                                  className="w-full h-16 bg-bg/50 border border-matrix/30 rounded p-2 text-[11px] focus:border-matrix focus:outline-none resize-none placeholder:text-matrix-dim/50"
                                />
                                {rejection && (
                                  <div className="text-[10px] text-danger whitespace-pre-wrap">
                                    {rejection}
                                  </div>
                                )}
                                <div className="flex flex-wrap gap-2">
                                  <Button
                                    size="sm"
                                    variant="matrix"
                                    disabled={busy || !artifact.trim()}
                                    onClick={() => close(item)}
                                  >
                                    ✓ CLOSE
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    disabled={busy}
                                    onClick={() =>
                                      act(() => api.snoozeCommitment(item.short_id, 30))
                                    }
                                  >
                                    😴 30M
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="destructive"
                                    disabled={busy}
                                    onClick={() =>
                                      act(() => api.dropCommitment(item.short_id))
                                    }
                                  >
                                    DROP
                                  </Button>
                                </div>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <p className="text-[10px] text-matrix-dim tracking-wider">
        Faint labels are your timetable template — the shape of the day, read from
        the sheet and not tracked. Cards are commitments: drag one to move it, click
        to close it. Reminders stay quiet 22:00–07:00.
      </p>
    </div>
  );
}
