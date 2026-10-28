"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type DayBlock, type DayItem, type DayView } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

/**
 * The day, drawn to scale.
 *
 * Every block is positioned and sized by its real start and end, so a quarter
 * hour is a sliver and a ninety minute deep block is six times taller.
 *
 * Two layers, deliberately distinct. The blocks are your timetable template,
 * read from the sheet: the *shape* of the day. It repeats daily and is not
 * tracked, because turning twenty-one recurring blocks into twenty-one
 * commitments would mean twenty-one things nagging you every morning. Ticking
 * one is recorded for that date only and never written back to the sheet.
 *
 * Commitments — study picks, tasks, reminders, anything you add — sit beside
 * the blocks they fall in. Drag one and it reschedules to where you dropped
 * it, snapped to the quarter hour.
 *
 * Two layout decisions do most of the work here:
 *
 *   - A sixteen hour day at a readable scale is far taller than a screen, so
 *     on a wide one it is split into two columns side by side, the way a
 *     printed timetable is. The seam is placed on a block boundary so nothing
 *     is ever cut in half.
 *   - The commitments lane only exists in a column that has commitments.
 *     Reserving half the width for it permanently left most of the screen as
 *     empty ruled lines on a day with nothing booked.
 *
 * Drag-and-drop is the native HTML5 API rather than a library — one dependency
 * not added, and it degrades to the time field on touch devices.
 */

/** Pixels per minute. The timeline is this one number times a duration. */
const DENSITY = { compact: 0.85, comfortable: 1.45 } as const;
type Density = keyof typeof DENSITY;

const SNAP_MINUTES = 15;
/** A commitment is a point in time, not a span, so every card is this tall. */
const ITEM_HEIGHT = 56;
const ITEM_GAP = 4;
/** Below this the day is one column; above it, two. */
const SPLIT_QUERY = "(min-width: 1280px)";
/**
 * Below this there is no room for a lane beside the blocks: at 375px it
 * squeezed the blocks to a sliver and their labels disappeared. On a phone the
 * commitments go under the timeline as a list instead.
 */
const NARROW_QUERY = "(max-width: 639px)";
/** A day shorter than this is not worth splitting. */
const MIN_SPLIT_MINUTES = 300;
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
 * day is focused work rather than upkeep. Keyword matching rather than a column
 * in the sheet, so adding a row needs no extra bookkeeping.
 */
const TONES = [
  {
    match: /deep block|study|reading|anchor|bounty|audit|interview|practice/i,
    bar: "bg-[var(--theme-accent)]",
    fill: "bg-matrix/[0.08] group-hover:bg-matrix/[0.14]",
    key: "focus"
  },
  {
    match: /walk|stretch|gym|workout|run|jog|exercise|sleep/i,
    bar: "bg-success",
    fill: "bg-success/[0.08] group-hover:bg-success/[0.14]",
    key: "body"
  },
  {
    match: /content|writing|open source|portfolio|build|ship|startup/i,
    bar: "bg-warning",
    fill: "bg-warning/[0.08] group-hover:bg-warning/[0.14]",
    key: "make"
  }
] as const;

const UPKEEP = {
  bar: "bg-matrix-dim/50",
  fill: "bg-bg-panel group-hover:bg-matrix/[0.06]",
  key: "upkeep"
} as const;

const LEGEND = [
  { key: "focus", label: "FOCUS", dot: "bg-matrix" },
  { key: "body", label: "BODY", dot: "bg-success" },
  { key: "make", label: "MAKE", dot: "bg-warning" }
];

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

function shiftDate(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
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
    return { ...b, minutes, end: b.end || toHHMM(start + minutes), plan: b.plan ?? [] };
  });
}

interface PlanLine {
  kind: "head" | "item";
  text: string;
  url?: string | null;
}

/**
 * A block's plan, flattened into the lines a card can draw.
 *
 * The theme's name goes above its work, so a block carrying two strands —
 * the day's rotation and the week's cycled theme — reads as two groups rather
 * than one run-on list. The caller slices this to whatever the block's height
 * allows, which is why it is a flat list and not nested markup.
 */
