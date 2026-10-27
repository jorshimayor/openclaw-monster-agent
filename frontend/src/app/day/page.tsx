"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type DayBlock, type DayItem, type DayView } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * The day, drawn to scale.
 *
 * Every block is positioned and sized by its real start and end, so a
 * fifteen-minute break is a sliver and a ninety-minute deep block is six times
 * taller. The previous version bucketed everything into fixed half-hours,
 * which drew those two the same size and lost the one thing a timetable is
 * for — seeing where the long stretches are.
 *
 * Two layers, deliberately distinct. The middle column is your timetable
 * template, read from the sheet: the *shape* of the day. It repeats daily and
 * is not tracked, because turning 19 recurring blocks into 19 commitments
 * would mean 19 things nagging you every morning. Ticking one is recorded for
 * that date only and never written back to the shared sheet.
 *
 * The right lane holds real commitments: study picks, tasks, reminders,
 * anything you add. Drag one and it reschedules to wherever you dropped it,
 * snapped to the quarter hour.
 *
 * Drag-and-drop is the native HTML5 API rather than a library — one dependency
 * not added, and it degrades to the time field on touch devices.
 */

/** Pixels per minute. The whole timeline is this one number times a duration. */
const DENSITY = { compact: 0.8, comfortable: 1.5 } as const;
type Density = keyof typeof DENSITY;

const SNAP_MINUTES = 15;
/**
 * A commitment is a point in time, not a span, so every card is the same
 * height and titles are clamped to two lines. Letting cards size to their
 * content would mean the stacker could not know where the next one starts,
 * and a three-line card would be written over by the card below it.
 */
const ITEM_HEIGHT = 56;
const ITEM_GAP = 4;
const FALLBACK_BOUNDS = { from: 5 * 60, to: 22 * 60 };

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

/**
 * What kind of hour this is, by what the sheet calls it.
 *
 * Colour carries the one judgement worth making at a glance: how much of the
 * day is actually focused work versus upkeep. Keyword matching rather than a
 * column in the sheet, so adding a row needs no extra bookkeeping.
 */
const TONES = [
  {
    match: /deep block|study|reading|anchor|bounty|audit|interview|practice/i,
    bar: "border-l-[var(--theme-accent)]",
    fill: "bg-matrix/[0.09] group-hover:bg-matrix/[0.16]",
    label: "focus"
  },
  {
    match: /walk|stretch|gym|workout|run|sleep/i,
    bar: "border-l-success",
    fill: "bg-success/[0.09] group-hover:bg-success/[0.16]",
    label: "body"
  },
  {
    match: /content|writing|open source|portfolio|build|ship/i,
    bar: "border-l-warning",
    fill: "bg-warning/[0.09] group-hover:bg-warning/[0.16]",
    label: "make"
  }
] as const;

const UPKEEP = {
  bar: "border-l-matrix-dim/60",
  fill: "bg-bg-panel group-hover:bg-matrix/[0.08]",
  label: "upkeep"
} as const;

function toneFor(label: string) {
  return TONES.find((t) => t.match.test(label)) ?? UPKEEP;
}

function toMinutes(hhmm: string): number {
  const [h, m] = (hhmm ?? "").split(":").map(Number);
  return Number.isFinite(h) ? h * 60 + (Number.isFinite(m) ? m : 0) : 0;
}

function toHHMM(minutes: number): string {
  const clamped = ((Math.round(minutes) % 1440) + 1440) % 1440;
  const h = Math.floor(clamped / 60);
  return `${String(h).padStart(2, "0")}:${String(clamped % 60).padStart(2, "0")}`;
}

/**
 * Fill in anything an older backend did not send.
 *
 * A Worker deploy goes live well before the container behind it restarts, so
 * for a few minutes the page can be served new while the API is still old.
 * Deriving the end from the duration — the same rule the backend uses — keeps
 * the timeline drawable across that window instead of collapsing every block
 * to a NaN height.
 */
function normalize(blocks: DayBlock[]): DayBlock[] {
  return blocks.map((b, i) => {
    if (b.end && Number.isFinite(b.minutes)) return b;
    const start = toMinutes(b.start);
    const parsed = /(\d+(?:\.\d+)?)\s*(hour|hr|h|min)/i.exec(b.duration ?? "");
    let minutes = parsed
      ? Math.round(parseFloat(parsed[1]) * (/^h/i.test(parsed[2]) ? 60 : 1))
      : 0;
    if (!minutes) {
      const next = blocks[i + 1] ? toMinutes(blocks[i + 1].start) : start + 30;
      minutes = Math.max(15, next - start);
    }
    return { ...b, minutes, end: b.end || toHHMM(start + minutes) };
  });
}

