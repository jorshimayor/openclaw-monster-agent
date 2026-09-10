"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ResourceGroup, type StudyResources } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Everything you study, in one place.
 *
 * The material was scattered across eight Google Sheets, a GitHub account and a
 * separate prep site, so "go and study" meant deciding where to look first.
 * This pulls all of it — every resource tab plus your own repos — into one
 * searchable shelf on the site you already have open.
 */

const SOURCE_LABEL: Record<string, string> = {
  sheet: "SHEET",
  github: "GITHUB",
  curated: "CURATED"
};

/** Group keys share a prefix per subject ("sd-", "ai-", "inv-", "stk-"). */
const AREA_FROM_KEY: { prefix: string; area: string }[] = [
  { prefix: "sd-", area: "System design" },
  { prefix: "ai-", area: "AI engineering" },
  { prefix: "inv-", area: "Investing" },
  { prefix: "stk-", area: "Stocks" },
  { prefix: "fb-", area: "Football" },
  { prefix: "github", area: "Your work" }
];

function areaOf(group: ResourceGroup): string {
  const hit = AREA_FROM_KEY.find((a) => group.key.startsWith(a.prefix));
  return hit?.area ?? "Other";
}

export default function StudyPage() {
  const [data, setData] = useState<StudyResources | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [area, setArea] = useState<string>("all");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const load = useCallback(async (refresh = false) => {
    setBusy(true);
    try {
      setData(await api.studyResources(refresh));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const areas = useMemo(() => {
    const seen = new Map<string, number>();
    for (const g of data?.groups ?? []) {
      const a = areaOf(g);
      seen.set(a, (seen.get(a) ?? 0) + g.items.length);
    }
    return [...seen.entries()].sort((a, b) => b[1] - a[1]);
  }, [data]);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.groups ?? [])
      .filter((g) => area === "all" || areaOf(g) === area)
      .map((g) => ({
        ...g,
        items: q
          ? g.items.filter(
              (i) =>
                i.title.toLowerCase().includes(q) ||
                (i.note ?? "").toLowerCase().includes(q)
            )
          : g.items
      }))
      .filter((g) => g.items.length > 0 || g.error);
  }, [data, query, area]);

  const shown = groups.reduce((n, g) => n + g.items.length, 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-wider glow-text">⟨ STUDY · THE SHELF ⟩</h1>
          <p className="text-xs text-matrix-dim mt-1 tracking-widest">
            {data
              ? `${data.total} RESOURCES · ${data.groups.length} GROUPS${
                  data.cached ? " · CACHED" : ""
                }`
              : "LOADING…"}
          </p>
        </div>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => load(true)}>
          {busy ? "REFRESHING…" : "⟳ REFRESH FROM SHEETS"}
        </Button>
      </div>

      {error && (
        <div className="text-xs text-danger border border-danger/40 bg-danger/10 rounded px-4 py-2.5">
          {error}
        </div>
      )}
      {data && data.failed.length > 0 && (
        <div className="text-[11px] text-warning border border-warning/30 rounded px-4 py-2">
          Some sources didn&apos;t load: {data.failed.join(", ")}. The rest is below.
        </div>
      )}

      <div className="flex flex-col lg:flex-row gap-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search everything — 'kafka', 'rag', 'reentrancy', 'xG'…"
          className="flex-1 bg-bg/50 border border-matrix/30 rounded px-3 py-2 text-sm focus:border-matrix focus:outline-none placeholder:text-matrix-dim/50"
        />
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setArea("all")}
            className={cn(
              "text-[10px] tracking-widest px-2.5 py-1 rounded border transition-colors",
              area === "all"
                ? "border-matrix bg-matrix/15 text-matrix"
                : "border-matrix/25 text-matrix-dim hover:border-matrix/50"
            )}
          >
            ALL
          </button>
          {areas.map(([a, n]) => (
            <button
              key={a}
              type="button"
              onClick={() => setArea(a)}
              className={cn(
                "text-[10px] tracking-widest px-2.5 py-1 rounded border transition-colors",
                area === a
                  ? "border-matrix bg-matrix/15 text-matrix"
                  : "border-matrix/25 text-matrix-dim hover:border-matrix/50"
              )}
            >
              {a.toUpperCase()} · {n}
            </button>
          ))}
        </div>
      </div>

      {query && (
        <p className="text-[11px] text-matrix-dim tracking-wider">
          {shown} match{shown === 1 ? "" : "es"} for “{query}”
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        {groups.map((g) => {
          // A search should show everything it matched, not hide it behind a
          // "show all" the user then has to click on every card.
          const limit = query || expanded[g.key] ? g.items.length : 8;
          return (
            <Card key={g.key}>
              <CardHeader>
                <CardTitle className="text-sm tracking-wider flex items-baseline justify-between gap-2">
                  <span className="min-w-0 truncate">{g.name}</span>
                  <span className="text-[10px] font-normal text-matrix-dim shrink-0">
                    {SOURCE_LABEL[g.source] ?? g.source} · {g.items.length}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {g.error ? (
                  <p className="text-xs text-matrix-dim">unavailable — {g.error}</p>
                ) : (
                  <ul className="space-y-2 text-sm">
                    {g.items.slice(0, limit).map((it, i) => (
                      <li key={`${g.key}-${i}`} className="leading-snug">
                        {it.url ? (
                          <a
                            href={it.url}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="text-matrix hover:underline underline-offset-2"
                          >
                            {it.title}
                          </a>
                        ) : (
                          <span>{it.title}</span>
                        )}
                        {it.meta?.language && (
                          <Badge variant="default" className="ml-2">
                            {it.meta.language}
                          </Badge>
                        )}
                        {it.note && (
                          <span className="block text-[11px] text-matrix-dim mt-0.5">
                            {it.note}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                {!query && g.items.length > 8 && (
                  <button
                    type="button"
                    onClick={() => setExpanded({ ...expanded, [g.key]: !expanded[g.key] })}
                    className="mt-2 text-[10px] uppercase tracking-widest text-matrix-dim hover:text-matrix"
                  >
                    {expanded[g.key] ? "show less" : `show all ${g.items.length}`}
                  </button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {data && groups.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center text-xs text-matrix-dim">
            NOTHING MATCHES · CLEAR THE SEARCH OR PICK ANOTHER AREA
          </CardContent>
        </Card>
      )}

      <p className="text-[10px] text-matrix-dim tracking-wider">
        Pulled live from your study sheets and GitHub. Cached 15 minutes — refresh
        to re-read the sheets after editing one.
      </p>
    </div>
  );
}
