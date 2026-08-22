import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

export default {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        matrix: {
          DEFAULT: "#00ff41",
          dim: "#008f20"
        },
        bg: {
          DEFAULT: "#0a0a0a",
          panel: "#0f1110",
          border: "#1a1f1c"
        }
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "Menlo", "monospace"],
        sans: ["Inter", "ui-sans-serif", "system-ui"]
      },
      boxShadow: {
        "matrix-glow": "0 0 12px rgba(0,255,65,0.25)"
      },
      keyframes: {
        "pulse-matrix": {
          "0%, 100%": { opacity: "1", boxShadow: "0 0 8px rgba(0,255,65,0.6)" },
          "50%": { opacity: "0.6", boxShadow: "0 0 20px rgba(0,255,65,0.9)" }
        }
      },
      animation: {
        "pulse-matrix": "pulse-matrix 1.5s ease-in-out infinite"
      }
    }
  },
  plugins: [typography]
} satisfies Config;
