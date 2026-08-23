"use client";

/**
 * Connection label for the header. MUST be a client component:
 * NEXT_PUBLIC_* vars are inlined at build time only into client bundles —
 * in the server-rendered layout the env var doesn't exist at the Pages edge
 * runtime, which is how "localhost:8000" ended up in production HTML.
 */
const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export function ConnLabel() {
  return (
    <span className="tracking-wider truncate">
      {base.replace(/^https?:\/\//, "")}
    </span>
  );
}
