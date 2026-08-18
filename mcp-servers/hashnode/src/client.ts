import { GraphQLClient, gql } from "graphql-request";
import { z } from "zod";
import type {
  PostSummary,
  FullPost,
  PublishResult,
  PublishPostInput,
  Draft,
} from "./types.js";

export class HashnodeApiError extends Error {
  public readonly statusCode?: number;
  public readonly errors?: unknown[];

  constructor(message: string, options?: { statusCode?: number; errors?: unknown[] }) {
    super(message);
    this.name = "HashnodeApiError";
    this.statusCode = options?.statusCode;
    this.errors = options?.errors;
  }
}

const PUBLISH_POST_MUTATION = gql`
  mutation PublishPost($input: PublishPostInput!) {
    publishPost(input: $input) {
      post {
        id
        title
        slug
        url
      }
    }
  }
`;

const CREATE_DRAFT_MUTATION = gql`
  mutation CreateDraft($input: CreateDraftInput!) {
    createDraft(input: $input) {
      draft {
        id
        title
        slug
      }
    }
  }
`;

const UPDATE_DRAFT_MUTATION = gql`
  mutation UpdateDraft($id: ObjectId!, $input: UpdateDraftInput!) {
    updateDraft(id: $id, input: $input) {
      draft {
        id
        title
        slug
      }
    }
  }
`;

const DELETE_DRAFT_MUTATION = gql`
  mutation DeleteDraft($id: ObjectId!) {
    deleteDraft(id: $id) {
      success
    }
  }
`;

const GET_PUBLICATION_POSTS_QUERY = gql`
  query GetPublicationPosts($publicationId: ObjectId!, $first: Int = 10) {
    publication(id: $publicationId) {
      posts(first: $first) {
        edges {
          node {
            id
            title
            slug
            url
            publishedAt
            brief
          }
        }
      }
    }
  }
`;

const GET_POST_QUERY = gql`
  query GetPost($id: ObjectId!) {
    post(id: $id) {
      id
      title
      slug
      url
      content {
        markdown
      }
      publishedAt
    }
  }
`;

const tagInputSchema = z.object({
  name: z.string().min(1),
  slug: z.string().min(1).optional(),
});

const publishPostInputSchema = z.object({
  title: z.string().min(3).max(200),
  contentMarkdown: z.string().min(50),
  publicationId: z.string().min(1).optional(),
  tags: z.array(tagInputSchema).optional(),
  coverImageUrl: z.string().url().optional(),
  subtitle: z.string().optional(),
});

export class HashnodeClient {
  private readonly gqlClient: GraphQLClient;
  private readonly defaultPublicationId?: string;
  public static readonly endpoint = "https://gql.hashnode.com";

  constructor(token: string, defaultPublicationId?: string) {
    if (!token || token.trim().length === 0) {
      throw new HashnodeApiError("Hashnode token is required");
    }
    this.defaultPublicationId = defaultPublicationId;
    this.gqlClient = new GraphQLClient(HashnodeClient.endpoint, {
      headers: {
        Authorization: token,
      },
    });
  }

  private resolvePublicationId(provided?: string): string {
    const id = provided ?? this.defaultPublicationId;
    if (!id) {
      throw new HashnodeApiError(
        "publicationId is required (either pass it explicitly or set HASHNODE_PUBLICATION_ID)"
      );
    }
    return id;
  }

  private buildGqlPublishInput(input: PublishPostInput) {
    const publicationId = this.resolvePublicationId(input.publicationId);
    const gqlInput: Record<string, unknown> = {
      title: input.title,
      contentMarkdown: input.contentMarkdown,
      publicationId,
    };
    if (input.tags && input.tags.length > 0) {
      gqlInput.tags = input.tags.map((t) => ({
        name: t.name,
        ...(t.slug ? { slug: t.slug } : {}),
      }));
    }
    if (input.coverImageUrl) {
      gqlInput.coverImageOptions = {
        coverImageURL: input.coverImageUrl,
      };
    }
    if (input.subtitle) {
      gqlInput.subtitle = input.subtitle;
    }
    return gqlInput;
  }

  public async publishPost(input: PublishPostInput): Promise<PublishResult> {
    const validated = publishPostInputSchema.parse(input);
    try {
      const gqlInput = this.buildGqlPublishInput(validated);
      const response = await this.gqlClient.request<{
        publishPost: { post: { id: string; title: string; slug: string; url: string } };
      }>(PUBLISH_POST_MUTATION, { input: gqlInput });

      const post = response.publishPost?.post;
      if (!post) {
        throw new HashnodeApiError("Publish succeeded but no post returned");
      }
      return {
        success: true,
        id: post.id,
        title: post.title,
        url: post.url,
      };
    } catch (err) {
      if (err instanceof HashnodeApiError) throw err;
      const message = err instanceof Error ? err.message : "Unknown error publishing post";
      throw new HashnodeApiError(message, { errors: [err] });
    }
  }

