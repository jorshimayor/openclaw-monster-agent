"use client";

/**
 * Career HQ — the one place: today's marching orders, the writing ledger,
 * the 41-week season calendar, the senior-SWE study guide (synced from the
 * OnchainSuite infra handbook), and the resource shelf.
 *
 * Privacy model: this page is a contentless shell. Everything sensitive
 * (calendars, study guide) is fetched from fieldtilt's key-gated /api/plan
 * (Neon-backed, never bundled). Paste the admin key once per device.
 */

import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Markdown from "@/components/Markdown";
import {
  BookOpen,
  CalendarDays,
  ExternalLink,
  Flame,
  KeyRound,
  PenLine,
  Target
} from "lucide-react";

const PLAN_API = "https://fieldtilt.joelobafemii.workers.dev/api/plan";

type LedgerWeek = { week: number; date: string; deep: string; fast: string; ship: string };
type Plan = {
  season: { header: string[]; rows: string[][]; syncedAt?: string } | null;
  ledger: { start: string; weeks: LedgerWeek[]; syncedAt?: string } | null;
  study: { sections: { num: number; title: string; body: string }[]; syncedAt?: string } | null;
};

const DAY_REPS: Record<number, string[]> = {
  1: ["2 DSA problems, timed, out loud", "Review the model call: what did it miss?"],
  2: ["1 system-design narration (35 min, whiteboard)", "Publish model scoring post"],
  3: ["2 DSA problems", "1 hour contest / bounty work"],
  4: ["STAR bank practice mode: 3 stories aloud", "Send 2 applications"],
  5: ["Publish the model call", "1 hour bounty work", "Send 2 applications"],
  6: ["Match-day content runs itself", "Draft the week's thread"],
  0: ["Rest, or finish the week's thread", "Prep Monday's writing slot"]
};

const PROPERTIES = [
  { label: "fieldtilt dashboard", href: "https://fieldtilt.joelobafemii.workers.dev/" },
  { label: "public terminal", href: "https://fieldtilt.joelobafemii.workers.dev/terminal" },
  { label: "prep masterclass", href: "https://fieldtilt.joelobafemii.workers.dev/prep" },
  { label: "infra handbook", href: "https://onchainsuite-infra-handbook.onchainsuite.workers.dev/" },
  { label: "github", href: "https://github.com/jorshimayor" }
];

type Tab = "today" | "timetable" | "study" | "resources";

const RESOURCES: { group: string; items: [string, string, string][] }[] = [
  {
    group: "web3 security depth",
    items: [
      ["RareSkills Solidity", "https://rareskills.io/learn-solidity", "the rigorous track, in order"],
      ["Proxy patterns", "https://rareskills.io/proxy-patterns", "pairs with the OZ function-clashing exploit"],
      ["ZK book", "https://rareskills.io/zk-book", "one chapter/week in the ZK phase"],
      ["Uniswap V3 book", "https://rareskills.io/uniswap-v3-book", "each chapter is an article seed"],
      ["Damn Vulnerable DeFi", "https://www.damnvulnerabledefi.xyz/", "publish every solve"],
      ["rekt.news", "https://rekt.news/", "one post-mortem retold per week"],
      ["Solodit", "https://solodit.cyfrin.io/", "one audit report per day in contest ramp"]
    ]
  },
  {
    group: "systems + interviews",
    items: [
      ["Hello Interview: in a hurry", "https://www.hellointerview.com/learn/system-design/in-a-hurry/introduction", "the grading rubric — read first"],
      ["Mixu: distributed systems", "http://book.mixu.net/distsys/single-page.html", "one sitting, publish the notes"],
      ["Teach Yourself CS", "https://teachyourselfcs.com/", "one book per area, ignore the rest"],
      ["DSA patterns sheet", "https://thita.ai/dsa-patterns-sheet", "pattern-first, with NeetCode 75"],
      ["Postgres book", "https://pgbook.dev/", "you run Neon in prod — formalize it"]
    ]
  },
  {
    group: "ai + agents",
    items: [
      ["CMU agents course", "https://www.cmu-agents.com/#/", "academic grounding for what you ship"],
      ["DeepLearning.AI shorts", "https://learn.deeplearning.ai/", "agents + evals courses first"],
      ["Stanford CS329Z", "https://cs329z.stanford.edu/", "the readings list is the gold"]
    ]
  }
];

