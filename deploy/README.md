# Monster Agent · Deployment

Zero-cost deployment stack for full-stack monster agent:

| Layer | Service | Plan | Limits |
|-------|---------|------|--------|
| Frontend (Next.js) | [Vercel Hobby](./vercel/) | Free | 100 GB bandwidth / month |
| Backend (Python FastAPI) | [Render Free Tier](./render/) | Free | 512 MB RAM, 750 hrs / month |

## Quick Deploy Order

1. **Render backend first** — follow [`render/README.md`](./render/README.md).
   - Grab the `https://*.onrender.com` URL once live.
2. **Vercel frontend** — follow [`vercel/README.md`](./vercel/).
   - Set `NEXT_PUBLIC_API_BASE_URL` to the Render URL from step 1.
3. **Update CORS** — add your Vercel domain to `BACKEND_CORS_ORIGINS` in Render env.
