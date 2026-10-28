"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type Library, type LibraryItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * The shelf: what to read, watch, take and pay for.
 *
 * `/study` answers "what am I doing this morning" — it is the schedule, and it
 * chases you. This answers "where do I go to learn X". Nothing here is tracked
 * or filed, which is the whole reason it can be long without being a burden.
 *
 * Organised by what a thing *is* — a course, a newsletter, an exam — because
 * that is the axis you search on when you want one. The filter searches titles
 * and notes together, so "proxy" finds the RareSkills track by its note rather
 * than only by matching a word in its name.
 */

const SECTION_ICON: Record<string, string> = {
  certifications: "★",
  courses: "▧",
  articles: "✎",
  newsletters: "✉",
  videos: "▶"
};

function matches(item: LibraryItem, needle: string): boolean {
  if (!needle) return true;
  const hay = `${item.title} ${item.note ?? ""} ${item.price ?? ""} ${item.url}`;
  return hay.toLowerCase().includes(needle);
}

export default function LibraryPage() {
  const [shelf, setShelf] = useState<Library | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [only, setOnly] = useState<string | null>(null);

  useEffect(() => {
    api
      .getLibrary()
      .then(setShelf)
      .catch((e) => setError((e as Error).message));
  }, []);

  const needle = query.trim().toLowerCase();

  /** Sections and groups vanish when nothing inside them survives the filter. */
  const sections = useMemo(() => {
    const picked = (shelf?.sections ?? []).filter((s) => !only || s.key === only);
    return picked
      .map((section) => ({
        ...section,
        groups: section.groups
          .map((g) => ({ ...g, items: g.items.filter((i) => matches(i, needle)) }))
          .filter((g) => g.items.length > 0)
      }))
      .filter((s) => s.groups.length > 0);
  }, [shelf, needle, only]);

  const shown = sections.reduce(
    (n, s) => n + s.groups.reduce((m, g) => m + g.items.length, 0),
    0
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-wider glow-text">⟨ THE SHELF ⟩</h1>
          <p className="mt-1 text-xs text-matrix-dim tracking-widest">
            {shelf
              ? `${shelf.total} RESOURCES · ${shelf.sections.length} SECTIONS`
              : "LOADING…"}
          </p>
        </div>
        {shelf?.prices_verified && (
          <p className="text-[10px] text-matrix-dim tracking-wider">
            Exam prices checked {shelf.prices_verified} against the official pages.
            <br />
            They go stale — re-check before paying.
          </p>
        )}
      </div>

      {error && (
        <div className="rounded border border-danger/40 bg-danger/10 px-4 py-2.5 text-xs text-danger">
          {error}
        </div>
      )}

      <Card>
        <CardContent className="flex flex-col gap-3 py-4 lg:flex-row lg:items-center">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search everything — 'proxy', 'aws', 'solana', 'audit'"
            className="flex-1 rounded border border-matrix/30 bg-bg/50 px-3 py-2 text-sm placeholder:text-matrix-dim/50 focus:border-matrix focus:outline-none"
          />
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => setOnly(null)}
              className={cn(
                "rounded border px-2.5 py-1 text-[10px] tracking-widest transition-colors",
                only === null
                  ? "border-matrix bg-matrix/10 text-matrix"
                  : "border-matrix/25 text-matrix-dim hover:border-matrix/50"
              )}
            >
              ALL
            </button>
            {(shelf?.sections ?? []).map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => setOnly(only === s.key ? null : s.key)}
                className={cn(
                  "rounded border px-2.5 py-1 text-[10px] tracking-widest transition-colors",
                  only === s.key
                    ? "border-matrix bg-matrix/10 text-matrix"
                    : "border-matrix/25 text-matrix-dim hover:border-matrix/50"
                )}
              >
                {SECTION_ICON[s.key] ?? "•"} {s.label.toUpperCase()} · {s.count}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {needle && (
        <p className="text-[11px] tracking-wider text-matrix-dim">
          {shown} match{shown === 1 ? "" : "es"} for “{query}”
        </p>
      )}

      {shelf && sections.length === 0 && (
        <p className="py-8 text-center text-xs text-matrix-dim">
          Nothing on the shelf matches that.
        </p>
      )}

      {sections.map((section) => (
        <section key={section.key} className="space-y-3">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-bg-border/60 pb-2">
            <h2 className="text-sm tracking-widest text-matrix">
              {SECTION_ICON[section.key] ?? "•"} {section.label.toUpperCase()}
            </h2>
            <span className="text-[10px] text-matrix-dim tabular-nums">
              {section.count}
            </span>
            {section.blurb && (
              <span className="text-[11px] text-matrix-dim">{section.blurb}</span>
            )}
          </div>

          <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {section.groups.map((group) => (
              <Card key={group.key} className="flex flex-col">
                <CardContent className="space-y-2.5 py-4">
                  <div className="flex items-baseline justify-between gap-2">
                    <h3 className="text-xs tracking-widest text-matrix">
                      {group.label.toUpperCase()}
                    </h3>
                    <span className="text-[10px] text-matrix-dim tabular-nums">
                      {group.items.length}
                    </span>
                  </div>
                  {group.note && (
                    <p className="text-[11px] leading-relaxed text-matrix-dim">
                      {group.note}
                    </p>
                  )}
                  <ul className="space-y-2.5">
                    {group.items.map((item) => (
                      <li
                        key={item.url + item.title}
                        className="border-l border-matrix/20 pl-2.5"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-xs leading-snug underline decoration-matrix/30 underline-offset-2 hover:decoration-matrix"
                          >
                            {item.title}
                          </a>
                          {item.price && (
                            <Badge
                              variant={
                                /free/i.test(item.price) ? "success" : "default"
                              }
                            >
                              {item.price}
                            </Badge>
                          )}
                        </div>
                        {item.note && (
                          <p className="mt-0.5 text-[10px] leading-relaxed text-matrix-dim">
                            {item.note}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      ))}

      <p className="text-[10px] tracking-wider text-matrix-dim">
        Add to any section by editing <code>backend/config/library.json</code> — a
        title and a url are the only required fields. Nothing here is tracked or
        chased: it is a catalogue, not a schedule. What you are doing today lives on
        The Day.
      </p>
    </div>
  );
}
