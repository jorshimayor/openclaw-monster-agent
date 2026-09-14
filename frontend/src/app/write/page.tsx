"use client";

import { useCallback, useState } from "react";
import { api, type DraftCheck, type DraftFinding } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Check a draft against the editorial standard.
 *
 * Deliberately a checker, not a generator: the writing and the research are
 * yours. Every finding cites the guideline it came from, so it can be confirmed
 * or dismissed rather than argued with. Structure is not graded — it is asked
 * about, because a confident machine verdict on structure would be exactly the
 * unfalsifiable feedback the style guide warns against.
 */

const KINDS = ["article", "outline", "newsletter", "tweet", "video_script"];

const TONE: Record<DraftFinding["severity"], string> = {
  block: "border-danger/50 bg-danger/5",
  warn: "border-warning/40 bg-warning/5",
  note: "border-matrix/25"
};

const BADGE: Record<DraftFinding["severity"], "error" | "warning" | "default"> = {
  block: "error",
  warn: "warning",
  note: "default"
};

export default function WritePage() {
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("article");
  const [result, setResult] = useState<DraftCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");

  const run = useCallback(async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.checkDraft(text, title || undefined, kind));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [text, title, kind]);

  const findings = (result?.findings ?? []).filter(
    (f) => filter === "all" || f.severity === filter
  );

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-wider glow-text">⟨ DRAFT CHECK ⟩</h1>
        <p className="text-xs text-matrix-dim mt-1 tracking-widest">
          YOUR EDITORIAL STANDARD, CHECKED MECHANICALLY · NOT A GENERATOR
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm tracking-widest">THE DRAFT</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-col lg:flex-row gap-3">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="How Does a Hypervisor Allocate Resources?"
              className="flex-1 bg-bg/50 border border-matrix/30 rounded px-3 py-2 text-sm focus:border-matrix focus:outline-none placeholder:text-matrix-dim/50"
            />
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className="lg:w-40 bg-bg/50 border border-matrix/30 rounded px-3 py-2 text-xs tracking-widest focus:border-matrix focus:outline-none"
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {k.replace("_", " ").toUpperCase()}
                </option>
              ))}
            </select>
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste the markdown draft…"
            className="w-full h-72 bg-bg/50 border border-matrix/30 rounded p-3 text-xs font-mono leading-relaxed focus:border-matrix focus:outline-none resize-y placeholder:text-matrix-dim/50"
          />
          <div className="flex items-center gap-3">
            <Button variant="matrix" disabled={busy || !text.trim()} onClick={run}>
              {busy ? "CHECKING…" : "⟶ CHECK AGAINST THE STANDARD"}
            </Button>
            <span className="text-[10px] text-matrix-dim tracking-wider">
              {text.trim() ? `${text.trim().split(/\s+/).length} words` : ""}
            </span>
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="text-xs text-danger border border-danger/40 bg-danger/10 rounded px-4 py-2.5">
          {error}
        </div>
      )}

      {result && (
        <>
          <div
            className={cn(
              "rounded border px-4 py-3 flex flex-wrap items-center gap-x-5 gap-y-2",
              result.passes ? "border-success/50 bg-success/5" : "border-danger/50 bg-danger/5"
            )}
          >
            <span className={cn("text-sm font-bold tracking-wider", result.passes ? "text-success" : "text-danger")}>
              {result.passes ? "✓ PASSES" : "✗ FAILS THE STANDARD"}
            </span>
            <span className="text-xs text-matrix-dim">{result.words} words</span>
            {(["block", "warn", "note"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setFilter(filter === s ? "all" : s)}
                className={cn(
                  "text-[10px] tracking-widest px-2 py-1 rounded border transition-colors",
                  filter === s ? "border-matrix bg-matrix/15" : "border-matrix/25 hover:border-matrix/50"
                )}
              >
                {s.toUpperCase()} · {result.counts[s]}
              </button>
            ))}
          </div>

          {findings.length > 0 && (
            <div className="space-y-2">
              {findings.map((f, i) => (
                <div key={i} className={cn("rounded border px-4 py-2.5", TONE[f.severity])}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant={BADGE[f.severity]}>{f.severity.toUpperCase()}</Badge>
                        <span className="text-xs font-bold">{f.title}</span>
                        <span className="text-[10px] text-matrix-dim">line {f.line}</span>
                      </div>
                      <p className="text-[11px] font-mono text-matrix/85 mt-1.5 break-words">
                        …{f.excerpt}…
                      </p>
                      <p className="text-[11px] text-matrix-dim mt-1">{f.suggestion}</p>
                      <p className="text-[10px] text-matrix-dim/70 mt-1 italic">
                        {f.why} — {f.source}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-sm tracking-widest">
                READ IT AGAIN AND ANSWER THESE
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-[11px] text-matrix-dim mb-3">
                Structure is not graded here. A machine verdict on whether the
                answer is buried would be confident and unfalsifiable — which is
                the failure mode the guide warns about.
              </p>
              <ul className="space-y-2 text-xs text-matrix/90">
                {result.review_questions.map((q, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-matrix-dim shrink-0">{i + 1}.</span>
                    <span>{q}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
