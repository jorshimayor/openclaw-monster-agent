"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from "react";
import {
  DEFAULT_THEME_ID,
  THEME_LIST,
  THEMES,
  isValidThemeId,
  type ThemeId,
  type ThemePalette
} from "@/lib/theme";

const STORAGE_KEY = "monster-agent.theme";

function resolveInitialTheme(): ThemeId {
  const envDefault =
    (typeof process !== "undefined" &&
      process.env &&
      process.env.NEXT_PUBLIC_DEFAULT_THEME) ||
    null;
  if (isValidThemeId(envDefault)) return envDefault;

  if (typeof window === "undefined") return DEFAULT_THEME_ID;

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isValidThemeId(stored)) return stored;
  } catch {
    /* localStorage unavailable */
  }

  return DEFAULT_THEME_ID;
}

function applyThemeToDom(id: ThemeId) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.setAttribute("data-theme", id);
  const palette = THEMES[id];
  if (palette.mode === "dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
}

/**
 * Inline bootstrap script — rendered before React so the correct theme is
 * painted on first paint (no flash of wrong theme, "FOUSC").
 *
 * Lives in a plain <script> in the root <head>. Must be tiny + sync.
 */
export const themeBootstrapScript = `
(function(){
  try{
    var k='${STORAGE_KEY}';
    var s=window.localStorage.getItem(k);
    var env=(window.__NEXT_DATA__||{}).props&&window.__NEXT_DATA__.props.pageProps&&window.__NEXT_DATA__.props.pageProps.__defaultTheme;
    var valid=['matrix','cyberpunk','aurora','slate','sunset','minimal'];
    var d=document.documentElement;
    var pick=s;
    if(valid.indexOf(pick)===-1){ pick=env; }
    if(valid.indexOf(pick)===-1){ pick='${DEFAULT_THEME_ID}'; }
    d.setAttribute('data-theme', pick);
    if(pick!=='minimal'){ d.classList.add('dark'); } else { d.classList.remove('dark'); }
  }catch(e){}
})();
`;

interface ThemeContextValue {
  themeId: ThemeId;
  theme: ThemePalette;
  allThemes: ThemePalette[];
  setTheme: (id: ThemeId) => void;
  cycleNext: () => void;
  resetToDefault: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({
  children,
  forcedTheme
}: {
  children: ReactNode;
  forcedTheme?: ThemeId;
}) {
  const [themeId, setThemeId] = useState<ThemeId>(() =>
    forcedTheme ?? resolveInitialTheme()
  );

  useEffect(() => {
    applyThemeToDom(themeId);
  }, [themeId]);

  const setTheme = useCallback(
    (id: ThemeId) => {
      setThemeId(id);
      try {
        window.localStorage.setItem(STORAGE_KEY, id);
      } catch {
        /* ignore */
      }
    },
    []
  );

  const cycleNext = useCallback(() => {
    const idx = THEME_LIST.findIndex((t) => t.id === themeId);
    const next = THEME_LIST[(idx + 1) % THEME_LIST.length].id;
    setTheme(next);
  }, [themeId, setTheme]);

  const resetToDefault = useCallback(() => {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
    setThemeId(DEFAULT_THEME_ID);
  }, [setTheme]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      themeId,
      theme: THEMES[themeId],
      allThemes: THEME_LIST,
      setTheme,
      cycleNext,
      resetToDefault
    }),
    [themeId, setTheme, cycleNext, resetToDefault]
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme() must be used within <ThemeProvider>");
  }
  return ctx;
}
