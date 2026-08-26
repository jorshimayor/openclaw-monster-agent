"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import type { Commitment } from "@/lib/types";
import { cn } from "@/lib/utils";

function overdueLabel(sec: number): string {
  const mins = Math.floor(sec / 60);
  if (mins < 60) return `${mins}m over`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h over`;
  return `${Math.floor(hours / 24)}d over`;
}

export default function CommitmentsCard() {
  const [items, setItems] = useState<Commitment[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api
        .listCommitments("open")
        .then((rows) => {
          if (cancelled) return;
          setItems(rows);
          setError(null);
        })
        .catch((e: Error) => {
          if (cancelled) return;
          setItems([]);
          setError(e.message);
        });
    load();
    const id = setInterval(load, 10000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const sorted = [...(items ?? [])].sort((a, b) => b.overdue_sec - a.overdue_sec);
  const overdueCount = sorted.filter((c) => c.overdue_sec > 0).length;

  return (
    <Card className={cn(overdueCount > 0 && "border-danger/50")}>
      <CardHeader>
        <CardTitle className="text-sm tracking-widest flex items-center justify-between">
          <span>WHAT YOU OWE</span>
          <Link
            href="/commitments"
            className="text-[10px] font-normal text-matrix hover:underline tracking-widest"
          >
            {items === null
              ? "LOADING…"
              : overdueCount > 0
              ? `${overdueCount} OVERDUE →`
              : `${sorted.length} OPEN →`}
          </Link>
        </CardTitle>
      </CardHeader>
      <CardContent className="py-3 px-2">
        {error && (
          <div className="px-4 py-6 text-xs text-danger">LEDGER UNAVAILABLE · {error}</div>
        )}
        {!error && items !== null && items.length === 0 && (
          <div className="px-4 py-8 text-center text-xs text-matrix-dim">
            NOTHING ON THE HOOK · YOU'RE CLEAR
          </div>
        )}
        <div className="space-y-1">
          {sorted.slice(0, 5).map((c) => (
            <Link
              key={c.id}
              href="/commitments"
              className="block px-4 py-2.5 rounded hover:bg-matrix/5 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="text-sm truncate">{c.title}</div>
                  <div className="text-[10px] text-matrix-dim tracking-wider mt-0.5">
                    <span className="font-mono">{c.short_id}</span>
                    {c.nag_count > 0 && ` · ${c.nag_count} reminders sent`}
                  </div>
                </div>
                <Badge variant={c.overdue_sec > 0 ? "error" : "default"} className="shrink-0">
                  {c.overdue_sec > 0 ? overdueLabel(c.overdue_sec) : "SCHEDULED"}
                </Badge>
              </div>
            </Link>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
