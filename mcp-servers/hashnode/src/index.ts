import "dotenv/config";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import { HashnodeClient, HashnodeApiError } from "./client.js";
import {
  publishPostTool,
  manageDraftsTool,
  readPostsTool,
} from "./tools/index.js";
import type { McpTool } from "./tools/publish.js";

const envSchema = z.object({
  HASHNODE_TOKEN: z.string().min(1, "HASHNODE_TOKEN is required"),
  HASHNODE_PUBLICATION_ID: z.string().optional(),
  LOG_LEVEL: z.string().default("info"),
});

type AnyMcpTool = McpTool<z.ZodTypeAny>;

function validateEnv() {
  try {
    return envSchema.parse(process.env);
  } catch (err) {
    if (err instanceof z.ZodError) {
      const issues = err.issues
        .map((i) => `${i.path.join(".")}: ${i.message}`)
        .join(", ");
      throw new Error(`Invalid environment variables: ${issues}`);
    }
    throw err;
  }
}

const env = validateEnv();

const client = new HashnodeClient(
  env.HASHNODE_TOKEN,
  env.HASHNODE_PUBLICATION_ID
);

export const tools: AnyMcpTool[] = [
  publishPostTool as AnyMcpTool,
  manageDraftsTool as AnyMcpTool,
  readPostsTool as AnyMcpTool,
];

function zodShapeToJsonSchema(shape: Record<string, z.ZodTypeAny>) {
  const properties: Record<string, unknown> = {};
  const required: string[] = [];

  for (const [key, schema] of Object.entries(shape)) {
    const def = (schema as z.ZodTypeAny)._def;
    const typeName = def.typeName;
    const isOptional =
      typeName === "ZodOptional" ||
      typeName === "ZodDefault" ||
      def.innerType?._def?.typeName === "ZodUndefined";

    let prop: Record<string, unknown> = {};

    if (typeName === "ZodString") {
      prop = { type: "string" };
      if (def.checks) {
        for (const check of def.checks) {
          if (check.kind === "min") prop.minLength = check.value;
          if (check.kind === "max") prop.maxLength = check.value;
          if (check.kind === "regex") prop.pattern = check.regex?.source;
        }
      }
    } else if (typeName === "ZodNumber") {
      prop = { type: "number" };
      if (def.checks) {
        for (const check of def.checks) {
          if (check.kind === "min") prop.minimum = check.value;
          if (check.kind === "max") prop.maximum = check.value;
          if (check.kind === "int") prop.integer = true;
        }
      }
    } else if (typeName === "ZodBoolean") {
      prop = { type: "boolean" };
    } else if (typeName === "ZodDefault") {
      const inner = def.innerType as z.ZodTypeAny;
      const innerDef = inner._def;
      if (innerDef.typeName === "ZodBoolean") prop = { type: "boolean" };
      else if (innerDef.typeName === "ZodNumber") prop = { type: "number" };
      else if (innerDef.typeName === "ZodString") prop = { type: "string" };
      else if (innerDef.typeName === "ZodEnum") {
        prop = { type: "string", enum: innerDef.values };
      }
      prop.default = def.defaultValue;
    } else if (typeName === "ZodEnum") {
      prop = { type: "string", enum: def.values };
    } else if (typeName === "ZodOptional") {
      const inner = def.innerType as z.ZodTypeAny;
      const innerDef = inner._def;
      if (innerDef.typeName === "ZodString") prop = { type: "string" };
      else if (innerDef.typeName === "ZodNumber") prop = { type: "number" };
      else if (innerDef.typeName === "ZodBoolean") prop = { type: "boolean" };
      else if (innerDef.typeName === "ZodArray") {
        prop = { type: "array" };
      } else if (innerDef.typeName === "ZodObject") {
        prop = { type: "object" };
      } else if (innerDef.typeName === "ZodEnum") {
        prop = { type: "string", enum: innerDef.values };
      }
    } else if (typeName === "ZodArray") {
      prop = { type: "array" };
    } else if (typeName === "ZodObject") {
      prop = { type: "object" };
    }

    properties[key] = prop;
    if (!isOptional) required.push(key);
  }

  return {
    type: "object",
    properties,
    required: required.length > 0 ? required : undefined,
  };
}

const server = new Server(
  {
    name: "hashnode-mcp",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: tools.map((t) => {
      const shape = (t.inputSchema as z.ZodObject<never>).shape as Record<
        string,
        z.ZodTypeAny
      >;
      return {
        name: t.name,
        description: t.description,
        inputSchema: zodShapeToJsonSchema(shape),
      };
    }),
  };
});

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const tool = tools.find((t) => t.name === req.params.name);
  if (!tool) {
    throw new Error(`Unknown tool: ${req.params.name}`);
  }

  const parsed = tool.inputSchema.safeParse(req.params.arguments ?? {});
  if (!parsed.success) {
    const issues = parsed.error.issues
      .map((i) => `${i.path.join(".")}: ${i.message}`)
      .join(", ");
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(
            { success: false, error: `Invalid input: ${issues}` },
            null,
            2
          ),
        },
      ],
      isError: true,
    };
  }

  try {
    return await tool.handler(parsed.data, client);
  } catch (err) {
    const message =
      err instanceof Error
        ? err.message
        : err instanceof HashnodeApiError
        ? err.message
        : "Unknown error";
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(
            { success: false, error: message },
            null,
            2
          ),
        },
      ],
      isError: true,
    };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  process.stderr.write("Hashnode MCP server running on stdio\n");

  const shutdown = async (signal: string) => {
    process.stderr.write(`\nReceived ${signal}, shutting down...\n`);
    try {
      await server.close();
    } catch {
    }
    process.exit(0);
  };

  process.on("SIGINT", () => void shutdown("SIGINT"));
  process.on("SIGTERM", () => void shutdown("SIGTERM"));
}

main().catch((err) => {
  process.stderr.write(
    `Fatal error starting server: ${err instanceof Error ? err.message : String(err)}\n`
  );
  process.exit(1);
});