function planLines(block: DayBlock, withHeads = true): PlanLine[] {
  const out: PlanLine[] = [];
  for (const entry of block.plan ?? []) {
    if (withHeads) out.push({ kind: "head", text: entry.label });
    for (const item of entry.items ?? []) {
      out.push({ kind: "item", text: item.text, url: item.url });
    }
  }
  return out;
}

function readDensity(): Density {
  try {
    return localStorage.getItem("day.density") === "compact" ? "compact" : "comfortable";
  } catch {
    return "comfortable";
  }
}

interface Range {
  from: number;
  to: number;
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
  /** Starts at one so the server and the first client render agree. */
  const [columns, setColumns] = useState(1);
  const [narrow, setNarrow] = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const [dropAt, setDropAt] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [addTime, setAddTime] = useState("");
  const [category, setCategory] = useState("study");
  const [expanded, setExpanded] = useState<string | null>(null);
  /**
   * The block whose full plan is open. A card can only ever show as much as
   * its duration leaves room for, and the long fellowship weeks do not fit —
   * so the card is a preview and this is the whole of it, links and all.
   */
  const [opened, setOpened] = useState<DayBlock | null>(null);
  const [artifact, setArtifact] = useState("");
  const [rejection, setRejection] = useState<string | null>(null);
  const nowRef = useRef<HTMLDivElement | null>(null);
  const laneRefs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => setDensity(readDensity()), []);

  useEffect(() => {
    const wide = window.matchMedia(SPLIT_QUERY);
    const phone = window.matchMedia(NARROW_QUERY);
    const sync = () => {
      setColumns(wide.matches ? 2 : 1);
      setNarrow(phone.matches);
    };
    sync();
    wide.addEventListener("change", sync);
    phone.addEventListener("change", sync);
    // Belt and braces: some environments change the viewport without
    // dispatching the media-query event.
    window.addEventListener("resize", sync);
    return () => {
      wide.removeEventListener("change", sync);
      phone.removeEventListener("change", sync);
      window.removeEventListener("resize", sync);
    };
  }, []);

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
   * The window the timeline covers: the hours the day occupies, rounded out to
   * whole hours, widened to hold any commitment outside the template so
   * nothing is positioned off-canvas.
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

  /**
   * One range per column. The seam goes on the start of the first block past
   * the midpoint, so a column break never lands inside a block.
   */
  const ranges: Range[] = useMemo(() => {
    if (columns === 1 || bounds.span < MIN_SPLIT_MINUTES) {
      return [{ from: bounds.from, to: bounds.to }];
    }
    const midpoint = bounds.from + bounds.span / 2;
    const seam =
      blocks.map((b) => toMinutes(b.start)).find((s) => s >= midpoint) ??
      bounds.from + Math.round(bounds.span / 2 / 60) * 60;
    return [
      { from: bounds.from, to: seam },
      { from: seam, to: bounds.to }
    ];
  }, [columns, bounds, blocks]);

  /** Everything each column needs, already placed. */
  const panes = useMemo(() => {
    return ranges.map((range) => {
      const within = blocks.filter((b) => {
        const s = toMinutes(b.start);
        return s >= range.from && s < range.to;
      });

      // Commitments that would land on top of each other are pushed down
      // rather than squeezed side by side: six narrow columns is six
      // unreadable ones, and the card carries its real time anyway.
      let cursor = -Infinity;
      const placed = (day?.items ?? [])
        .filter((i) => {
          const t = toMinutes(i.local_time);
          return t >= range.from && t < range.to;
        })
        .sort((a, b) => a.local_time.localeCompare(b.local_time))
        .map((item) => {
          const at = (toMinutes(item.local_time) - range.from) * pxPerMin;
          const top = Math.max(at, cursor);
          cursor = top + ITEM_HEIGHT + ITEM_GAP;
          return { item, top, nudged: top > at + 1 };
        });

      const hours: number[] = [];
      for (let m = Math.ceil(range.from / 60) * 60; m <= range.to; m += 60) hours.push(m);

      return {
        range,
        blocks: within,
        placed,
        hours,
        bottom: placed.length ? cursor : 0
      };
    });
  }, [ranges, blocks, day, pxPerMin]);

  const paneHeight = useMemo(
    () =>
      Math.max(
        ...panes.map((p) =>
          Math.max((p.range.to - p.range.from) * pxPerMin, p.bottom)
        )
      ),
    [panes, pxPerMin]
  );

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
  }, [day?.date, density, columns]);

  const timeAtY = (pane: number, clientY: number): string => {
    const rect = laneRefs.current[pane]?.getBoundingClientRect();
    const range = ranges[pane];
    if (!rect || !range) return toHHMM(bounds.from);
    const raw = range.from + (clientY - rect.top) / pxPerMin;
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

  const renderItem = (
    { item, top, nudged }: { item: DayItem; top: number; nudged: boolean },
    positioned = true
  ) => {
    const isOpen = expanded === item.id;
    return (
      <div
        key={item.id}
        className={cn(
          positioned ? "absolute inset-x-0" : "relative",
          isOpen ? "z-30" : "z-10"
        )}
        style={positioned ? { top } : undefined}
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
          style={{
            height: isOpen || !positioned ? undefined : ITEM_HEIGHT - ITEM_GAP
          }}
          className={cn(
            "cursor-grab active:cursor-grabbing overflow-hidden rounded-md border border-bg-border border-l-2 bg-bg px-2.5 py-1.5 text-xs shadow-sm hover:border-matrix/50 transition-colors",
            SOURCE_TONE[item.source] ?? "border-l-matrix/40",
            dragging === item.short_id && "opacity-40",
            item.status === "done" && "opacity-50 line-through",
            item.overdue_sec > 0 && item.status === "open" && "border-danger/50"
          )}
        >
          <div className="flex items-start justify-between gap-2">
            <span
              className={cn("min-w-0 leading-snug", !isOpen && positioned && "line-clamp-2")}
            >
              {item.title}
            </span>
            <span className="flex items-center gap-1.5 shrink-0">
              {item.status === "proposed" && <Badge variant="warning">PROPOSED</Badge>}
              {item.status === "open" && item.nag_count > 0 && (
                <Badge variant={item.nag_count >= 4 ? "error" : "warning"}>
                  {item.nag_count}×
                </Badge>
              )}
              {item.status === "done" && <Badge variant="success">DONE</Badge>}
            </span>
          </div>
          <div className="truncate text-[9px] font-mono text-matrix-dim/70 tabular-nums">
            {item.local_time}
            {nudged && (
              <span title="Shown below its slot so it is not hidden behind another card">
                {" "}
                ↓
              </span>
            )}
            {item.detail && <span className="font-sans"> · {item.detail}</span>}
          </div>
        </div>

        {isOpen && item.status !== "done" && (
          <div className="mt-1.5 space-y-2 rounded-md border border-matrix/25 bg-bg p-2.5 shadow-accent-glow">
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
                    onClick={() => act(() => api.snoozeCommitment(item.short_id, 30))}
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
  };

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
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border border-matrix/30 bg-matrix/[0.04] rounded px-4 py-3">
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
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-bg-border/60 px-4 py-2.5 text-[10px] tracking-widest text-matrix-dim">
            <span className="text-matrix">TIMETABLE</span>
            {LEGEND.map((l) => (
              <span key={l.key} className="flex items-center gap-1.5">
                <i className={cn("h-2 w-2 rounded-[2px] not-italic", l.dot)} />
                {l.label}
              </span>
            ))}
            <span className="ml-auto tabular-nums">
              {toHHMM(bounds.from)}–{toHHMM(bounds.to)} · {blocks.length} BLOCKS
            </span>
          </div>

          <div className="px-3 py-4">
            <div
              className={cn(
                "mx-auto grid gap-x-8",
                panes.length === 2 ? "grid-cols-2 max-w-[1600px]" : "max-w-[900px] grid-cols-1"
              )}
            >
              {panes.map((pane, paneIndex) => {
                const showsNow =
                  isToday &&
                  nowMinutes >= pane.range.from &&
                  nowMinutes <= pane.range.to;
                const offset = (m: number) => (m - pane.range.from) * pxPerMin;
                const hasItems = !narrow && pane.placed.length > 0;

                return (
                  <div
                    key={paneIndex}
                    className="relative min-w-0"
                    style={{ height: paneHeight }}
                  >
                    {/* Hour rules, behind everything, stopping at the column edge. */}
                    {pane.hours.map((m) => (
                      <div
                        key={m}
                        className="absolute left-10 right-0 border-t border-bg-border/35"
                        style={{ top: offset(m) }}
                      />
                    ))}

                    {showsNow && (
                      <div
                        ref={nowRef}
                        className="absolute left-10 right-0 z-20 pointer-events-none"
                        style={{ top: offset(nowMinutes) }}
                      >
                        <div className="h-px bg-danger shadow-[0_0_6px_var(--theme-danger)]" />
                        <span className="absolute -top-[7px] -left-10 text-[9px] font-mono text-danger bg-bg pr-1">
                          {day?.now_local}
                        </span>
                      </div>
                    )}

                    {dropAt &&
                      toMinutes(dropAt) >= pane.range.from &&
                      toMinutes(dropAt) <= pane.range.to && (
                        <div
                          className="absolute left-10 right-0 z-20 pointer-events-none"
                          style={{ top: offset(toMinutes(dropAt)) }}
                        >
                          <div className="h-px bg-matrix" />
                          <span className="absolute -top-[7px] right-0 text-[9px] font-mono text-matrix bg-bg px-1">
                            {dropAt}
                          </span>
                        </div>
                      )}

                    <div
                      className={cn(
                        "relative grid h-full gap-x-3",
                        hasItems
                          ? "grid-cols-[2.5rem_minmax(0,1fr)_minmax(0,17rem)]"
                          : "grid-cols-[2.5rem_minmax(0,1fr)]"
                      )}
                    >
                      <div className="relative">
                        {pane.hours.map((m) => (
                          <div
                            key={m}
                            className="absolute right-1 -translate-y-1/2 text-[10px] font-mono text-matrix-dim/60 tabular-nums"
                            style={{ top: offset(m) }}
                          >
                            {toHHMM(m)}
                          </div>
                        ))}
                      </div>

                      {/*
                        The blocks column doubles as the drop target. Dropping
                        onto the time you are looking at is the obvious
                        gesture, and it works whether or not this column
                        currently has a commitments lane.
                      */}
                      <div
                        ref={(el) => {
                          laneRefs.current[paneIndex] = el;
                        }}
                        className={cn(
                          "relative rounded transition-colors",
                          dragging && "bg-matrix/[0.04] outline-dashed outline-1 outline-matrix/25"
                        )}
                        onDragOver={(e) => {
                          e.preventDefault();
                          setDropAt(timeAtY(paneIndex, e.clientY));
                        }}
                        onDragLeave={() => setDropAt(null)}
                        onDrop={(e) => drop(timeAtY(paneIndex, e.clientY))}
                      >
                        {pane.blocks.map((b) => {
                          const tone = toneFor(b.label);
                          const height = Math.max(b.minutes * pxPerMin - 3, 10);
                          // What fits. A quarter hour at the tighter scale is
                          // thirteen pixels, less than one line of text, so it
                          // becomes a bare band and leans on its tooltip.
                          const tier =
                            height >= 40 ? "full" : height >= 20 ? "row" : "band";
                          const isCurrent = current === b;
                          // The plan lines carry links, and an anchor cannot
                          // live inside a button — so the block is a div and
                          // only its header row toggles done.
                          let lines = planLines(b);
                          // A half-hour block is 43px: a label, a time and
                          // nothing else. Book Reading is exactly that, and
                          // what to read is the whole point of it — so when
                          // the choice is the clock or the work, the clock
                          // goes. It is still in the tooltip and the gutter.
                          let room = Math.max(0, Math.floor((height - 34) / 14));
                          const showTime = lines.length === 0 || room > 0;
                          if (!showTime) room = Math.max(0, Math.floor((height - 21) / 14));
                          // Headings name the strand; items are the work. When
                          // the two will not both fit, the heading goes — a
                          // block reading only "FELLOWSHIP WEEK 6 · PAPER",
                          // with the paper itself cut, says nothing at all.
                          if (room < lines.length) lines = planLines(b, false);
                          const shown = lines.slice(0, room);
                          const hidden = lines.length - shown.length;
                          return (
                            <div
                              key={`${b.start}-${b.label}`}
                              role="button"
                              tabIndex={0}
                              onClick={() => setOpened(b)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  setOpened(b);
                                }
                              }}
                              title={`${b.start}–${b.end} · ${b.minutes}m · open the full plan`}
                              style={{ top: offset(toMinutes(b.start)), height }}
                              className={cn(
                                "group absolute inset-x-0 flex cursor-pointer overflow-hidden rounded-md border border-bg-border/70 bg-bg text-left transition-colors hover:border-matrix/50",
                                isCurrent && "border-matrix/60 ring-1 ring-matrix/40",
                                b.done && "opacity-40"
                              )}
                            >
                              <span
                                aria-hidden
                                className={cn("absolute inset-0 transition-colors", tone.fill)}
                              />
                              <span
                                aria-hidden
                                className={cn("relative w-[3px] shrink-0 rounded-l", tone.bar)}
                              />
                              {tier !== "band" && (
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    toggleBlock(b);
                                  }}
                                  title={b.done ? "Done — click to undo" : "Tick this block off"}
                                  aria-label={b.done ? "Mark not done" : "Mark done"}
                                  className="relative z-10 shrink-0 self-start px-1.5 pt-1.5 text-[11px] leading-none text-matrix-dim hover:text-matrix"
                                >
                                  {b.done ? "☑" : "☐"}
                                </button>
                              )}
                              <div className="relative min-w-0 flex-1">
                                <div
                                  className={cn(
                                    "block w-full text-left",
                                    tier === "band"
                                      ? "px-2"
                                      : tier === "row"
                                        ? "px-2.5 py-[3px]"
                                        : "px-2.5 pt-1.5"
                                  )}
                                >
                                  {tier === "band" ? (
                                    <span className="block truncate text-[9px] leading-[10px] text-matrix-dim">
                                      {b.label}
                                    </span>
                                  ) : tier === "row" ? (
                                    <span className="flex items-center justify-between gap-2">
                                      <span
                                        className={cn(
                                          "truncate text-[11px]",
                                          b.done && "line-through"
                                        )}
                                      >
                                        {b.label}
                                      </span>
                                      <span className="shrink-0 text-[9px] font-mono text-matrix-dim/70 tabular-nums">
                                        {b.minutes}m
                                      </span>
                                    </span>
                                  ) : (
                                    <>
                                      <span
                                        className={cn(
                                          "block truncate text-[12px] leading-snug",
                                          b.done && "line-through"
                                        )}
                                      >
                                        {b.label}
                                      </span>
                                      <span
                                        className={cn(
                                          "block text-[10px] font-mono text-matrix-dim/70 tabular-nums",
                                          !showTime && "hidden"
                                        )}
                                      >
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
                                      </span>
                                    </>
                                  )}
                                </div>

                                {tier === "full" && shown.length > 0 && (
                                  <div className="mt-1 space-y-[1px] px-2.5 pb-1">
                                    {shown.map((line, i) =>
                                      line.kind === "head" ? (
                                        <div
                                          key={i}
                                          className="truncate text-[9px] uppercase tracking-wider text-matrix/70"
                                        >
                                          {line.text}
                                        </div>
                                      ) : (
                                        <div key={i} className="truncate text-[10px] leading-[13px]">
                                          <span className="text-matrix-dim/50">· </span>
                                          {line.url ? (
                                            <a
                                              href={line.url}
                                              target="_blank"
                                              rel="noreferrer"
                                              onClick={(e) => e.stopPropagation()}
                                              title={`${line.text} — ${line.url}`}
                                              className="underline decoration-matrix/30 underline-offset-2 hover:decoration-matrix"
                                            >
                                              {line.text}
                                            </a>
                                          ) : (
                                            <span title={line.text}>{line.text}</span>
                                          )}
                                        </div>
                                      )
                                    )}
                                    {hidden > 0 && room >= 2 && (
                                      <div className="text-[9px] text-matrix-dim/60">
                                        +{hidden} more
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      {hasItems && (
                        <div className="relative">
                          {pane.placed.map((placement) => renderItem(placement))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {narrow && (day?.items ?? []).length > 0 && (
              <div className="mt-5 border-t border-bg-border/60 pt-4">
                <div className="mb-2 text-[10px] tracking-widest text-matrix-dim">
                  COMMITMENTS · {(day?.items ?? []).length}
                </div>
                <div className="space-y-1.5">
                  {panes
                    .flatMap((p) => p.placed)
                    .map((placement) => renderItem(placement, false))}
                </div>
              </div>
            )}

            {(day?.items ?? []).length === 0 && (
              <p className="mt-4 text-center text-[11px] text-matrix-dim/60">
                Nothing committed to this day yet — the shape above is your template.
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/*
        The whole plan, untruncated. A card can only show what its duration
        leaves room for — a ninety-minute fellowship week has six lines and
        fits five — so everything is reachable here, links included.
      */}
      <Dialog open={opened !== null} onOpenChange={(o) => !o && setOpened(null)}>
        <DialogContent className="max-w-2xl">
          {opened && (
            <>
              <DialogHeader>
                <DialogTitle className="text-base tracking-wider">
                  {opened.label}
                </DialogTitle>
                <p className="text-[11px] font-mono text-matrix-dim tabular-nums">
                  {opened.start}–{opened.end} · {opened.minutes}m
                  {opened.meridiem_corrected &&
                    ` · read as morning; the sheet says ${opened.raw_time}`}
                  {opened.shifted && " · moved later to clear the block before it"}
                </p>
              </DialogHeader>

              <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-1">
                {(opened.plan ?? []).length === 0 && (
                  <p className="text-xs text-matrix-dim">
                    Nothing is scheduled against this block — it is yours.
                  </p>
                )}
                {(opened.plan ?? []).map((entry, i) => (
                  <div key={i} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <h3 className="text-[11px] uppercase tracking-widest text-matrix">
                        {entry.label}
                      </h3>
                      <Badge variant={entry.unavailable ? "error" : "default"}>
                        {entry.unavailable ? "UNAVAILABLE" : entry.kind.toUpperCase()}
                      </Badge>
                    </div>
                    <ul className="space-y-2">
                      {entry.items.map((item, j) => (
                        <li
                          key={j}
                          className={cn(
                            "border-l pl-3",
                            entry.unavailable ? "border-danger/40" : "border-matrix/25"
                          )}
                        >
                          <p
                            className={cn(
                              "text-xs leading-relaxed",
                              entry.unavailable && "text-danger"
                            )}
                          >
                            {item.text}
                          </p>
                          {item.url && (
                            <a
                              href={item.url}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-1 inline-block break-all text-[11px] text-matrix underline decoration-matrix/30 underline-offset-2 hover:decoration-matrix"
                            >
                              {item.url}
                            </a>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap gap-2 border-t border-bg-border/60 pt-3">
                <Button
                  size="sm"
                  variant={opened.done ? "ghost" : "matrix"}
                  disabled={busy}
                  onClick={() => {
                    toggleBlock(opened);
                    setOpened({ ...opened, done: !opened.done });
                  }}
                >
                  {opened.done ? "↩ NOT DONE" : "✓ TICK OFF"}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setOpened(null)}>
                  CLOSE
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

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
        recorded for this date only, never written back to the shared sheet. Commitments
        sit beside the block they fall in: drag one onto the timeline to move it to the
        quarter hour you drop it on, click to close it with an artifact. Reminders are
        capped at two per round and stay quiet 22:00–07:00.
      </p>
    </div>
  );
}
