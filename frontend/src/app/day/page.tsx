"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  type BlockPlan,
  type DayBlock,
  type DayItem,
  type DayView,
  type PlanItem
} from "@/lib/api";
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
 * The day, drawn to scale — one column, detail on demand.
 *
 * Blocks are positioned and sized by their real start and end, so a quarter
 * hour is a sliver and a ninety-minute block is six times taller.
 *
 * The previous version put commitments in a lane beside the blocks, and wrote
 * each block's plan inside the block. Those two things come from the same
 * place: the rotation files a commitment from a theme, and the same theme's
 * tasks are attached to the block it belongs to. So six of ten cards were a
 * second rendering of text already on screen, in a parallel column, both
 * truncated to fit. That is what made it unreadable.
 *
 * Now there is one column. A commitment belongs to the block its time falls
 * in; where it repeats a line of that block's plan, the commitment wins —
 * it is the trackable one. The row says what the hour is for and how much is
 * in it; opening a block gives the whole of it, links and actions included.
 *
 * Drag-and-drop is the native HTML5 API rather than a library. Blocks are the
 * drop targets: dropping something on a block moves it to that block's start,
 * which is the only time anyone ever actually wants.
 */

/** Pixels per minute. The timeline is this one number times a duration. */
const DENSITY = { compact: 0.85, comfortable: 1.45 } as const;
type Density = keyof typeof DENSITY;

/** Below this the day is one column; above it, two. */
const SPLIT_QUERY = "(min-width: 1120px)";
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

/**
 * What kind of hour this is, by what the sheet calls it. Colour carries the
 * one judgement worth making at a glance: how much of the day is focused work
 * rather than upkeep.
 */
const TONES = [
  {
    match: /deep block|study|reading|anchor|bounty|audit|interview|practice|saa/i,
    bar: "bg-[var(--theme-accent)]",
    tint: "bg-matrix/[0.05] group-hover:bg-matrix/[0.1]",
    dot: "bg-matrix"
  },
  {
    match: /walk|stretch|gym|workout|run|jog|exercise|sleep/i,
    bar: "bg-success",
    tint: "bg-success/[0.05] group-hover:bg-success/[0.1]",
    dot: "bg-success"
  },
  {
    match: /content|writing|open source|portfolio|build|ship|startup/i,
    bar: "bg-warning",
    tint: "bg-warning/[0.05] group-hover:bg-warning/[0.1]",
    dot: "bg-warning"
  }
] as const;

