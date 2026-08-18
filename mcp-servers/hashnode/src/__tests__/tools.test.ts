import { describe, it, expect, vi } from "vitest";
import type { Mock } from "vitest";
import { publishPostTool } from "../tools/publish.js";
import { manageDraftsTool } from "../tools/draft.js";
import { readPostsTool } from "../tools/read.js";
import type { HashnodeClient } from "../client.js";

function createMockClient(): HashnodeClient {
  return {
    publishPost: vi.fn(),
    createDraft: vi.fn(),
    updateDraft: vi.fn(),
    deleteDraft: vi.fn(),
    readPosts: vi.fn(),
    getPost: vi.fn(),
  } as unknown as HashnodeClient;
}

describe("Tools", () => {
  describe("publish_post", () => {
    it("publish_post_dryRun_returns_preview_without_GQL", async () => {
      const client = createMockClient();
      const result = await publishPostTool.handler(
        {
          title: "Preview Post",
          contentMarkdown: "# Hello\n\nThis is a test preview with enough content words to be counted properly for the dry run preview.",
          dryRun: true,
        },
        client
      );

      expect(result.isError).toBeUndefined();
      expect(result.content.length).toBe(1);
      expect(result.content[0].type).toBe("text");

      const parsed = JSON.parse(result.content[0].text);
      expect(parsed.success).toBe(true);
      expect(parsed.preview).toBe(true);
      expect(parsed.title).toBe("Preview Post");
      expect(parsed.wordCount).toBeGreaterThan(0);
      expect(parsed.publicationId).toBe("default");

      expect(client.publishPost as Mock).not.toHaveBeenCalled();
    });

    it("publish_post_calls_client", async () => {
      const client = createMockClient();
      (client.publishPost as Mock).mockResolvedValue({
        success: true,
        id: "p1",
        title: "Real Post",
        url: "https://example.hashnode.dev/real",
      });

      const result = await publishPostTool.handler(
        {
          title: "Real Post",
          contentMarkdown: "# Real content\n\nThis is real content that has enough length to pass the validation minimum so it can be actually published.",
        },
        client
      );

      expect(client.publishPost as Mock).toHaveBeenCalledTimes(1);
      expect(client.publishPost as Mock).toHaveBeenCalledWith({
        title: "Real Post",
        contentMarkdown: expect.stringContaining("# Real content"),
      });

      const parsed = JSON.parse(result.content[0].text);
      expect(parsed.success).toBe(true);
      expect(parsed.id).toBe("p1");
      expect(parsed.url).toBe("https://example.hashnode.dev/real");
    });
  });

  describe("manage_drafts", () => {
    it("manage_drafts_action_create", async () => {
      const client = createMockClient();
      (client.createDraft as Mock).mockResolvedValue({
        id: "d1",
        title: "New Draft",
        slug: "new-draft",
      });

      const result = await manageDraftsTool.handler(
        {
          action: "create",
          title: "New Draft",
          contentMarkdown: "# Draft body\n\nThis draft content has enough words in it to pass the minimum length validation for draft creation.",
        },
        client
      );

      expect(client.createDraft as Mock).toHaveBeenCalledTimes(1);
      const parsed = JSON.parse(result.content[0].text);
      expect(parsed.success).toBe(true);
      expect(parsed.action).toBe("create");
      expect(parsed.draft.id).toBe("d1");
    });

    it("manage_drafts_missing_draftId_for_delete_throws", async () => {
      const client = createMockClient();
      const result = await manageDraftsTool.handler(
        {
          action: "delete",
        },
        client
      );

      expect(result.isError).toBe(true);
      const parsed = JSON.parse(result.content[0].text);
      expect(parsed.success).toBe(false);
      expect(parsed.error).toContain("draftId");
      expect(client.deleteDraft as Mock).not.toHaveBeenCalled();
    });

    it("manage_drafts_action_update_calls_client", async () => {
      const client = createMockClient();
      (client.updateDraft as Mock).mockResolvedValue({
        id: "d1",
        title: "Updated",
        slug: "updated",
      });

      const result = await manageDraftsTool.handler(
        {
          action: "update",
          draftId: "d1",
          title: "Updated",
        },
        client
      );

      expect(client.updateDraft as Mock).toHaveBeenCalledWith("d1", {
        title: "Updated",
      });
      const parsed = JSON.parse(result.content[0].text);
      expect(parsed.success).toBe(true);
      expect(parsed.draft.title).toBe("Updated");
    });
  });

  describe("read_posts", () => {
    it("read_posts_list_returns_array", async () => {
      const client = createMockClient();
      (client.readPosts as Mock).mockResolvedValue([
        { id: "a", title: "A", slug: "a", url: "url-a" },
        { id: "b", title: "B", slug: "b", url: "url-b" },
      ]);

      const result = await readPostsTool.handler(
        {
          mode: "list",
          limit: 10,
        },
        client
      );

      expect(client.readPosts as Mock).toHaveBeenCalledWith(undefined, 10);
      const parsed = JSON.parse(result.content[0].text);
      expect(parsed.success).toBe(true);
      expect(parsed.mode).toBe("list");
      expect(parsed.count).toBe(2);
      expect(Array.isArray(parsed.posts)).toBe(true);
    });

    it("read_posts_get_by_id_requires_postId", async () => {
      const client = createMockClient();
      const result = await readPostsTool.handler(
        {
          mode: "get_by_id",
        },
        client
      );

      expect(result.isError).toBe(true);
      const parsed = JSON.parse(result.content[0].text);
      expect(parsed.success).toBe(false);
      expect(parsed.error).toContain("postId");
      expect(client.getPost as Mock).not.toHaveBeenCalled();
    });

    it("read_posts_get_by_id_calls_getPost", async () => {
      const client = createMockClient();
      (client.getPost as Mock).mockResolvedValue({
        id: "p1",
        title: "Full",
        slug: "full",
        url: "url-full",
        contentMarkdown: "# Content",
      });

      const result = await readPostsTool.handler(
        {
          mode: "get_by_id",
          postId: "p1",
        },
        client
      );

      expect(client.getPost as Mock).toHaveBeenCalledWith("p1");
      const parsed = JSON.parse(result.content[0].text);
      expect(parsed.success).toBe(true);
      expect(parsed.post.id).toBe("p1");
      expect(parsed.post.contentMarkdown).toBe("# Content");
    });
  });
});
