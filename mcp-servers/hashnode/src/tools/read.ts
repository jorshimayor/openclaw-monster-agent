import { z } from "zod";
import type { McpTool } from "./publish.js";

export const readPostsSchema = z.object({
  mode: z.enum(["list", "get_by_id"]).default("list"),
  publicationId: z.string().optional(),
  postId: z.string().optional(),
  limit: z.number().int().min(1).max(50).default(10),
});

export const readPostsTool: McpTool<typeof readPostsSchema> = {
  name: "read_posts",
  description:
    "List published posts from a Hashnode publication or fetch a single post by id",
  inputSchema: readPostsSchema,
  handler: async (args, client) => {
    try {
      if (args.mode === "list") {
        const posts = await client.readPosts(args.publicationId, args.limit);
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                {
                  success: true,
                  mode: "list",
                  count: posts.length,
                  posts,
                },
                null,
                2
              ),
            },
          ],
        };
      }

      if (args.mode === "get_by_id") {
        if (!args.postId) {
          throw new Error("postId is required for get_by_id mode");
        }
        const post = await client.getPost(args.postId);
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                {
                  success: true,
                  mode: "get_by_id",
                  post,
                },
                null,
                2
              ),
            },
          ],
        };
      }

      throw new Error(`Unknown mode: ${args.mode}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              { success: false, mode: args.mode, error: message },
              null,
              2
            ),
          },
        ],
        isError: true,
      };
    }
  },
};
