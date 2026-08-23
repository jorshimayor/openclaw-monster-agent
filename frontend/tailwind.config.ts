import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

/**
 * Tailwind tokens — all color utilities resolve to CSS variables declared in
 * globals.css via html[data-theme="..."]. This means switching themes is a
 * single HTML attribute write — no React re-render needed for color changes.
 *
 * Naming intentionally mirrors the original hardcoded matrix/bg tokens so
 * existing component classes (bg-matrix, text-matrix-dim, border-bg-border,
 * shadow-matrix-glow, animate-pulse-matrix, …) continue to work unchanged.
 */
export default {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        matrix: {
          DEFAULT: "var(--theme-accent)",
          dim: "var(--theme-accent-dim)"
        },
        accent: {
          DEFAULT: "var(--theme-accent)",
          dim: "var(--theme-accent-dim)",
          fg: "var(--theme-accent-fg)"
        },
        bg: {
          DEFAULT: "var(--theme-bg)",
          panel: "var(--theme-bg-panel)",
          border: "var(--theme-bg-border)"
        },
        success: "var(--theme-success)",
        warning: "var(--theme-warning)",
        danger: "var(--theme-danger)",
        text: {
          DEFAULT: "var(--theme-text)",
          dim: "var(--theme-text-dim)"
        }
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "Menlo", "monospace"],
        sans: ["Inter", "ui-sans-serif", "system-ui"]
      },
      boxShadow: {
        "matrix-glow":
          "0 0 12px color-mix(in srgb, var(--theme-accent) 25%, transparent)",
        "accent-glow":
          "0 0 12px color-mix(in srgb, var(--theme-accent) 25%, transparent)",
        "accent-glow-lg":
          "0 0 20px color-mix(in srgb, var(--theme-accent) 45%, transparent)"
      },
      ringColor: {
        DEFAULT: "var(--theme-accent)"
      },
      keyframes: {
        "pulse-matrix": {
          "0%, 100%": {
            opacity: "1",
            boxShadow:
              "0 0 8px color-mix(in srgb, var(--theme-accent) 60%, transparent)"
          },
          "50%": {
            opacity: "0.65",
            boxShadow:
              "0 0 20px color-mix(in srgb, var(--theme-accent) 90%, transparent)"
          }
        }
      },
      animation: {
        "pulse-matrix": "pulse-matrix 1.5s ease-in-out infinite"
      }
    }
  },
  plugins: [typography]
} satisfies Config;
