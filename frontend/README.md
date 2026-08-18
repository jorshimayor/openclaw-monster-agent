# Monster Agent · Frontend (Next.js / Command-Center UI)

## Local Dev Quick Start

### Requirements

- **Node 20+** (LTS recommended)
- **npm** (bundled with Node)

### Install

```bash
cd frontend
npm install
```

### Configure

```bash
cp .env.example .env.local
```

Contents of `frontend/.env.local`:
```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

This must point to your running FastAPI backend (default port: `8000). For production, set this to your Render backend URL.

### Run Dev Server

```bash
cd frontend
npm run dev
```

Open **http://localhost:3000**

Pages:
- `/` — Command-Center dashboard (system status, agent roster, pipeline activity legend, recent knowledge crystals).
- `/tasks` — Submit + monitor pipeline tasks.
- `/tasks/[id]` — Live SSE stream of 11-step pipeline.
- `/agents` — 8-agent roster.
- `/knowledge` — Knowledge crystals browser.
- `/integrations` — MCP integrations health (5 servers status).

### Production Build

```bash
cd frontend
npm run build
npm start
```

## Aesthetic Notes

### Palette · Command-Center Matrix

The UI uses a custom "matrix" cyberpunk command-center theme. Key colors (Tailwind config in `tailwind.config.ts`):

| Token          | Hex        | Role                               |
|--------------|------------|------------------------------------|
| bg-deep      | `#05070d`  | Page background                    |
| panel        | `#0b1120`  | Card panels, cards                   |
| matrix-green  | `#22d3ee`  | Primary accent (status OK, highlights |
| warning       | `#fbbf24`  | Warnings, amber                   |
| danger        | `#ef4444`  | Errors, failures            |
| accent       | `#a855f7`  | Agent avatars, pipeline step glows  |
| muted       | `#64748b`  | Secondary text, borders            |

### Typography

Default font: **JetBrains Mono** (monospace). Applied globally via `globals.css`:
- Code blocks, numbers, IDs, status badges, timestamps all use JetBrains Mono for command-center feel.