  public async createDraft(input: PublishPostInput): Promise<Draft> {
    const validated = publishPostInputSchema.parse(input);
    try {
      const gqlInput = this.buildGqlPublishInput(validated);
      const response = await this.gqlClient.request<{
        createDraft: { draft: { id: string; title: string; slug: string } };
      }>(CREATE_DRAFT_MUTATION, { input: gqlInput });

      const draft = response.createDraft?.draft;
      if (!draft) {
        throw new HashnodeApiError("Create draft succeeded but no draft returned");
      }
      return draft;
    } catch (err) {
      if (err instanceof HashnodeApiError) throw err;
      const message = err instanceof Error ? err.message : "Unknown error creating draft";
      throw new HashnodeApiError(message, { errors: [err] });
    }
  }

  public async updateDraft(
    id: string,
    input: Partial<PublishPostInput>
  ): Promise<Draft> {
    const idSchema = z.string().min(1, "draftId is required");
    const updateSchema = publishPostInputSchema.partial();
    const validId = idSchema.parse(id);
    const validated = updateSchema.parse(input);

    if (Object.keys(validated).length === 0) {
      throw new HashnodeApiError("At least one field must be provided for update");
    }

    try {
      const gqlInput: Record<string, unknown> = {};
      if (validated.title) gqlInput.title = validated.title;
      if (validated.contentMarkdown) gqlInput.contentMarkdown = validated.contentMarkdown;
      if (validated.publicationId) gqlInput.publicationId = validated.publicationId;
      if (validated.subtitle) gqlInput.subtitle = validated.subtitle;
      if (validated.tags && validated.tags.length > 0) {
        gqlInput.tags = validated.tags.map((t) => ({
          name: t!.name,
          ...(t!.slug ? { slug: t!.slug } : {}),
        }));
      }
      if (validated.coverImageUrl) {
        gqlInput.coverImageOptions = { coverImageURL: validated.coverImageUrl };
      }

      const response = await this.gqlClient.request<{
        updateDraft: { draft: { id: string; title: string; slug: string } };
      }>(UPDATE_DRAFT_MUTATION, { id: validId, input: gqlInput });

      const draft = response.updateDraft?.draft;
      if (!draft) {
        throw new HashnodeApiError("Update draft succeeded but no draft returned");
      }
      return draft;
    } catch (err) {
      if (err instanceof HashnodeApiError) throw err;
      const message = err instanceof Error ? err.message : "Unknown error updating draft";
      throw new HashnodeApiError(message, { errors: [err] });
    }
  }

  public async deleteDraft(id: string): Promise<boolean> {
    const idSchema = z.string().min(1, "draftId is required");
    const validId = idSchema.parse(id);
    try {
      const response = await this.gqlClient.request<{
        deleteDraft: { success: boolean };
      }>(DELETE_DRAFT_MUTATION, { id: validId });
      return response.deleteDraft?.success ?? false;
    } catch (err) {
      if (err instanceof HashnodeApiError) throw err;
      const message = err instanceof Error ? err.message : "Unknown error deleting draft";
      throw new HashnodeApiError(message, { errors: [err] });
    }
  }

  public async readPosts(
    publicationId?: string,
    first: number = 10
  ): Promise<PostSummary[]> {
    const resolvedPubId = this.resolvePublicationId(publicationId);
    const firstSchema = z.number().int().min(1).max(50);
    const validFirst = firstSchema.parse(first);

    try {
      const response = await this.gqlClient.request<{
        publication: {
          posts: {
            edges: {
              node: {
                id: string;
                title: string;
                slug: string;
                url: string;
                publishedAt?: string;
                brief?: string;
              };
            }[];
          };
        };
      }>(GET_PUBLICATION_POSTS_QUERY, {
        publicationId: resolvedPubId,
        first: validFirst,
      });

      const edges = response.publication?.posts?.edges ?? [];
      return edges.map((e) => ({
        id: e.node.id,
        title: e.node.title,
        slug: e.node.slug,
        url: e.node.url,
        publishedAt: e.node.publishedAt,
        brief: e.node.brief,
      }));
    } catch (err) {
      if (err instanceof HashnodeApiError) throw err;
      const message = err instanceof Error ? err.message : "Unknown error reading posts";
      throw new HashnodeApiError(message, { errors: [err] });
    }
  }

  public async getPost(id: string): Promise<FullPost> {
    const idSchema = z.string().min(1, "postId is required");
    const validId = idSchema.parse(id);

    try {
      const response = await this.gqlClient.request<{
        post: {
          id: string;
          title: string;
          slug: string;
          url: string;
          content?: { markdown?: string };
          publishedAt?: string;
        };
      }>(GET_POST_QUERY, { id: validId });

      const post = response.post;
      if (!post) {
        throw new HashnodeApiError(`Post with id ${validId} not found`);
      }

      return {
        id: post.id,
        title: post.title,
        slug: post.slug,
        url: post.url,
        contentMarkdown: post.content?.markdown,
        publishedAt: post.publishedAt,
      };
    } catch (err) {
      if (err instanceof HashnodeApiError) throw err;
      const message = err instanceof Error ? err.message : "Unknown error fetching post";
      throw new HashnodeApiError(message, { errors: [err] });
    }
  }
}
