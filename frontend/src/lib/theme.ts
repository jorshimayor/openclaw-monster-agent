export type ThemeId =
  | "matrix"
  | "cyberpunk"
  | "aurora"
  | "slate"
  | "sunset"
  | "minimal";

export interface ThemePalette {
  id: ThemeId;
  name: string;
  description: string;
  mode: "dark" | "light";
  swatch: [string, string, string];
  tokens: {
    accent: string;
    accentDim: string;
    accentFg: string;
    bg: string;
    bgPanel: string;
    bgBorder: string;
    text: string;
    textDim: string;
    success: string;
    warning: string;
    danger: string;
  };
}

export const THEMES: Record<ThemeId, ThemePalette> = {
  matrix: {
    id: "matrix",
    name: "Matrix Green",
    description: "Classic hacker terminal — neon green on black",
    mode: "dark",
    swatch: ["#00ff41", "#0a0a0a", "#008f20"],
    tokens: {
      accent: "#00ff41",
      accentDim: "#008f20",
      accentFg: "#0a0a0a",
      bg: "#0a0a0a",
      bgPanel: "#0f1110",
      bgBorder: "#1a1f1c",
      text: "#00ff41",
      textDim: "#008f20",
      success: "#34d399",
      warning: "#fbbf24",
      danger: "#f87171"
    }
  },
  cyberpunk: {
    id: "cyberpunk",
    name: "Cyberpunk Neon",
    description: "Night city — hot pink + electric cyan",
    mode: "dark",
    swatch: ["#ff2bd6", "#08060f", "#22d3ee"],
    tokens: {
      accent: "#ff2bd6",
      accentDim: "#a21caf",
      accentFg: "#08060f",
      bg: "#08060f",
      bgPanel: "#100a1e",
      bgBorder: "#2a1a3e",
      text: "#f0abfc",
      textDim: "#a21caf",
      success: "#22d3ee",
      warning: "#fbbf24",
      danger: "#fb7185"
    }
  },
  aurora: {
    id: "aurora",
    name: "Aurora Borealis",
    description: "Teal-mint gradient — calm arctic command deck",
    mode: "dark",
    swatch: ["#5eead4", "#02111a", "#0ea5e9"],
    tokens: {
      accent: "#5eead4",
      accentDim: "#14b8a6",
      accentFg: "#02111a",
      bg: "#02111a",
      bgPanel: "#062030",
      bgBorder: "#0f3a52",
      text: "#ccfbf1",
      textDim: "#14b8a6",
      success: "#34d399",
      warning: "#fbbf24",
      danger: "#fb7185"
    }
  },
  slate: {
    id: "slate",
    name: "Slate Professional",
    description: "Corporate dark mode — blue slate, no glow",
    mode: "dark",
    swatch: ["#60a5fa", "#0b1220", "#94a3b8"],
    tokens: {
      accent: "#60a5fa",
      accentDim: "#3b82f6",
      accentFg: "#0b1220",
      bg: "#0b1220",
      bgPanel: "#111827",
      bgBorder: "#1f2937",
      text: "#e5e7eb",
      textDim: "#94a3b8",
      success: "#34d399",
      warning: "#fbbf24",
      danger: "#f87171"
    }
  },
  sunset: {
    id: "sunset",
    name: "Sunset Amber",
    description: "Warm desert palette — amber + tangerine on charcoal",
    mode: "dark",
    swatch: ["#fb923c", "#140a06", "#facc15"],
    tokens: {
      accent: "#fb923c",
      accentDim: "#d97706",
      accentFg: "#140a06",
      bg: "#140a06",
      bgPanel: "#1c120a",
      bgBorder: "#3a2415",
      text: "#fed7aa",
      textDim: "#d97706",
      success: "#4ade80",
      warning: "#facc15",
      danger: "#f87171"
    }
  },
  minimal: {
    id: "minimal",
    name: "Minimal Light",
    description: "Calm light theme — ink on paper, no effects",
    mode: "light",
    swatch: ["#111827", "#fafaf9", "#6b7280"],
    tokens: {
      accent: "#111827",
      accentDim: "#4b5563",
      accentFg: "#fafaf9",
      bg: "#fafaf9",
      bgPanel: "#ffffff",
      bgBorder: "#e5e7eb",
      text: "#111827",
      textDim: "#6b7280",
      success: "#059669",
      warning: "#d97706",
      danger: "#dc2626"
    }
  }
};

export const THEME_LIST: ThemePalette[] = (
  Object.keys(THEMES) as ThemeId[]
).map((k) => THEMES[k]);

export const DEFAULT_THEME_ID: ThemeId = "matrix";

export function isValidThemeId(v: string | null | undefined): v is ThemeId {
  if (!v) return false;
  return v in THEMES;
}
