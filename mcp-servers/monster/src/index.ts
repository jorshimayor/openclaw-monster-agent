#!/usr/bin/env node
/**
 * Monster Agent MCP server.
 *
 * Lets another agent talk to the Monster bot over MCP instead of raw HTTP:
 * tools are discoverable, arguments are validated before they leave this
 * process, and the Cloudflare Access service token stays here rather than
 * being handed to the caller.
 *
 *   MONSTER_API_BASE_URL       https://monster-agent-backend.<account>.workers.dev
 *   MONSTER_ACCESS_CLIENT_ID   Access service token client id
 *   MONSTER_ACCESS_CLIENT_SECRET
 *
 * Without the token pair it still runs and still talks to the API — which is
 * exactly what the API allows today. It says so on startup rather than
 * pretending to be authenticated.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { zodToJsonSchema } from "zod-to-json-schema";

import { MonsterApiError, MonsterClient } from "./client.js";
import { TOOLS, TOOLS_BY_NAME } from "./tools.js";

const baseUrl = process.env.MONSTER_API_BASE_URL;
if (!baseUrl) {
  console.error("MONSTER_API_BASE_URL is not set — nothing to talk to.");
  process.exit(1);
}

const clientId = process.env.MONSTER_ACCESS_CLIENT_ID;
const clientSecret = process.env.MONSTER_ACCESS_CLIENT_SECRET;
const client = new MonsterClient({ baseUrl, clientId, clientSecret });

if (!client.authenticated) {
  console.error(
    "warning: no Access service token set. Calls go out unauthenticated, " +
      "which works only while the API is still open to the internet.",
  );
}

const server = new Server(
  { name: "monster-agent", version: "1.0.0" },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS.map((tool) => ({
    name: tool.name,
    description: tool.description,
    inputSchema: zodToJsonSchema(tool.schema, { target: "jsonSchema7" }) as any,
  })),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const tool = TOOLS_BY_NAME.get(request.params.name);
  if (!tool) {
    return {
      isError: true,
      content: [{ type: "text" as const, text: `unknown tool ${request.params.name}` }],
    };
  }

  const parsed = tool.schema.safeParse(request.params.arguments ?? {});
  if (!parsed.success) {
    // Validate here so a bad call never reaches the API and never costs a
    // container wake.
    return {
      isError: true,
      content: [
        { type: "text" as const, text: `invalid arguments: ${parsed.error.message}` },
      ],
    };
  }

  try {
    const result = await tool.handler(client, parsed.data);
    return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
  } catch (error) {
    const text =
      error instanceof MonsterApiError
        ? `${error.message}\n${error.body}`
        : `${(error as Error)?.message ?? error}`;
    return { isError: true, content: [{ type: "text" as const, text }] };
  }
});

await server.connect(new StdioServerTransport());
console.error(`monster-agent MCP server ready — ${TOOLS.length} tools, ${baseUrl}`);
