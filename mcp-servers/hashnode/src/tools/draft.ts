import { z } from "zod";
import type { HashnodeClient } from "../client.js";
import type { McpTool } from "./publish.js";
import type { DraftAction } from "../types.js";

export const manageDraftsSchema = z.object({
  action: z.enum(["create", "update", "delete", "get"]),
  draftId: z
    .string()
    .optional()
    .describe("Required for update/delete/get"),
  title: z.string().min(3).max(200).optional(),
  contentMarkdown: z.string().min(50).optional(),
  publicationId: z.string().optional(),
});

export const manageDraftsTool: McpTool<typeof manageDraftsSchema> = {
  name: "manage_drafts",
  description:
    "CRUD operations on Hashnode drafts (create, read one, update, delete by id)",
  inputSchema: manageDraftsSchema,
  handler: async (args, client) => {
    const action = args.action as DraftAction;

    try {
      switch (action) {
        case "create": {
          if (!args.title || !args.contentMarkdown) {
            throw new Error("title and contentMarkdown are required for create action");
          }
          const draft = await client.createDraft({
            title: args.title,
            contentMarkdown: args.contentMarkdown,
            publicationId: args.publicationId,
          });
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(
                  { success: true, action: "create", draft },
                  null,
                  2
                ),
              },
            ],
          };
        }

        case "update": {
          if (!args.draftId) {
            throw new Error("draftId is required for update action");
          }
          const updateInput: {
            title?: string;
            contentMarkdown?: string;
            publicationId?: string;
          } = {};
          if (args.title) updateInput.title = args.title;
          if (args.contentMarkdown) updateInput.contentMarkdown = args.contentMarkdown;
          if (args.publicationId) updateInput.publicationId = args.publicationId;

          if (Object.keys(updateInput).length === 0) {
            throw new Error(
              "At least one of title, contentMarkdown, or publicationId must be provided for update"
            );
          }

          const draft = await client.updateDraft(args.draftId, updateInput);
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(
                  { success: true, action: "update", draft },
                  null,
                  2
                ),
              },
            ],
          };
        }

        case "delete": {
          if (!args.draftId) {
            throw new Error("draftId is required for delete action");
          }
          const success = await client.deleteDraft(args.draftId);
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(
                  { success, action: "delete", draftId: args.draftId },
                  null,
                  2
                ),
              },
            ],
          };
        }

        case "get": {
          if (!args.draftId) {
            throw new Error("draftId is required for get action");
          }
          const post = await client.getPost(args.draftId);
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(
                  { success: true, action: "get", post },
                  null,
                  2
                ),
              },
            ],
          };
        }

        default:
          throw new Error(`Unknown action: ${action}`);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              { success: false, action, error: message },
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
