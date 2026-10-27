"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";
import { NAV_LINKS } from "@/lib/nav";
import SidebarStatus from "@/components/SidebarStatus";
import { cn } from "@/lib/utils";

/**
 * Navigation on a narrow screen.
 *
 * The rail beside the content is a fixed 16rem and never gave any of it back,
 * so at phone width the page had about 120px to live in — headings broke one
 * word per line and the inputs were a few characters wide. Below `md` the rail
 * is hidden and this takes over: a button in the header, a drawer over the
 * content.
 *
 * The panel stays mounted so it can slide rather than appear, but the status
 * block inside it is mounted only while the drawer is open. That block polls
 * the API on a timer, and `pollWhileVisible` goes by document visibility, not
 * by whether the element is on screen — a second copy sitting behind a closed
 * drawer would quietly double the request rate.
 */
export default function NavDrawer() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const openerRef = useRef<HTMLButtonElement>(null);
  const closerRef = useRef<HTMLButtonElement>(null);

  // Tapping a link navigates underneath; without this the drawer stays over it.
  useEffect(() => setOpen(false), [pathname]);


  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    /*
     * The page behind a modal drawer should not scroll with it. The lock is a
     * class rather than an inline style so the breakpoint that hides the
     * drawer also releases it: turning a phone to landscape crosses `md` — an
     * iPhone on its side is 812px wide — and an inline lock would survive
     * that, leaving the page unscrollable with nothing on screen to unlock it.
     */
    document.body.classList.add("overflow-hidden", "md:overflow-auto");
    closerRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("overflow-hidden", "md:overflow-auto");
      openerRef.current?.focus();
    };
  }, [open]);

  return (
    <>
      <button
        ref={openerRef}
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open navigation"
        aria-expanded={open}
        aria-controls="nav-drawer"
        className="md:hidden -ml-1 shrink-0 rounded border border-transparent p-1.5 hover:border-matrix/30 hover:bg-matrix/5 transition-colors"
      >
        <Menu className="h-4 w-4" />
      </button>

      {/*
        Transitioning visibility as well as the slide keeps the panel out of the
        tab order while closed, without cutting the slide-out short: the
        discrete flip to hidden lands at the end of the duration.
      */}
      <div
        className={cn(
          "md:hidden fixed inset-0 z-50 transition-[visibility] duration-200",
          open ? "visible" : "invisible"
        )}
      >
        <div
          aria-hidden
          onClick={() => setOpen(false)}
          className={cn(
            "absolute inset-0 bg-black/70 transition-opacity duration-200",
            open ? "opacity-100" : "opacity-0"
          )}
        />

        <div
          id="nav-drawer"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation"
          className={cn(
            "absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-bg-border bg-bg-panel transition-transform duration-200",
            open ? "translate-x-0" : "-translate-x-full"
          )}
        >
          <div className="flex items-start justify-between gap-2 border-b border-bg-border px-5 py-5">
            <div>
              <div className="flex items-center gap-2 text-lg font-bold tracking-wider glow-text">
                <span className="text-2xl">🦞</span>
                <span>MONSTER</span>
              </div>
              <div className="mt-1 text-[10px] text-matrix-dim tracking-[0.2em]">
                J.A.R.V.I.S. · COMMAND
              </div>
            </div>
            <button
              ref={closerRef}
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close navigation"
              className="rounded border border-transparent p-1.5 hover:border-matrix/30 hover:bg-matrix/5 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
            {NAV_LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className="flex items-center gap-3 rounded border border-transparent px-3 py-2.5 text-sm hover:border-matrix/30 hover:bg-matrix/5 transition-colors"
              >
                <span className="text-matrix-dim">{l.icon}</span>
                <span>{l.label}</span>
              </Link>
            ))}
          </nav>

          <div className="border-t border-bg-border px-4 py-4">
            <div className="mb-2 text-[10px] text-matrix-dim tracking-widest">
              SYSTEM STATUS
            </div>
            {open && <SidebarStatus />}
          </div>
        </div>
      </div>
    </>
  );
}
