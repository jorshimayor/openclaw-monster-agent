"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import type { KnowledgeCrystal } from "@/lib/types";
import { formatDate, truncate } from "@/lib/utils";

const CAT: Record<
  KnowledgeCrystal["category"],
  "default" | "success" | "warning" | "error"
> = {
  strategies: "success",
  pitfalls: "error",
  frameworks: "warning",
  entities: "default"
};

export default function RecentKnowledgeCard() {
  const [items, setItems] = useState<KnowledgeCrystal[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listKnowledge(undefined, 5)
      .then((rows) => !cancelled && setItems(rows))
      .catch((e: Error) => {
        if (cancelled) return;
        setItems([]);
        setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm tracking-widest flex items-center justify-between">
          <span>CRYSTALLIZED KNOWLEDGE</span>
          <span className="text-[10px] text-matrix-dim font-normal">
            {items === null ? "LOADING…" : `${items.length} RECENT`}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="py-3 px-2">
        {error && (
          <div className="px-4 py-6 text-xs text-danger">
            KNOWLEDGE STORE UNAVAILABLE · {error}
          </div>
        )}
        {!error && items !== null && items.length === 0 && (
          <div className="px-4 py-8 text-center text-xs text-matrix-dim">
            NOTHING CRYSTALLIZED YET · COMPLETE A TASK TO EXTRACT KNOWLEDGE
          </div>
        )}
        <div className="space-y-1">
          {(items ?? []).map((it) => (
            <div
              key={it.id}
              className="px-4 py-3 rounded hover:bg-matrix/5 transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="mb-2">
                    <Badge variant={CAT[it.category]}>
                      {it.category.toUpperCase()}
                    </Badge>
                  </div>
                  <div className="text-sm truncate glow-text" title={it.title}>
                    {truncate(it.title, 70)}
                  </div>
                </div>
                <div className="text-[10px] text-matrix-dim tracking-wider text-right shrink-0">
                  <div>{it.id.slice(0, 8)}</div>
                  <div className="mt-0.5" suppressHydrationWarning>
                    {formatDate(it.createdAt)}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
