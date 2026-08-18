import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const STEPS: { n: number; key: string; label: string }[] = [
  { n: 1, key: "complexity", label: "COMPLEXITY" },
  { n: 2, key: "pattern", label: "PATTERN" },
  { n: 3, key: "experience", label: "EXPERIENCE" },
  { n: 4, key: "team", label: "TEAM" },
  { n: 5, key: "prompt", label: "PROMPT" },
  { n: 6, key: "execute", label: "EXECUTE" },
  { n: 7, key: "verify", label: "VERIFY" },
  { n: 8, key: "quality_gate", label: "GATE" },
  { n: 9, key: "fix", label: "FIX" },
  { n: 10, key: "synthesize", label: "SYNTHESIZE" },
  { n: 11, key: "reflect", label: "REFLECT" }
];

export default function PipelineActivityLegend() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm tracking-widest flex items-center justify-between">
          <span>11-STEP PIPELINE</span>
          <span className="text-[10px] text-matrix-dim font-normal">
            ALL NODES STANDBY
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-4">
          {STEPS.map((s, idx) => (
            <div key={s.key} className="flex items-center">
              <div className="flex flex-col items-center">
                <div className="w-9 h-9 rounded-full border border-matrix/20 bg-bg text-matrix-dim flex items-center justify-center text-xs font-mono">
                  {s.n}
                </div>
                <div className="text-[9px] text-matrix-dim/80 tracking-widest mt-1.5 max-w-[72px] text-center">
                  {s.label}
                </div>
              </div>
              {idx < STEPS.length - 1 && (
                <div className="w-3 h-px bg-matrix/20 mx-1 mb-5" />
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