function useLocal<T>(key: string, initial: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(initial);
  useEffect(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw) setV(JSON.parse(raw));
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const set = (nv: T) => {
    setV(nv);
    try {
      localStorage.setItem(key, JSON.stringify(nv));
    } catch {}
  };
  return [v, set];
}

export default function HqPage() {
  const [key, setKey] = useState<string>("");
  const [keyInput, setKeyInput] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [err, setErr] = useState<string>("");
  const [tab, setTab] = useState<Tab>("today");
  const [studyIdx, setStudyIdx] = useState(0);
  const [done, setDone] = useLocal<Record<string, boolean>>("hq-ledger-done", {});

  useEffect(() => {
    try {
      const k = localStorage.getItem("fieldtiltKey") || "";
      setKey(k);
    } catch {}
  }, []);

  useEffect(() => {
    if (!key) return;
    setErr("");
    fetch(PLAN_API, { headers: { Authorization: `Bearer ${key}` } })
      .then((r) => {
        if (r.status === 401 || r.status === 403) throw new Error("bad-key");
        return r.json();
      })
      .then((d) => (d.error ? setErr(d.error) : setPlan(d)))
      .catch((e) =>
        setErr(e.message === "bad-key" ? "Key rejected — paste the current fieldtilt admin key." : `Could not reach the plan API: ${e.message}`)
      );
  }, [key]);

  const ledgerCur = useMemo(() => {
    if (!plan?.ledger) return -1;
    const raw = Math.floor((Date.now() - new Date(plan.ledger.start + "T00:00:00Z").getTime()) / (7 * 864e5));
    return Math.max(0, Math.min(raw, plan.ledger.weeks.length - 1));
  }, [plan]);

  const seasonCur = useMemo(() => {
    if (!plan?.season) return -1;
    const now = Date.now();
    return plan.season.rows.findIndex((r) => {
      const t = Date.parse(r[1]);
      return Number.isFinite(t) && now >= t && now < t + 7 * 864e5;
    });
  }, [plan]);

  const publishedCount = Object.values(done).filter(Boolean).length;

  if (!key) {
    return (
      <div className="mx-auto max-w-lg pt-16">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="h-4 w-4" /> Career HQ is locked
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-[var(--theme-text-dim)]">
              This page holds the private season plan, writing ledger and study guide. Paste the fieldtilt admin key once — it stays on this device.
            </p>
            <input
              type="password"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder="fieldtilt admin key (CRON_SECRET)"
              className="w-full rounded border border-[var(--theme-bg-border)] bg-[var(--theme-bg)] px-3 py-2 font-mono text-sm"
            />
            <Button
              onClick={() => {
                try {
                  localStorage.setItem("fieldtiltKey", keyInput.trim());
                } catch {}
                setKey(keyInput.trim());
              }}
            >
              Unlock
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const week = plan?.ledger?.weeks?.[ledgerCur];
  const seasonRow = seasonCur >= 0 ? plan?.season?.rows[seasonCur] : undefined;

  return (
    <div className="space-y-6">
      {/* hero */}
      <div className="rounded-lg border border-[var(--theme-bg-border)] bg-[var(--theme-bg-panel)] p-6">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--theme-accent)]">
              career_hq · jorshimayor
            </p>
            <h1 className="mt-1 text-2xl font-bold">
              African finance rails × football intelligence × production agents
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-[var(--theme-text-dim)]">
              One place: what to study, write, post and ship — every day of the season. {publishedCount > 0 && `${publishedCount} pieces published so far.`}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {PROPERTIES.map((p) => (
              <a key={p.href} href={p.href} target="_blank" rel="noreferrer noopener">
                <Badge variant="default" className="cursor-pointer">
                  {p.label} <ExternalLink className="ml-1 h-3 w-3" />
                </Badge>
              </a>
            ))}
          </div>
        </div>
      </div>

      {err && <p className="font-mono text-sm text-[var(--theme-danger)]">❯ {err}</p>}

      {/* tabs */}
      <div className="flex flex-wrap gap-2">
        {(
          [
            ["today", "Today", Flame],
            ["timetable", "Timetable", CalendarDays],
            ["study", "Study guide", BookOpen],
            ["resources", "Resources", Target]
          ] as [Tab, string, typeof Flame][]
        ).map(([t, label, Icon]) => (
          <Button key={t} variant={tab === t ? "default" : "outline"} size="sm" onClick={() => setTab(t)}>
            <Icon className="mr-1 h-3.5 w-3.5" /> {label}
          </Button>
        ))}
      </div>

      {/* TODAY */}
      {tab === "today" && (
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Today&apos;s reps</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 text-sm text-[var(--theme-text-dim)]">
                {(DAY_REPS[new Date().getDay()] || []).map((r) => (
                  <li key={r} className="flex gap-2">
                    <span className="text-[var(--theme-accent)]">❯</span> {r}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <PenLine className="h-4 w-4" /> This week&apos;s writing {week && <Badge variant="success">W{week.week}</Badge>}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {week ? (
                (["deep", "fast", "ship"] as const).map((slot) => (
                  <label key={slot} className="flex cursor-pointer items-start gap-2">
                    <input
                      type="checkbox"
                      checked={!!done[`${ledgerCur}:${slot}`]}
                      onChange={(e) => setDone({ ...done, [`${ledgerCur}:${slot}`]: e.target.checked })}
                      className="mt-1 accent-[var(--theme-success)]"
                    />
                    <span className={done[`${ledgerCur}:${slot}`] ? "text-[var(--theme-text-dim)] line-through" : ""}>
                      <span className="font-mono text-[10px] uppercase text-[var(--theme-accent)]">{slot}</span>{" "}
                      {week[slot]}
                    </span>
                  </label>
                ))
              ) : (
                <p className="text-[var(--theme-text-dim)]">Loading the ledger…</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Season week — BUILD is law</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-[var(--theme-text-dim)]">
              {seasonRow ? (
                <>
                  <p className="font-mono text-[10px] uppercase text-[var(--theme-accent)]">
                    week {seasonRow[0]} · {seasonRow[2]}
                  </p>
                  <p className="mt-2 text-[var(--theme-text)]">{seasonRow[4]}</p>
                  <p className="mt-2">Post: {seasonRow[5]}</p>
                </>
              ) : (
                <p>Loading the season calendar…</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* TIMETABLE */}
      {tab === "timetable" && plan && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Writing ledger — 16 weeks, 3 pieces each</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {plan.ledger?.weeks.map((w, wi) => (
                <div
                  key={w.week}
                  className={`rounded border p-3 ${
                    wi === ledgerCur
                      ? "border-[var(--theme-accent)]"
                      : "border-[var(--theme-bg-border)] " + (wi < ledgerCur ? "opacity-50" : "")
                  }`}
                >
                  <p className="font-mono text-[11px] uppercase tracking-wider">
                    <span className="text-[var(--theme-accent)]">W{String(w.week).padStart(2, "0")}</span>
                    <span className="text-[var(--theme-text-dim)]"> · wk of {w.date}</span>
                    {wi === ledgerCur && <span className="text-[var(--theme-success)]"> ← now</span>}
                  </p>
                  {(["deep", "fast", "ship"] as const).map((slot) => (
                    <label key={slot} className="mt-1 flex cursor-pointer items-start gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={!!done[`${wi}:${slot}`]}
                        onChange={(e) => setDone({ ...done, [`${wi}:${slot}`]: e.target.checked })}
                        className="mt-1 accent-[var(--theme-success)]"
                      />
                      <span className={done[`${wi}:${slot}`] ? "text-[var(--theme-text-dim)] line-through" : "text-[var(--theme-text-dim)]"}>
                        <span className="font-mono text-[10px] uppercase text-[var(--theme-accent)]">{slot}</span> {w[slot]}
                      </span>
                    </label>
                  ))}
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Season calendar — 41 weeks</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1000px] border-collapse text-xs">
                  <thead>
                    <tr>
                      {plan.season?.header.map((h) => (
                        <th key={h} className="border-b border-[var(--theme-bg-border)] p-2 text-left font-mono text-[10px] uppercase text-[var(--theme-text-dim)]">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {plan.season?.rows.map((r, i) => (
                      <tr
                        key={r[0]}
                        className={
                          i === seasonCur
                            ? "bg-[var(--theme-accent)]/10"
                            : (r[r.length - 1] || "").includes("✅")
                              ? "opacity-50"
                              : ""
                        }
                      >
                        {r.map((c, ci) => (
                          <td key={ci} className={`border-t border-[var(--theme-bg-border)] p-2 align-top ${ci === 4 ? "text-[var(--theme-text)]" : "text-[var(--theme-text-dim)]"}`}>
                            {c}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* STUDY */}
      {tab === "study" && (
        <div className="grid gap-4 md:grid-cols-[280px_1fr]">
          <Card className="md:sticky md:top-4 md:self-start">
            <CardHeader>
              <CardTitle className="text-sm">
                Study guide {plan?.study && <Badge>{plan.study.sections.length} sections</Badge>}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="max-h-[60vh] space-y-1 overflow-y-auto">
                {plan?.study?.sections.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => setStudyIdx(i)}
                    className={`block w-full rounded px-2 py-1 text-left text-xs ${
                      i === studyIdx
                        ? "bg-[var(--theme-accent)]/15 text-[var(--theme-text)]"
                        : "text-[var(--theme-text-dim)] hover:text-[var(--theme-text)]"
                    }`}
                  >
                    <span className="font-mono text-[var(--theme-accent)]">{s.num >= 0 ? s.num : "·"}</span> {s.title}
                  </button>
                )) || <p className="text-xs text-[var(--theme-text-dim)]">Loading…</p>}
              </div>
              <p className="mt-3 font-mono text-[10px] text-[var(--theme-text-dim)]">
                source: onchainsuite infra handbook · synced {plan?.study?.syncedAt?.slice(0, 10)}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              {plan?.study?.sections[studyIdx] ? (
                <Markdown source={plan.study.sections[studyIdx].body} />
              ) : (
                <p className="text-sm text-[var(--theme-text-dim)]">Pick a section.</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* RESOURCES */}
      {tab === "resources" && (
        <div className="grid gap-4 md:grid-cols-3">
          {RESOURCES.map((g) => (
            <Card key={g.group}>
              <CardHeader>
                <CardTitle className="text-sm uppercase tracking-wider">{g.group}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  {g.items.map(([name, href, note]) => (
                    <li key={href}>
                      <a href={href} target="_blank" rel="noreferrer noopener" className="text-[var(--theme-accent)] hover:underline">
                        {name}
                      </a>
                      <span className="text-[var(--theme-text-dim)]"> — {note}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
          <Card className="md:col-span-3">
            <CardContent className="pt-6 text-sm text-[var(--theme-text-dim)]">
              The full 40+ resource library with progress tracking lives on{" "}
              <a className="text-[var(--theme-accent)] hover:underline" href="https://fieldtilt.joelobafemii.workers.dev/prep" target="_blank" rel="noreferrer noopener">
                the prep masterclass
              </a>
              . This shelf is the working subset.
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
