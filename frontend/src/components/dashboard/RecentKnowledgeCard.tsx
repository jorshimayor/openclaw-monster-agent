import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";
import { useIsHydrated } from "@/lib/hydration";

const BASE_DATE = new Date("2026-08-16T19:28:38.000Z").getTime();

const ITEMS = [
  {
    id: "kc_001",
    category: "strategies" as const,
    title: "Solana Memecoin Launch: 3-Phase Playbook",
    offsetDays: 2
  },
  {
    id: "kc_002",
    category: "pitfalls" as const,
    title: "Common xG Data Misuses in Football Hot Takes",
    offsetDays: 5
  },
  {
    id: "kc_003",
    category: "frameworks" as const,
    title: "SPINE: Multi-Agent Output Quality Gate",
    offsetDays: 9
  }
];

const CAT: Record<
  (typeof ITEMS)[number]["category"] | "entities",
  "default" | "success" | "warning" | "error"
> = {
  strategies: "success",
  pitfalls: "error",
  frameworks: "warning",
  entities: "default"
};

export default function RecentKnowledgeCard() {
  const hydrated = useIsHydrated();
  const nowRef = hydrated ? Date.now() : BASE_DATE + 86400000 * 11;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm tracking-widest">
          CRYSTALLIZED KNOWLEDGE
        </CardTitle>
      </CardHeader>
      <CardContent className="py-3 px-2">
        <div className="space-y-1">
          {ITEMS.map((it) => {
            const createdAt = new Date(nowRef - 86400000 * it.offsetDays).toISOString();
            return (
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
                    <div className="text-sm truncate glow-text">
                      {it.title}
                    </div>
                  </div>
                  <div className="text-[10px] text-matrix-dim tracking-wider text-right shrink-0">
                    <div>{it.id}</div>
                    <div className="mt-0.5">{formatDate(createdAt)}</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
