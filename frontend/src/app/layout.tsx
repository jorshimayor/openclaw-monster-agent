import type { Metadata } from "next";
import { JetBrains_Mono, Inter } from "next/font/google";
import Link from "next/link";
import "@/styles/globals.css";
import { ThemeProvider, themeBootstrapScript } from "@/lib/theme-provider";
import { ConnLabel } from "@/components/ConnLabel";
import ThemeSwitcher from "@/components/ui/theme-switcher";

const jb = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });
const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "Monster Agent · J.A.R.V.I.S. Command Center",
  description: "Multi-agent orchestration dashboard"
};

const NAV_LINKS = [
  { href: "/", label: "Dashboard", icon: "⬢" },
  { href: "/tasks", label: "Tasks", icon: "▤" },
  { href: "/agents", label: "Agents", icon: "◎" },
  { href: "/knowledge", label: "Knowledge", icon: "◈" },
  { href: "/integrations", label: "Integrations", icon: "⬡" }
];

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`dark ${jb.variable} ${inter.variable}`}>
      <head>
        <script
          dangerouslySetInnerHTML={{ __html: themeBootstrapScript }}
          // Run before React paints to avoid flash of unstyled (wrong) theme.
          // eslint-disable-next-line react/no-danger
        />
      </head>
      <body className="bg-bg text-matrix font-mono antialiased min-h-screen flex">
        <ThemeProvider>
          <aside className="w-64 border-r border-bg-border bg-bg-panel flex flex-col shrink-0">
            <div className="px-5 py-5 border-b border-bg-border">
              <div className="flex items-center gap-2 text-lg font-bold tracking-wider glow-text">
                <span className="text-2xl">🦞</span>
                <span>MONSTER</span>
              </div>
              <div className="text-[10px] text-matrix-dim mt-1 tracking-[0.2em]">
                J.A.R.V.I.S. · COMMAND
              </div>
            </div>
            <nav className="flex-1 py-4 px-3 space-y-1">
              {NAV_LINKS.map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  className="flex items-center gap-3 px-3 py-2.5 text-sm rounded border border-transparent hover:border-matrix/30 hover:bg-matrix/5 transition-colors"
                >
                  <span className="text-matrix-dim">{l.icon}</span>
                  <span>{l.label}</span>
                </Link>
              ))}
            </nav>
            <div className="px-4 py-4 border-t border-bg-border">
              <div className="text-[10px] text-matrix-dim tracking-widest mb-2">
                SYSTEM STATUS
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-matrix-dim">API</span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-matrix animate-pulse"></span>
                    ONLINE
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-matrix-dim">Nodes</span>
                  <span>8 / 8</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-matrix-dim">Queue</span>
                  <span>0</span>
                </div>
              </div>
            </div>
          </aside>

          <div className="flex-1 flex flex-col min-w-0">
            <header className="h-14 border-b border-bg-border bg-bg-panel px-6 flex items-center justify-between shrink-0 gap-4">
              <div className="flex items-center gap-4 text-xs min-w-0">
                <span className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-matrix animate-pulse-matrix"></span>
                  <span className="text-matrix-dim shrink-0">CONN:</span>
                  <ConnLabel />
                </span>
              </div>
              <div className="flex items-center gap-4 text-xs text-matrix-dim shrink-0">
                <ThemeSwitcher />
                <span className="hidden sm:inline">SESSION: 0xA1B2C3D4</span>
                <span className="text-matrix">v1.0.0</span>
              </div>
            </header>

            <main className="flex-1 p-6 overflow-auto scanlines">{children}</main>

            <footer className="border-t border-bg-border px-6 py-2 text-[10px] text-matrix-dim flex justify-between shrink-0">
              <span>© MONSTER AGENT · MULTI-AGENT ORCHESTRATION</span>
              <span>BUILD 2026.08.17 · STABLE</span>
            </footer>
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}