function shiftDate(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function readDensity(): Density {
  try {
    return localStorage.getItem("day.density") === "compact" ? "compact" : "comfortable";
  } catch {
    return "comfortable";
  }
}

export default function DayPage() {
  const [date, setDate] = useState<string>("");
  /**
   * Which date the backend considers today, taken from a load with no date.
   * The browser's own UTC date is a day out either side of midnight in your
   * offset, and the now-line must not appear on the wrong day.
   */
  const [todayIso, setTodayIso] = useState<string | null>(null);
  const [day, setDay] = useState<DayView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [density, setDensity] = useState<Density>("comfortable");
  const [dragging, setDragging] = useState<string | null>(null);
  const [dropAt, setDropAt] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [addTime, setAddTime] = useState("");
  const [category, setCategory] = useState("study");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [artifact, setArtifact] = useState("");
  const [rejection, setRejection] = useState<string | null>(null);
  const nowRef = useRef<HTMLDivElement | null>(null);
  const laneRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => setDensity(readDensity()), []);

  const load = useCallback(async (d?: string) => {
    try {
      const view = await api.getDay(d);
      setDay(view);
      setDate(view.date);
      if (!d) setTodayIso(view.date);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(() => date && load(date), 30000);
    return () => clearInterval(id);
  }, [date, load]);

  const blocks = useMemo(() => normalize(day?.blocks ?? []), [day]);
  const pxPerMin = DENSITY[density];
  const isToday = day !== null && day.date === todayIso;
  const nowMinutes = day ? toMinutes(day.now_local) : 0;

  const setDensityPersisted = (next: Density) => {
    setDensity(next);
    try {
      localStorage.setItem("day.density", next);
    } catch {
      /* private browsing; the toggle still works for this visit */
    }
  };

  /**
   * The window the timeline covers: the hours the day actually occupies,
   * rounded out to whole hours, widened to hold any commitment that sits
   * outside the template so nothing is ever positioned off-canvas.
   */
  const bounds = useMemo(() => {
    let from = blocks.length
      ? Math.min(...blocks.map((b) => toMinutes(b.start)))
      : FALLBACK_BOUNDS.from;
    let to = blocks.length
      ? Math.max(...blocks.map((b) => toMinutes(b.end)))
      : FALLBACK_BOUNDS.to;
    for (const item of day?.items ?? []) {
      const at = toMinutes(item.local_time);
      from = Math.min(from, at);
      to = Math.max(to, at + 30);
    }
    if (isToday) {
      from = Math.min(from, nowMinutes);
      to = Math.max(to, nowMinutes + 15);
    }
    from = Math.floor(from / 60) * 60;
    to = Math.ceil(to / 60) * 60;
    return { from, to, span: Math.max(to - from, 60) };
  }, [blocks, day, isToday, nowMinutes]);

  const offsetOf = useCallback(
    (minutes: number) => (minutes - bounds.from) * pxPerMin,
    [bounds.from, pxPerMin]
  );

  const hours = useMemo(() => {
    const out: number[] = [];
    for (let m = bounds.from; m <= bounds.to; m += 60) out.push(m);
    return out;
  }, [bounds.from, bounds.to]);

  /**
   * Commitments that would land on top of each other are pushed down the lane
   * rather than squeezed side by side. Six things due at 07:30 as six narrow
   * columns is six unreadable columns; stacked, they stay full width and the
   * card carries its real time, which is the part that matters.
   */
  const laidOut = useMemo(() => {
    let cursor = -Infinity;
    const placed = [...(day?.items ?? [])]
      .sort((a, b) => a.local_time.localeCompare(b.local_time))
      .map((item) => {
        const at = offsetOf(toMinutes(item.local_time));
        const top = Math.max(at, cursor);
        cursor = top + ITEM_HEIGHT + ITEM_GAP;
        return { item, top, nudged: top > at + 1 };
      });
    return { placed, bottom: placed.length ? cursor : 0 };
  }, [day, offsetOf]);

  const current = isToday
    ? blocks.find(
        (b) => nowMinutes >= toMinutes(b.start) && nowMinutes < toMinutes(b.end)
      )
    : undefined;
  const upNext = isToday
    ? blocks.find((b) => toMinutes(b.start) > nowMinutes)
    : undefined;

  const progress = useMemo(() => {
    const total = blocks.reduce((sum, b) => sum + b.minutes, 0);
    const done = blocks.filter((b) => b.done).reduce((sum, b) => sum + b.minutes, 0);
    return { total, done, pct: total ? Math.round((done / total) * 100) : 0 };
  }, [blocks]);

  /** The sheet rows the backend had to correct, so they can be fixed at source. */
  const corrected = blocks.filter(
    (b) => b.meridiem_corrected || b.shifted || b.duration_inferred
  );

  useEffect(() => {
    nowRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [day?.date, density]);

  const timeAtY = (clientY: number): string => {
    const rect = laneRef.current?.getBoundingClientRect();
    if (!rect) return toHHMM(bounds.from);
    const raw = bounds.from + (clientY - rect.top) / pxPerMin;
    const snapped = Math.round(raw / SNAP_MINUTES) * SNAP_MINUTES;
    return toHHMM(Math.min(Math.max(snapped, bounds.from), bounds.to));
  };

  const drop = async (at: string) => {
    if (!dragging || !day) return;
    setBusy(true);
    setDropAt(null);
    try {
      await api.moveDayItem(dragging, at, day.date);
      await load(day.date);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDragging(null);
      setBusy(false);
    }
  };

  const toggleBlock = async (block: DayBlock) => {
    if (!day) return;
    setBusy(true);
    // Optimistic: ticking a block is the fastest interaction on the page and
    // should not wait on a round trip.
    setDay({
      ...day,
      blocks: day.blocks.map((b) =>
        b.start === block.start && b.label === block.label ? { ...b, done: !b.done } : b
      )
    });
    try {
      await api.setBlockDone(block.start, block.label, !block.done, day.date);
    } catch (e) {
      setError((e as Error).message);
      await load(day.date);
    } finally {
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
            {isToday && day && ` · ${day.now_local}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            title="Switch timeline scale"
            onClick={() =>
              setDensityPersisted(density === "compact" ? "comfortable" : "compact")
            }
          >
            {density === "compact" ? "⤢ ROOMY" : "⤡ TIGHT"}
          </Button>
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

      {/* Where you are right now, which is the only thing worth reading first. */}
      {isToday && (current || upNext) && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border border-matrix/30 bg-matrix/[0.04] rounded px-4 py-3">
          {current ? (
            <div className="min-w-0">
              <div className="text-[10px] text-matrix-dim tracking-widest">NOW</div>
              <div className="text-sm truncate">
                {current.label}
                <span className="text-matrix-dim text-xs">
                  {" "}
                  · {Math.max(0, toMinutes(current.end) - nowMinutes)}m left
                </span>
              </div>
            </div>
          ) : (
            <div className="text-xs text-matrix-dim">Nothing scheduled right now.</div>
          )}
          {upNext && (
            <div className="min-w-0">
              <div className="text-[10px] text-matrix-dim tracking-widest">NEXT</div>
              <div className="text-sm truncate">
                {upNext.start} {upNext.label}
              </div>
            </div>
          )}
          <div className="ml-auto flex items-center gap-3">
            <div className="h-1.5 w-28 rounded-full bg-bg-border overflow-hidden">
              <div
                className="h-full bg-matrix transition-[width] duration-500"
                style={{ width: `${progress.pct}%` }}
              />
            </div>
            <span className="text-[10px] text-matrix-dim tabular-nums tracking-wider">
              {progress.pct}% · {Math.round(progress.done / 60)}h of{" "}
              {Math.round(progress.total / 60)}h
            </span>
          </div>
        </div>
      )}

      {day?.themes?.cycled && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border border-matrix/25 rounded px-4 py-2.5 text-xs">
          <span className="text-matrix-dim tracking-widest text-[10px]">TODAY</span>
          {day.themes.daily.map((t) => (
            <Badge key={t} variant="success">
              {t.toUpperCase()} · DAILY
            </Badge>
          ))}
          <Badge variant="default">{day.themes.cycled.toUpperCase()}</Badge>
          <span className="text-[10px] text-matrix-dim tracking-wider ml-auto">
            next: {day.themes.upcoming.map((u) => u.theme).join(" → ")}
          </span>
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
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-bg-border/60 px-4 py-2 text-[10px] tracking-widest text-matrix-dim">
            <span>TIMETABLE</span>
            <span className="flex items-center gap-1.5">
              <i className="h-2 w-2 rounded-sm bg-matrix/70 not-italic" /> FOCUS
            </span>
            <span className="flex items-center gap-1.5">
              <i className="h-2 w-2 rounded-sm bg-success/70 not-italic" /> BODY
            </span>
            <span className="flex items-center gap-1.5">
              <i className="h-2 w-2 rounded-sm bg-warning/70 not-italic" /> MAKE
            </span>
            <span className="ml-auto">COMMITMENTS →</span>
          </div>

          <div className="overflow-x-auto px-3 py-4">
            <div
              className="relative min-w-[34rem]"
              style={{ height: Math.max(bounds.span * pxPerMin, laidOut.bottom) }}
            >
              {/* Hour lines, drawn across both columns so the eye can read along. */}
              {hours.map((m) => (
                <div
                  key={m}
                  className="absolute left-0 right-0 border-t border-bg-border/40"
                  style={{ top: offsetOf(m) }}
                />
              ))}

              {isToday && nowMinutes >= bounds.from && nowMinutes <= bounds.to && (
                <div
                  ref={nowRef}
                  className="absolute left-0 right-0 z-20 pointer-events-none"
                  style={{ top: offsetOf(nowMinutes) }}
                >
                  <div className="h-px bg-danger shadow-[0_0_6px_var(--theme-danger)]" />
                  <div className="absolute -top-2 left-0 text-[9px] font-mono text-danger bg-bg px-1">
                    {day?.now_local}
                  </div>
                </div>
              )}

              {dropAt && (
                <div
                  className="absolute left-0 right-0 z-20 pointer-events-none"
                  style={{ top: offsetOf(toMinutes(dropAt)) }}
                >
                  <div className="h-px bg-matrix" />
                  <div className="absolute -top-2 right-0 text-[9px] font-mono text-matrix bg-bg px-1">
                    {dropAt}
                  </div>
                </div>
              )}

              <div className="relative grid h-full grid-cols-[3.25rem_minmax(8rem,15rem)_minmax(0,1fr)] gap-x-3">
                <div className="relative">
                  {hours.map((m) => (
                    <div
                      key={m}
                      className="absolute right-0 -translate-y-1/2 text-[10px] font-mono text-matrix-dim/70 tabular-nums"
                      style={{ top: offsetOf(m) }}
                    >
                      {toHHMM(m)}
                    </div>
                  ))}
                </div>

                <div className="relative">
                  {blocks.map((b) => {
                    const tone = toneFor(b.label);
                    const height = Math.max(b.minutes * pxPerMin - 2, 10);
                    // What fits. A quarter-hour block at the tighter scale is
                    // twelve pixels tall, which is less than one line of text,
                    // so it becomes a bare band and leans on its tooltip.
                    const tier = height >= 32 ? "full" : height >= 19 ? "label" : "band";
                    const isCurrent = current === b;
                    return (
                      <button
                        key={`${b.start}-${b.label}`}
                        type="button"
                        disabled={busy}
                        onClick={() => toggleBlock(b)}
                        title={
                          `${b.start}–${b.end} · ${b.minutes}m` +
                          (b.done ? " · done, click to undo" : " · click to tick off")
                        }
                        style={{ top: offsetOf(toMinutes(b.start)), height }}
                        className={cn(
                          "group absolute inset-x-0 overflow-hidden rounded-r-sm border-l-2 bg-bg px-2 py-0.5 text-left",
                          tone.bar,
                          isCurrent && "ring-1 ring-matrix/60",
                          b.done && "opacity-40"
                        )}
                      >
                        <span
                          aria-hidden
                          className={cn("absolute inset-0 transition-colors", tone.fill)}
                        />
                        {tier !== "band" && (
                          <div
                            className={cn(
                              "relative truncate",
                              tier === "full"
                                ? "text-[11px] leading-snug"
                                : "text-[10px] leading-none",
                              b.done && "line-through"
                            )}
                          >
                            {b.done ? "☑ " : ""}
                            {b.label}
                          </div>
                        )}
                        {tier === "full" && (
                          <div className="relative text-[9px] font-mono text-matrix-dim/70 tabular-nums">
                            {b.start}–{b.end} · {b.minutes}m
                            {(b.meridiem_corrected || b.shifted) && (
                              <span
                                className="text-warning"
                                title={
                                  b.meridiem_corrected
                                    ? `The sheet says ${b.raw_time}; read as morning to keep the rows in order.`
                                    : "Moved later: the sheet had this overlapping the block before it."
                                }
                              >
                                {" "}
                                ✎
                              </span>
                            )}
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>

                <div
                  ref={laneRef}
                  className={cn(
                    "relative rounded-sm transition-colors",
                    dragging && "bg-matrix/[0.04] outline-dashed outline-1 outline-matrix/25"
                  )}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDropAt(timeAtY(e.clientY));
                  }}
                  onDragLeave={() => setDropAt(null)}
                  onDrop={(e) => drop(timeAtY(e.clientY))}
                >
                  {laidOut.placed.map(({ item, top, nudged }) => {
                    const isOpen = expanded === item.id;
                    return (
                      <div
                        key={item.id}
                        className={cn("absolute inset-x-0", isOpen ? "z-30" : "z-10")}
                        style={{ top }}
                      >
                        <div
                          draggable
                          onDragStart={() => setDragging(item.short_id)}
                          onDragEnd={() => {
                            setDragging(null);
                            setDropAt(null);
                          }}
                          onClick={() => setExpanded(isOpen ? null : item.id)}
                          title={item.title}
                          style={{ height: isOpen ? undefined : ITEM_HEIGHT - ITEM_GAP }}
                          className={cn(
                            "cursor-grab active:cursor-grabbing overflow-hidden rounded border border-matrix/25 border-l-2 bg-bg px-2.5 py-1 text-xs hover:border-matrix/50 transition-colors",
                            SOURCE_TONE[item.source] ?? "border-l-matrix/40",
                            dragging === item.short_id && "opacity-40",
                            item.status === "done" && "opacity-50 line-through",
                            item.overdue_sec > 0 &&
                              item.status === "open" &&
                              "border-danger/50"
                          )}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <span
                              className={cn("min-w-0 leading-snug", !isOpen && "line-clamp-2")}
                            >
                              {item.title}
                            </span>
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
                          <div className="text-[9px] font-mono text-matrix-dim/70 tabular-nums truncate">
                            {item.local_time}
                            {nudged && (
                              <span title="Shown below its slot so it is not hidden behind another card">
                                {" "}
                                ↓
                              </span>
                            )}
                            {item.detail && (
                              <span className="font-sans"> · {item.detail}</span>
                            )}
                          </div>
                        </div>

                        {isOpen && item.status !== "done" && (
                          <div className="mt-1.5 space-y-2 rounded border border-matrix/25 bg-bg p-2.5 shadow-accent-glow">
                            {item.status === "proposed" ? (
                              <div className="flex gap-2">
                                <Button
                                  size="sm"
                                  variant="matrix"
                                  disabled={busy}
                                  onClick={() => act(() => api.approveCommitment(item.short_id))}
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
                                    onClick={() => act(() => api.dropCommitment(item.short_id))}
                                  >
                                    DROP
                                  </Button>
                                </div>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {(day?.items ?? []).length === 0 && (
                    <div className="absolute inset-x-0 top-0 text-[11px] text-matrix-dim/60 px-2">
                      Nothing committed to this day yet.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {corrected.length > 0 && (
        <details className="text-[10px] text-matrix-dim border border-matrix/15 rounded px-4 py-2">
          <summary className="cursor-pointer tracking-wider">
            {corrected.length} row{corrected.length > 1 ? "s" : ""} read differently from
            the sheet
          </summary>
          <ul className="mt-2 space-y-1">
            {corrected.map((b) => (
              <li key={`${b.start}-${b.label}`}>
                <b>{b.label}</b> — sheet says <code>{b.raw_time || "no time"}</code>, drawn{" "}
                {b.start}–{b.end}
                {b.meridiem_corrected && " (AM/PM corrected from the row order)"}
                {b.shifted && " (moved later; it overlapped the block before it)"}
                {b.duration_inferred && " (no duration in the sheet; ran to the next block)"}
              </li>
            ))}
          </ul>
        </details>
      )}

      <p className="text-[10px] text-matrix-dim tracking-wider">
        Blocks are drawn to scale, so height is real time. Click one to tick it off —
        recorded for this date only, never written back to the shared sheet. Cards in the
        right lane are commitments: drag one to move it to the quarter hour you drop it
        on, click to close it with an artifact. Reminders are capped at two per round and
        stay quiet 22:00–07:00.
      </p>
    </div>
  );
}