const UPKEEP = {
  bar: "bg-matrix-dim/40",
  tint: "bg-transparent group-hover:bg-matrix/[0.04]",
  dot: "bg-matrix-dim/50"
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

function shiftDate(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

const URL_IN_TEXT = /https?:\/\/[^\s<>"')\]]+/g;

/**
 * Same work, written twice.
 *
 * One side is a task line with its url already split off; the other is the
 * commitment title derived from that same line, url still attached. Comparing
 * the raw text therefore never matches — strip urls from both first, and allow
 * one to be a prefix of the other, because a title is sometimes the task line
 * plus a trailing clause.
 */
function sameWork(a: string, b: string): boolean {
  const n = (s: string) =>
    s.replace(URL_IN_TEXT, " ").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const x = n(a);
  const y = n(b);
  // Short strings collide by accident — "break" is a block label and a task.
  if (x.length < 12 || y.length < 12) return x === y;
  return x === y || x.startsWith(y) || y.startsWith(x);
}

function linksIn(...parts: (string | null | undefined)[]): string[] {
  const found = parts.join(" ").match(URL_IN_TEXT) ?? [];
  return [...new Set(found.map((u) => u.replace(/[.,;)]+$/, "")))];
}

/**
 * Fill in anything an older backend did not send. A Worker deploy goes live
 * well before the container behind it restarts, so for a few minutes the page
 * can be served new while the API is still old.
 */
function normalize(blocks: DayBlock[]): DayBlock[] {
  return blocks.map((b, i) => {
    if (b.end && Number.isFinite(b.minutes)) return { ...b, plan: b.plan ?? [] };
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

/** A block with everything that belongs to it, already deduplicated. */
interface BlockView {
  block: DayBlock;
  items: DayItem[];
  strands: BlockPlan[];
  /** Plan lines plus commitments — what the row's count means. */
  count: number;
}

export default function DayPage() {
  const [date, setDate] = useState<string>("");
  const [todayIso, setTodayIso] = useState<string | null>(null);
  const [day, setDay] = useState<DayView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [density, setDensity] = useState<Density>("comfortable");
  const [columns, setColumns] = useState(1);
  const [dragging, setDragging] = useState<string | null>(null);
  const [dropOn, setDropOn] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [addTime, setAddTime] = useState("");
  const [category, setCategory] = useState("study");
  const [artifact, setArtifact] = useState("");
  const [rejection, setRejection] = useState<string | null>(null);
  const [opened, setOpened] = useState<BlockView | null>(null);
  const nowRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => setDensity(readDensity()), []);

  useEffect(() => {
    const wide = window.matchMedia(SPLIT_QUERY);
    const sync = () => setColumns(wide.matches ? 2 : 1);
    sync();
    wide.addEventListener("change", sync);
    window.addEventListener("resize", sync);
    return () => {
      wide.removeEventListener("change", sync);
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
    const id = setInterval(() => date && load(date), 60000);
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
   * Every block with its commitments folded in, and its plan deduplicated
   * against them. Where the same work appears as both a plan line and a
   * commitment the commitment wins, because that is the one you can close.
   */
  const views = useMemo<BlockView[]>(() => {
    const items = day?.items ?? [];
    return blocks.map((block) => {
      const from = toMinutes(block.start);
      const to = toMinutes(block.end);
      const mine = items.filter((i) => {
        const at = toMinutes(i.local_time);
        return at >= from && at < to;
      });
      const strands = block.plan
        .map((strand) => ({
          ...strand,
          items: strand.items.filter(
            (line) => !mine.some((i) => sameWork(i.title, line.text))
          )
        }))
        .filter((s) => s.items.length > 0 || s.unavailable);
      const planCount = strands.reduce((n, s) => n + s.items.length, 0);
      return { block, items: mine, strands, count: planCount + mine.length };
    });
  }, [blocks, day]);

  /** Commitments whose time falls in no block at all. */
  const orphans = useMemo(() => {
    const claimed = new Set(views.flatMap((v) => v.items.map((i) => i.id)));
    return (day?.items ?? []).filter((i) => !claimed.has(i.id));
  }, [views, day]);

  const bounds = useMemo(() => {
    let from = blocks.length
      ? Math.min(...blocks.map((b) => toMinutes(b.start)))
      : FALLBACK_BOUNDS.from;
    let to = blocks.length
      ? Math.max(...blocks.map((b) => toMinutes(b.end)))
      : FALLBACK_BOUNDS.to;
    if (isToday) {
      from = Math.min(from, nowMinutes);
      to = Math.max(to, nowMinutes + 15);
    }
    from = Math.floor(from / 60) * 60;
    to = Math.ceil(to / 60) * 60;
    return { from, to, span: Math.max(to - from, 60) };
  }, [blocks, isToday, nowMinutes]);

  /** One range per column, split on a block boundary so nothing is cut. */
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

  const panes = useMemo(
    () =>
      ranges.map((range) => {
        const hours: number[] = [];
        for (let m = Math.ceil(range.from / 60) * 60; m <= range.to; m += 60) hours.push(m);
        return {
          range,
          hours,
          views: views.filter((v) => {
            const s = toMinutes(v.block.start);
            return s >= range.from && s < range.to;
          })
        };
      }),
    [ranges, views]
  );

  const paneHeight = useMemo(
    () => Math.max(...ranges.map((r) => (r.to - r.from) * pxPerMin)),
    [ranges, pxPerMin]
  );

  const current = isToday
    ? views.find(
        (v) =>
          nowMinutes >= toMinutes(v.block.start) && nowMinutes < toMinutes(v.block.end)
      )
    : undefined;
  const upNext = isToday
    ? views.find((v) => toMinutes(v.block.start) > nowMinutes)
    : undefined;

  const progress = useMemo(() => {
    const total = blocks.reduce((sum, b) => sum + b.minutes, 0);
    const done = blocks.filter((b) => b.done).reduce((sum, b) => sum + b.minutes, 0);
    return { total, done, pct: total ? Math.round((done / total) * 100) : 0 };
  }, [blocks]);

  const corrected = blocks.filter(
    (b) => b.meridiem_corrected || b.shifted || b.duration_inferred
  );

  useEffect(() => {
    nowRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [day?.date, density, columns]);

  // --- actions ------------------------------------------------------------

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

  const toggleBlock = async (block: DayBlock) => {
    if (!day) return;
    setBusy(true);
    // Optimistic: ticking a block is the fastest interaction on the page.
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

  const drop = async (block: DayBlock) => {
    if (!dragging || !day) return;
    setDropOn(null);
    await act(() => api.moveDayItem(dragging, block.start, day.date));
    setDragging(null);
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

  const closeItem = async (item: DayItem) => {
    setBusy(true);
    setRejection(null);
    try {
      await api.completeCommitment(item.short_id, { artifact_text: artifact });
      setArtifact("");
      await load(day?.date);
      setOpened(null);
    } catch (e) {
      const err = e as ApiError;
      setRejection(err.status === 422 ? err.message : `Could not close: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const proposed = (day?.items ?? []).filter((i) => i.status === "proposed");

  // --- pieces -------------------------------------------------------------

  /** The strand tags on a row: what this hour is for, without the content. */
  const tags = (view: BlockView) => {
    const names = view.strands.map((s) => s.label.split(" · ")[0]);
    for (const i of view.items) {
      const n = i.source.replace(/-/g, " ");
      if (!names.some((x) => x.toLowerCase().startsWith(n.slice(0, 6)))) names.push(n);
    }
    return [...new Set(names)].slice(0, 2);
  };

  const planItemRow = (line: PlanItem, i: number, muted = false) => (
    <li key={i} className={cn("border-l pl-3", muted ? "border-danger/40" : "border-matrix/25")}>
      <p className={cn("text-xs leading-relaxed", muted && "text-danger")}>{line.text}</p>
      {line.url && (
        <a
          href={line.url}
          target="_blank"
          rel="noreferrer"
          className="mt-0.5 inline-block break-all text-[11px] text-matrix underline decoration-matrix/30 underline-offset-2 hover:decoration-matrix"
        >
          {line.url}
        </a>
      )}
    </li>
  );

  const itemCard = (item: DayItem, draggable = false) => {
    const links = linksIn(item.title, item.detail);
    return (
      <div
        key={item.id}
        draggable={draggable}
        onDragStart={draggable ? () => setDragging(item.short_id) : undefined}
        onDragEnd={draggable ? () => { setDragging(null); setDropOn(null); } : undefined}
        className={cn(
          "rounded-md border border-bg-border border-l-2 bg-bg/60 p-3",
          item.status === "done" && "opacity-50",
          item.overdue_sec > 0 && item.status === "open" && "border-l-danger",
          item.status === "proposed" ? "border-l-warning" : "border-l-matrix/50",
          draggable && "cursor-grab active:cursor-grabbing"
        )}
      >
        <div className="flex items-start justify-between gap-2">
          <p className={cn("text-xs leading-relaxed", item.status === "done" && "line-through")}>
            {item.title}
          </p>
          <Badge
            variant={
              item.status === "done"
                ? "success"
                : item.status === "proposed"
                  ? "warning"
                  : "default"
            }
          >
            {item.status.toUpperCase()}
          </Badge>
        </div>
        <p className="mt-1 font-mono text-[10px] text-matrix-dim tabular-nums">
          {item.local_time}
          {item.detail && <span className="font-sans"> · {item.detail}</span>}
        </p>
        {links.map((url) => (
          <a
            key={url}
            href={url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 block break-all text-[11px] text-matrix underline decoration-matrix/30 underline-offset-2 hover:decoration-matrix"
          >
            {url}
          </a>
        ))}

        <div className="mt-2 flex flex-wrap gap-1.5">
          {item.status === "proposed" && (
            <Button
              size="sm"
              variant="matrix"
              disabled={busy}
              onClick={() => act(() => api.approveCommitment(item.short_id))}
            >
              ✓ APPROVE
            </Button>
          )}
          {item.status === "open" && (
            <>
              <Button
                size="sm"
                variant="matrix"
                disabled={busy || !artifact.trim()}
                onClick={() => closeItem(item)}
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
            </>
          )}
          {item.status !== "done" && (
            <Button
              size="sm"
              variant="destructive"
              disabled={busy}
              onClick={() => act(() => api.dropCommitment(item.short_id))}
            >
              DROP
            </Button>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-wider glow-text">⟨ THE DAY ⟩</h1>
          <p className="mt-1 text-xs tracking-widest text-matrix-dim">
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
        <div className="rounded border border-danger/40 bg-danger/10 px-4 py-2.5 text-xs text-danger">
          {error}
        </div>
      )}
      {day?.block_error && (
        <div className="rounded border border-matrix/20 px-4 py-2 text-[11px] text-matrix-dim">
          Your timetable shape isn&apos;t showing: {day.block_error}. Items still work.
        </div>
      )}

      {isToday && (current || upNext) && (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded border border-matrix/30 bg-matrix/[0.04] px-4 py-3">
          {current ? (
            <div className="min-w-0">
              <div className="text-[10px] tracking-widest text-matrix-dim">NOW</div>
              <button
                type="button"
                onClick={() => setOpened(current)}
                className="truncate text-left text-sm hover:text-matrix"
              >
                {current.block.label}
                <span className="text-xs text-matrix-dim">
                  {" "}
                  · {Math.max(0, toMinutes(current.block.end) - nowMinutes)}m left
                </span>
              </button>
            </div>
          ) : (
            <div className="text-xs text-matrix-dim">Nothing scheduled right now.</div>
          )}
          {upNext && (
            <div className="min-w-0">
              <div className="text-[10px] tracking-widest text-matrix-dim">NEXT</div>
              <button
                type="button"
                onClick={() => setOpened(upNext)}
                className="truncate text-left text-sm hover:text-matrix"
              >
                {upNext.block.start} {upNext.block.label}
              </button>
            </div>
          )}
          <div className="ml-auto flex items-center gap-3">
            <div className="h-1.5 w-28 overflow-hidden rounded-full bg-bg-border">
              <div
                className="h-full bg-matrix transition-[width] duration-500"
                style={{ width: `${progress.pct}%` }}
              />
            </div>
            <span className="text-[10px] tracking-wider text-matrix-dim tabular-nums">
              {progress.pct}% · {Math.round(progress.done / 60)}h of{" "}
              {Math.round(progress.total / 60)}h
            </span>
          </div>
        </div>
      )}

      {proposed.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-warning/40 bg-warning/5 px-4 py-2.5">
          <span className="text-xs">
            <b>{proposed.length}</b> waiting on your go-ahead — nothing is chasing you
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
          <form onSubmit={add} className="flex flex-col gap-3 lg:flex-row">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Apply to Zelus Analytics · 2 DSA problems · ship the README"
              className="flex-1 rounded border border-matrix/30 bg-bg/50 px-3 py-2 text-sm placeholder:text-matrix-dim/50 focus:border-matrix focus:outline-none"
            />
            <input
              value={addTime}
              onChange={(e) => setAddTime(e.target.value)}
              placeholder="14:30"
              className="rounded border border-matrix/30 bg-bg/50 px-3 py-2 text-sm placeholder:text-matrix-dim/50 focus:border-matrix focus:outline-none lg:w-28"
            />
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="rounded border border-matrix/30 bg-bg/50 px-3 py-2 text-xs tracking-widest focus:border-matrix focus:outline-none lg:w-32"
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
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-bg-border/60 px-4 py-2.5 text-[10px] tracking-widest text-matrix-dim">
            <span className="text-matrix">TIMETABLE</span>
            <span className="flex items-center gap-1.5">
              <i className="h-2 w-2 rounded-[2px] bg-matrix not-italic" /> FOCUS
            </span>
            <span className="flex items-center gap-1.5">
              <i className="h-2 w-2 rounded-[2px] bg-success not-italic" /> BODY
            </span>
            <span className="flex items-center gap-1.5">
              <i className="h-2 w-2 rounded-[2px] bg-warning not-italic" /> MAKE
            </span>
            <span className="ml-auto tabular-nums">
              {toHHMM(bounds.from)}–{toHHMM(bounds.to)} · CLICK A BLOCK FOR THE DETAIL
            </span>
          </div>

          <div className="px-3 py-4">
            <div
              className={cn(
                "mx-auto grid gap-x-10",
                panes.length === 2
                  ? "max-w-[1500px] grid-cols-2"
                  : "max-w-[760px] grid-cols-1"
              )}
            >
              {panes.map((pane, paneIndex) => {
                const showsNow =
                  isToday && nowMinutes >= pane.range.from && nowMinutes <= pane.range.to;
                const offset = (m: number) => (m - pane.range.from) * pxPerMin;

                return (
                  <div key={paneIndex} className="relative min-w-0" style={{ height: paneHeight }}>
                    {pane.hours.map((m) => (
                      <div
                        key={m}
                        className="absolute left-11 right-0 border-t border-bg-border/30"
                        style={{ top: offset(m) }}
                      />
                    ))}

                    {showsNow && (
                      <div
                        ref={nowRef}
                        className="pointer-events-none absolute left-11 right-0 z-20"
                        style={{ top: offset(nowMinutes) }}
                      >
                        <div className="h-px bg-danger shadow-[0_0_6px_var(--theme-danger)]" />
                        <span className="absolute -top-[7px] -left-11 bg-bg pr-1 font-mono text-[9px] text-danger">
                          {day?.now_local}
                        </span>
                      </div>
                    )}

                    <div className="relative grid h-full grid-cols-[2.75rem_minmax(0,1fr)] gap-x-2">
                      <div className="relative">
                        {pane.hours.map((m) => (
                          <div
                            key={m}
                            className="absolute right-0 -translate-y-1/2 font-mono text-[10px] tabular-nums text-matrix-dim/60"
                            style={{ top: offset(m) }}
                          >
                            {toHHMM(m)}
                          </div>
                        ))}
                      </div>

                      <div className="relative">
                        {pane.views.map((view) => {
                          const b = view.block;
                          const tone = toneFor(b.label);
                          const height = Math.max(b.minutes * pxPerMin - 3, 11);
                          const tier = height >= 42 ? "full" : height >= 22 ? "row" : "band";
                          const isCurrent = current?.block === b;
                          const isTarget = dropOn === b.start;
                          const unavailable = view.strands.some((s) => s.unavailable);

                          return (
                            <div
                              key={`${b.start}-${b.label}`}
                              role="button"
                              tabIndex={0}
                              onClick={() => setOpened(view)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  setOpened(view);
                                }
                              }}
                              onDragOver={(e) => {
                                e.preventDefault();
                                setDropOn(b.start);
                              }}
                              onDragLeave={() =>
                                setDropOn((s) => (s === b.start ? null : s))
                              }
                              onDrop={() => drop(b)}
                              title={`${b.start}–${b.end} · ${b.minutes}m — open for the detail`}
                              style={{ top: offset(toMinutes(b.start)), height }}
                              className={cn(
                                "group absolute inset-x-0 flex cursor-pointer overflow-hidden rounded-md border bg-bg text-left transition-colors",
                                isCurrent
                                  ? "border-matrix/60 ring-1 ring-matrix/30"
                                  : "border-bg-border/60 hover:border-matrix/40",
                                isTarget && "border-matrix ring-1 ring-matrix/50",
                                b.done && "opacity-40"
                              )}
                            >
                              <span
                                aria-hidden
                                className={cn("absolute inset-0 transition-colors", tone.tint)}
                              />
                              <span
                                aria-hidden
                                className={cn("relative w-[3px] shrink-0", tone.bar)}
                              />

                              {tier === "band" ? (
                                <span className="relative flex-1 truncate px-2 text-[9px] leading-[11px] text-matrix-dim">
                                  {b.label}
                                </span>
                              ) : (
                                <div className="relative flex min-w-0 flex-1 items-start gap-2 px-2.5 py-1.5">
                                  <div className="min-w-0 flex-1">
                                    <div
                                      className={cn(
                                        "truncate text-[12.5px] leading-tight",
                                        b.done && "line-through"
                                      )}
                                    >
                                      {b.label}
                                    </div>
                                    {tier === "full" && (
                                      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                                        <span className="font-mono text-[10px] tabular-nums text-matrix-dim/70">
                                          {b.start}–{b.end}
                                        </span>
                                        {tags(view).map((t) => (
                                          <span
                                            key={t}
                                            className="rounded-sm bg-matrix/10 px-1.5 py-px text-[9px] uppercase tracking-wider text-matrix/80"
                                          >
                                            {t}
                                          </span>
                                        ))}
                                        {unavailable && (
                                          <span className="text-[9px] uppercase tracking-wider text-danger">
                                            unavailable
                                          </span>
                                        )}
                                      </div>
                                    )}
                                  </div>

                                  <div className="flex shrink-0 items-center gap-1.5">
                                    {view.count > 0 && (
                                      <span className="rounded-full border border-matrix/30 px-1.5 text-[10px] leading-4 tabular-nums text-matrix/80">
                                        {view.count}
                                      </span>
                                    )}
                                    <span className="font-mono text-[10px] tabular-nums text-matrix-dim/60">
                                      {b.minutes}m
                                    </span>
                                    <button
                                      type="button"
                                      disabled={busy}
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        toggleBlock(b);
                                      }}
                                      aria-label={b.done ? "Mark not done" : "Mark done"}
                                      title={b.done ? "Done — click to undo" : "Tick off"}
                                      className="text-[11px] leading-none text-matrix-dim hover:text-matrix"
                                    >
                                      {b.done ? "☑" : "☐"}
                                    </button>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </CardContent>
      </Card>

      {orphans.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm tracking-widest">
              NOT ON THE TIMETABLE · {orphans.length}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-[11px] text-matrix-dim">
              These fall outside every block. Drag one onto a block to move it there.
            </p>
            <div className="grid gap-2 md:grid-cols-2">
              {orphans.map((i) => itemCard(i, true))}
            </div>
          </CardContent>
        </Card>
      )}

      {/*
        The whole of one block. The row says what the hour is for and how much
        is in it; everything else — the full text, the links, the actions —
        lives here, which is what keeps the row readable.
      */}
      <Dialog
        open={opened !== null}
        onOpenChange={(o) => {
          if (!o) {
            setOpened(null);
            setRejection(null);
            setArtifact("");
          }
        }}
      >
        <DialogContent className="max-w-2xl">
          {opened && (
            <>
              <DialogHeader>
                <DialogTitle className="text-base tracking-wide">
                  {opened.block.label}
                </DialogTitle>
                <p className="font-mono text-[11px] tabular-nums text-matrix-dim">
                  {opened.block.start}–{opened.block.end} · {opened.block.minutes}m
                  {opened.block.meridiem_corrected &&
                    ` · read as morning; the sheet says ${opened.block.raw_time}`}
                  {opened.block.shifted && " · moved later to clear the block before it"}
                </p>
              </DialogHeader>

              <div className="max-h-[58vh] space-y-5 overflow-y-auto pr-1">
                {opened.strands.map((strand, i) => (
                  <div key={i} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <h3 className="text-[11px] uppercase tracking-widest text-matrix">
                        {strand.label}
                      </h3>
                      <Badge variant={strand.unavailable ? "error" : "default"}>
                        {strand.unavailable ? "UNAVAILABLE" : strand.kind.toUpperCase()}
                      </Badge>
                    </div>
                    <ul className="space-y-2">
                      {strand.items.map((line, j) =>
                        planItemRow(line, j, Boolean(strand.unavailable))
                      )}
                    </ul>
                  </div>
                ))}

                {opened.items.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-[11px] uppercase tracking-widest text-matrix">
                      Tracked here · {opened.items.length}
                    </h3>
                    {opened.items.some((i) => i.status === "open") && (
                      <textarea
                        value={artifact}
                        onChange={(e) => setArtifact(e.target.value)}
                        placeholder="Paste the link, or 40+ characters of what you made…"
                        className="h-16 w-full resize-none rounded border border-matrix/30 bg-bg/50 p-2 text-[11px] placeholder:text-matrix-dim/50 focus:border-matrix focus:outline-none"
                      />
                    )}
                    {rejection && (
                      <p className="whitespace-pre-wrap text-[10px] text-danger">{rejection}</p>
                    )}
                    <div className="space-y-2">{opened.items.map((i) => itemCard(i))}</div>
                  </div>
                )}

                {opened.strands.length === 0 && opened.items.length === 0 && (
                  <p className="text-xs text-matrix-dim">
                    Nothing is scheduled against this block — it is yours.
                  </p>
                )}
              </div>

              <div className="flex flex-wrap gap-2 border-t border-bg-border/60 pt-3">
                <Button
                  size="sm"
                  variant={opened.block.done ? "ghost" : "matrix"}
                  disabled={busy}
                  onClick={() => {
                    toggleBlock(opened.block);
                    setOpened({
                      ...opened,
                      block: { ...opened.block, done: !opened.block.done }
                    });
                  }}
                >
                  {opened.block.done ? "↩ NOT DONE" : "✓ TICK OFF"}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setOpened(null)}>
                  BACK
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      {corrected.length > 0 && (
        <details className="rounded border border-matrix/15 px-4 py-2 text-[10px] text-matrix-dim">
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

      <p className="text-[10px] tracking-wider text-matrix-dim">
        Height is real time. A row shows what the hour is for and how much is in it;
        open it for the whole thing — links, commitments and all. The tick marks a block
        done for this date only and is never written back to the shared sheet. Nothing
        here reminds you.
      </p>
    </div>
  );
}
