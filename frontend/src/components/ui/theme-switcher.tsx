"use client";

import { useEffect, useRef, useState } from "react";
import { Palette, RotateCcw, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTheme } from "@/lib/theme-provider";
import { Button } from "@/components/ui/button";

export default function ThemeSwitcher({
  className
}: {
  className?: string;
}) {
  const { themeId, theme, allThemes, setTheme, resetToDefault } = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  return (
    <div ref={ref} className={cn("relative shrink-0", className)}>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Theme"
        className="gap-2 px-2.5"
      >
        <Palette className="w-4 h-4" />
        <span className="hidden md:inline text-[10px] tracking-widest">
          THEME: {theme.name.toUpperCase()}
        </span>
        <span
          className="inline-block w-3 h-3 rounded-full border border-bg-border"
          style={{ background: theme.tokens.accent }}
          aria-hidden
        />
      </Button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-2 w-72 rounded-lg border border-bg-border bg-bg-panel shadow-matrix-glow z-50 overflow-hidden"
        >
          <div className="px-4 py-3 border-b border-bg-border flex items-center justify-between">
            <div>
              <div className="text-[10px] tracking-widest text-matrix-dim">
                APPEARANCE
              </div>
              <div className="text-sm font-medium">Choose a theme</div>
            </div>
            <button
              type="button"
              onClick={resetToDefault}
              title="Reset to default"
              className="text-matrix-dim hover:text-matrix p-1.5 rounded border border-transparent hover:border-matrix/30 hover:bg-matrix/5 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="p-2 grid grid-cols-1 gap-1.5 max-h-80 overflow-auto">
            {allThemes.map((t) => {
              const active = t.id === themeId;
              return (
                <button
                  type="button"
                  key={t.id}
                  role="menuitemradio"
                  aria-checked={active}
                  onClick={() => {
                    setTheme(t.id);
                    setOpen(false);
                  }}
                  className={cn(
                    "group flex items-center gap-3 px-3 py-2.5 rounded text-left transition-colors border",
                    active
                      ? "border-matrix/50 bg-matrix/10 shadow-matrix-glow/40"
                      : "border-transparent hover:border-matrix/20 hover:bg-matrix/5"
                  )}
                >
                  <div
                    className="flex w-10 h-10 shrink-0 rounded border border-bg-border overflow-hidden"
                    aria-hidden
                  >
                    {t.swatch.map((c, i) => (
                      <span
                        key={i}
                        className="flex-1"
                        style={{ background: c }}
                      />
                    ))}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-medium">{t.name}</div>
                      {active && (
                        <Check className="w-4 h-4 text-matrix shrink-0" />
                      )}
                    </div>
                    <div className="text-[10px] tracking-wider text-matrix-dim mt-0.5 line-clamp-1">
                      {t.description} ·{" "}
                      <span className="uppercase">{t.mode}</span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="px-4 py-2.5 border-t border-bg-border text-[10px] tracking-widest text-matrix-dim flex items-center justify-between">
            <span>SAVED LOCALLY</span>
            <span className="text-matrix">{themeId}</span>
          </div>
        </div>
      )}
    </div>
  );
}
