import type { Metadata } from "next";
import { JetBrains_Mono, Inter } from "next/font/google";
import Link from "next/link";
import "@/styles/globals.css";
import { ThemeProvider, themeBootstrapScript } from "@/lib/theme-provider";
import { ConnLabel } from "@/components/ConnLabel";
import SidebarStatus from "@/components/SidebarStatus";
import NavDrawer from "@/components/NavDrawer";
import ThemeSwitcher from "@/components/ui/theme-switcher";
import { NAV_LINKS } from "@/lib/nav";

const jb = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });
const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "Monster Agent · J.A.R.V.I.S. Command Center",
  description: "Multi-agent orchestration dashboard",
  // Written by brand/render.py — edit the template, not the public file.
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg", apple: "/logo-mark.svg" }
};

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
          <aside className="hidden md:flex w-64 border-r border-bg-border bg-bg-panel flex-col shrink-0">
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
              <SidebarStatus />
            </div>
          </aside>

          <div className="flex-1 flex flex-col min-w-0">
            <header className="h-14 border-b border-bg-border bg-bg-panel px-4 md:px-6 flex items-center justify-between shrink-0 gap-3">
              <div className="flex items-center gap-3 text-xs min-w-0">
                <NavDrawer />
                <span className="flex items-center gap-2 min-w-0">
                  <span className="w-2 h-2 rounded-full bg-matrix animate-pulse-matrix"></span>
                  <span className="text-matrix-dim shrink-0">CONN:</span>
                  <ConnLabel />
                </span>
              </div>
              <div className="flex items-center gap-4 text-xs text-matrix-dim shrink-0">
                <ThemeSwitcher />
                <span className="text-matrix">v1.0.0</span>
              </div>
            </header>

            <main className="flex-1 p-4 md:p-6 overflow-auto scanlines">{children}</main>

            <footer className="border-t border-bg-border px-4 md:px-6 py-2 text-[10px] text-matrix-dim flex justify-between gap-4 shrink-0">
              <span className="truncate">© MONSTER AGENT · MULTI-AGENT ORCHESTRATION</span>
              <span className="hidden lg:inline shrink-0">
                MULTI-AGENT PIPELINE · ACCOUNTABILITY LEDGER
              </span>
            </footer>
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}
