# Hashnode MCP Server

Standalone Model Context Protocol server for Hashnode integration.

## Setup

```bash
npm install
npm run build
```

## Run

```bash
npm start
```

## Environment Variables

Required:
- `HASHNODE_TOKEN` — Hashnode Personal Access Token

Optional:
- `HASHNODE_PUBLICATION_ID` — Default publication ID for posts/drafts
- `LOG_LEVEL` — Logging verbosity (default: info)
