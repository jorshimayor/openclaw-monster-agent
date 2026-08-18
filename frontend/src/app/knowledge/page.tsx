"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { KnowledgeCrystal } from "@/lib/types";
import type { KnowledgeQueryHit } from "@/lib/api";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { RefreshCw, Search, Database, Sparkles } from "lucide-react";

type FilterKey = "all" | KnowledgeCrystal["category"];

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "ALL" },
  { key: "strategies", label: "STRATEGIES" },
  { key: "pitfalls", label: "PITFALLS" },
  { key: "frameworks", label: "FRAMEWORKS" },
  { key: "entities", label: "ENTITIES" }
];

const CAT_VARIANT: Record<
  KnowledgeCrystal["category"],
  "default" | "success" | "warning" | "error"
> = {
  strategies: "success",
  pitfalls: "error",
  frameworks: "warning",
  entities: "default"
};

export default function KnowledgePage() {
  const [filter, setFilter] = useState<FilterKey>("all");
  const [q, setQ] = useState("");
  const [crystals, setCrystals] = useState<KnowledgeCrystal[]>([]);
  const [queryResults, setQueryResults] = useState<KnowledgeQueryHit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [querying, setQuerying] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast((t) => (t === msg ? null : t)), 3200);
  }, []);

  const loadCrystals = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await api.listKnowledge(undefined, 100);
      setCrystals(list);
    } catch (e: any) {
      setError(e?.message || "Failed to load knowledge crystals");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCrystals();
  }, [loadCrystals]);

  const handleQuery = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!q.trim()) {
      setQueryResults(null);
      return;
    }
    setQuerying(true);
    setError(null);
    try {
      const hits = await api.queryKnowledge(q.trim(), 12);
      setQueryResults(hits);
    } catch (e: any) {
      setError(e?.message || "Query failed");
    } finally {
      setQuerying(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setError(null);
    try {
      const res = await api.syncKnowledge();
      showToast(`✓ Sync queued · ${res.queued} crystal(s) will be pushed to Notion`);
    } catch (e: any) {
      setError(e?.message || "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const activeList = queryResults ? queryResults.map((h) => h.crystal) : crystals;

  const filtered = activeList.filter(
    (c) => filter === "all" || c.category === filter
  );

  const scoreFor = (crystalId: string): number | null => {
    if (!queryResults) return null;
    const hit = queryResults.find((h) => h.crystal.id === crystalId);
    return hit ? Number(hit.score) : null;
  };

  return (
    <div className="space-y-6 relative">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-wider glow-text">
            ⟨ CRYSTALLIZED KNOWLEDGE ⟩
          </h1>
          <p className="text-xs text-matrix-dim mt-1 tracking-widest">
            REUSABLE ENTITIES · STRATEGIES · PITFALLS · FRAMEWORKS
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadCrystals}
            disabled={loading}
            className="text-xs tracking-wider"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 mr-2 ${loading ? "animate-spin" : ""}`}
            />
            REFRESH
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleSync}
            disabled={syncing}
            className="text-xs tracking-wider"
          >
            <Database
              className={`w-3.5 h-3.5 mr-2 ${syncing ? "animate-pulse" : ""}`}
            />
            SYNC TO NOTION
          </Button>
        </div>
      </div>

      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-matrix text-bg text-xs font-mono tracking-wider px-4 py-3 rounded shadow-matrix-glow border border-matrix/60 max-w-sm">
          {toast}
        </div>
      )}

      {error && (
        <Card>
          <CardContent className="pt-6 text-red-400 text-xs tracking-wider">
            ERROR: {error}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="pt-6 pb-5 space-y-4">
          <form onSubmit={handleQuery} className="relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-matrix-dim" />
            <input
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                if (!e.target.value) setQueryResults(null);
              }}
              placeholder="Semantic search crystals (e.g. 'reentrancy audit strategies')..."
              className="w-full bg-black/40 border border-matrix/30 rounded pl-11 pr-28 py-2.5 text-sm focus:border-matrix focus:outline-none focus:shadow-matrix-glow placeholder:text-matrix-dim/50"
            />
            <Button
              type="submit"
              size="sm"
              disabled={querying || !q.trim()}
              className="absolute right-1.5 top-1.5 text-xs tracking-wider"
            >
              <Sparkles
                className={`w-3.5 h-3.5 mr-2 ${querying ? "animate-pulse" : ""}`}
              />
              {querying ? "QUERYING" : "QUERY"}
            </Button>
          </form>

          {queryResults && (
            <div className="text-[10px] tracking-widest text-matrix-dim">
              SEMANTIC QUERY RESULTS · {queryResults.length} HIT
              {queryResults.length === 1 ? "" : "S"} · TOP-K=12
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={`text-xs px-3 py-1.5 rounded border tracking-wider transition-colors ${
                  filter === f.key
                    ? "border-matrix bg-matrix/10 text-matrix shadow-matrix-glow"
                    : "border-bg-border text-matrix-dim hover:border-matrix/30 hover:text-matrix"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="space-y-4">
        {loading && filtered.length === 0 && (
          <div className="text-xs text-matrix-dim text-center py-12 animate-pulse">
            LOADING KNOWLEDGE STORE…
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="text-xs text-matrix-dim text-center py-12">
            {queryResults
              ? "NO QUERY HITS MATCH CURRENT FILTER"
              : "NO CRYSTALS IN STORE — RUN A PIPELINE FIRST"}
          </div>
        )}
        {filtered.map((c) => {
          const score = scoreFor(c.id);
          return (
            <Card key={c.id}>
              <CardHeader>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2 mb-3">
                      <Badge variant={CAT_VARIANT[c.category]}>
                        {c.category.toUpperCase()}
                      </Badge>
                      {score !== null && (
                        <Badge
                          variant={
                            score > 0.8
                              ? "success"
                              : score > 0.5
                              ? "default"
                              : "warning"
                          }
                          className="font-mono"
                        >
                          SCORE {(score * 100).toFixed(1)}%
                        </Badge>
                      )}
                    </div>
                    <CardTitle className="text-base tracking-wider glow-text">
                      {c.title}
                    </CardTitle>
                  </div>
                  <div className="text-[10px] text-matrix-dim tracking-widest text-right">
                    <div>ID: {c.id.slice(0, 12)}…</div>
                    <div>{formatDate(c.createdAt)}</div>
                    {c.sourceTaskId && (
                      <div>SRC: {c.sourceTaskId.slice(0, 10)}…</div>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-matrix/90 leading-relaxed bg-black/40 border border-matrix/20 rounded p-4 whitespace-pre-wrap">
                  {c.content}
                </p>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
