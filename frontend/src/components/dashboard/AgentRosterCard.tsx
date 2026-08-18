import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const ROSTER = [
  { emoji: "🧭", name: "Project Lead", role: "orchestrator" },
  { emoji: "✍️", name: "Web2 Content", role: "content_web2" },
  { emoji: "⛓️", name: "Web3 Content", role: "content_web3" },
  { emoji: "⚽", name: "Football", role: "football" },
  { emoji: "🛠️", name: "Editor", role: "editor" },
  { emoji: "🔬", name: "Security", role: "security" },
  { emoji: "🧠", name: "Knowledge", role: "knowledge" },
  { emoji: "👤", name: "Study", role: "study" }
];

export default function AgentRosterCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm tracking-widest flex items-center justify-between">
          <span>AGENT ROSTER</span>
          <span className="text-[10px] text-matrix-dim font-normal">
            8 / 8 ONLINE
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="py-3 px-2">
        <div className="divide-y divide-bg-border/60">
          {ROSTER.map((r) => (
            <div
              key={r.role}
              className="flex items-center justify-between px-4 py-2.5 hover:bg-matrix/5 transition-colors rounded"
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded border border-matrix/20 bg-matrix/5 flex items-center justify-center text-base">
                  {r.emoji}
                </div>
                <div>
                  <div className="text-sm font-medium">{r.name}</div>
                  <div className="text-[10px] text-matrix-dim tracking-widest">
                    {r.role.toUpperCase().replace(/_/g, " ")}
                  </div>
                </div>
              </div>
              <Badge variant="success" className="gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                IDLE
              </Badge>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
