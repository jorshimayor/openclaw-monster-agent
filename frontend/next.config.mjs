/** @type {import('next').NextConfig} */
export default {
  reactStrictMode: true,
  // Inline the API base at build time via config `env` — this survives every
  // build path. `vercel build` (run inside @cloudflare/next-on-pages) does
  // NOT load the repo's .env.production, which is how localhost:8000 ended
  // up baked into the production bundle. Shell env still overrides.
  env: {
    NEXT_PUBLIC_API_BASE_URL:
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      (process.env.NODE_ENV === "production"
        ? "https://monster-agent-backend.joelobafemii.workers.dev"
        : "http://localhost:8000")
  },
  experimental: {
    serverActions: {
      allowedOrigins: ["*"]
    }
  },
  images: {
    remotePatterns: []
  }
}
