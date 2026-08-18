import { z } from "zod";
import type { HashnodeClient } from "../client.js";
import type { PublishResult } from "../types.js";

export interface McpTool<TSchema extends z.ZodTypeAny> {
  name: string;
  description: string;
  inputSchema: TSchema;
  handler: (args: z.infer<TSchema>, client: HashnodeClient) => Promise<{
    content: Array<{ type: "text"; text: string }>;
    isError?: boolean;
  }>;
}

export const publishPostSchema = z.object({
  title: z.string().min(3).max(200),
  contentMarkdown: z.string().min(50),
  publicationId: z.string().optional(),
  tags: z
    .array(
      z.object({
        name: z.string(),
        slug: z.string().optional(),
      })
    )
    .optional(),
  coverImageUrl: z.string().url().optional(),
  subtitle: z.string().optional(),
  dryRun: z
    .boolean()
    .default(false)
    .describe("If true, skip publish and return preview only"),
});

export const publishPostTool: McpTool<typeof publishPostSchema> = {
  name: "publish_post",
  description:
    "Publish a blog post to Hashnode. Requires title and markdown content. Returns published post URL.",
  inputSchema: publishPostSchema,
  handler: async (args, client) => {
    const { dryRun, ...publishInput } = args;

    if (dryRun) {
      const preview = {
        success: true,
        preview: true,
        title: publishInput.title,
        wordCount: publishInput.contentMarkdown.split(/\s+/).filter(Boolean).length,
        tagCount: publishInput.tags?.length ?? 0,
        hasCoverImage: !!publishInput.coverImageUrl,
        subtitle: publishInput.subtitle,
        publicationId: publishInput.publicationId ?? "default",
      };
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(preview, null, 2),
          },
        ],
      };
    }

    try {
      const result: PublishResult = await client.publishPost(publishInput);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(result, null, 2),
          },
        ],
      };
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
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
  },
};
