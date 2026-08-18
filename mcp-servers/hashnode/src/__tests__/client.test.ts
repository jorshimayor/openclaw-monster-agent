import { describe, it, expect, beforeAll, afterAll, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { HashnodeClient, HashnodeApiError } from "../client.js";

const TOKEN = "test-token-123";
const PUB_ID = "pub-456";
const ENDPOINT = "https://gql.hashnode.com";

const restHandlers = [
  http.post(ENDPOINT, async ({ request }) => {
    const body = (await request.json()) as {
      operationName?: string;
      query?: string;
      variables?: Record<string, unknown>;
    };
    const query = body.query ?? "";

    if (query.includes("mutation PublishPost")) {
      const input = (body.variables?.input ?? {}) as Record<string, unknown>;
      return HttpResponse.json({
        data: {
          publishPost: {
            post: {
              id: "post-1",
              title: input.title,
              slug: "test-post-slug",
              url: "https://example.hashnode.dev/test-post",
            },
          },
        },
      });
    }

    if (query.includes("mutation CreateDraft")) {
      const input = (body.variables?.input ?? {}) as Record<string, unknown>;
      return HttpResponse.json({
        data: {
          createDraft: {
            draft: {
              id: "draft-1",
              title: input.title,
              slug: "draft-slug",
            },
          },
        },
      });
    }

    if (query.includes("mutation UpdateDraft")) {
      const id = body.variables?.id as string;
      const input = (body.variables?.input ?? {}) as Record<string, unknown>;
      return HttpResponse.json({
        data: {
          updateDraft: {
            draft: {
              id,
              title: (input.title as string) ?? "Updated Draft",
              slug: "updated-slug",
            },
          },
        },
      });
    }

    if (query.includes("mutation DeleteDraft")) {
      return HttpResponse.json({
        data: {
          deleteDraft: {
            success: true,
          },
        },
      });
    }

    if (query.includes("query GetPublicationPosts")) {
      return HttpResponse.json({
        data: {
          publication: {
            posts: {
              edges: [
                {
                  node: {
                    id: "post-a",
                    title: "Post A",
                    slug: "post-a",
                    url: "https://example.hashnode.dev/post-a",
                    publishedAt: "2024-01-01T00:00:00.000Z",
                    brief: "Brief of post A",
                  },
                },
                {
                  node: {
                    id: "post-b",
                    title: "Post B",
                    slug: "post-b",
                    url: "https://example.hashnode.dev/post-b",
                    publishedAt: "2024-01-02T00:00:00.000Z",
                    brief: "Brief of post B",
                  },
                },
              ],
            },
          },
        },
      });
    }

    if (query.includes("query GetPost")) {
      const id = body.variables?.id as string;
      return HttpResponse.json({
        data: {
          post: {
            id,
            title: "Full Post Title",
            slug: "full-post",
            url: "https://example.hashnode.dev/full-post",
            content: {
              markdown: "# Hello\n\nThis is the full markdown content of the post.",
            },
            publishedAt: "2024-01-15T00:00:00.000Z",
          },
        },
      });
    }

    return HttpResponse.json(
      { errors: [{ message: "Unknown operation" }] },
      { status: 400 }
    );
  }),
];

const mockServer = setupServer(...restHandlers);

describe("HashnodeClient", () => {
  beforeAll(() => {
    mockServer.listen({ onUnhandledRequest: "error" });
  });

  afterAll(() => {
    mockServer.close();
  });

  beforeEach(() => {
    mockServer.resetHandlers();
  });

  it("publishPost_success", async () => {
    const client = new HashnodeClient(TOKEN, PUB_ID);
    const result = await client.publishPost({
      title: "Test Post",
      contentMarkdown: "# Hello\n\nThis is a test post with enough content to satisfy the minimum length requirement for publishing.",
    });
    expect(result.success).toBe(true);
    expect(result.id).toBe("post-1");
    expect(result.title).toBe("Test Post");
    expect(result.url).toBe("https://example.hashnode.dev/test-post");
  });

  it("publishPost_missingToken_throws", () => {
    expect(() => new HashnodeClient("")).toThrow(HashnodeApiError);
    expect(() => new HashnodeClient("   ")).toThrow(HashnodeApiError);
  });

  it("createDraft_success", async () => {
    const client = new HashnodeClient(TOKEN, PUB_ID);
    const draft = await client.createDraft({
      title: "My Draft",
      contentMarkdown: "# Draft content\n\nThis is draft content that is long enough to pass validation rules for the minimum length.",
    });
    expect(draft.id).toBe("draft-1");
    expect(draft.title).toBe("My Draft");
    expect(draft.slug).toBe("draft-slug");
  });

  it("updateDraft_success", async () => {
    const client = new HashnodeClient(TOKEN, PUB_ID);
    const draft = await client.updateDraft("draft-1", {
      title: "Updated Title",
    });
    expect(draft.id).toBe("draft-1");
    expect(draft.title).toBe("Updated Title");
    expect(draft.slug).toBe("updated-slug");
  });

  it("deleteDraft_success", async () => {
    const client = new HashnodeClient(TOKEN, PUB_ID);
    const success = await client.deleteDraft("draft-1");
    expect(success).toBe(true);
  });

  it("readPosts_returnsList", async () => {
    const client = new HashnodeClient(TOKEN, PUB_ID);
    const posts = await client.readPosts();
    expect(Array.isArray(posts)).toBe(true);
    expect(posts.length).toBe(2);
    expect(posts[0].id).toBe("post-a");
    expect(posts[0].title).toBe("Post A");
    expect(posts[0].url).toBeTruthy();
    expect(posts[0].publishedAt).toBeTruthy();
    expect(posts[0].brief).toBeTruthy();
  });

  it("getPost_returnsFull", async () => {
    const client = new HashnodeClient(TOKEN, PUB_ID);
    const post = await client.getPost("post-full-1");
    expect(post.id).toBe("post-full-1");
    expect(post.title).toBe("Full Post Title");
    expect(post.contentMarkdown).toContain("# Hello");
    expect(post.publishedAt).toBeTruthy();
    expect(post.url).toBeTruthy();
  });

  it("publishPost_requiresPublicationId_whenNoDefault", async () => {
    const client = new HashnodeClient(TOKEN);
    await expect(
      client.publishPost({
        title: "No Pub Id",
        contentMarkdown: "# Content that is long enough to pass validation.\n\nMore words here to be safe.",
      })
    ).rejects.toThrow(HashnodeApiError);
  });

  it("updateDraft_requiresFields", async () => {
    const client = new HashnodeClient(TOKEN, PUB_ID);
    await expect(client.updateDraft("draft-x", {})).rejects.toThrow(
      HashnodeApiError
    );
  });
});
