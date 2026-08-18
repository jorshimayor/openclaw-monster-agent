export interface PostSummary {
  id: string;
  title: string;
  slug: string;
  url: string;
  publishedAt?: string;
  brief?: string;
}

export interface FullPost extends PostSummary {
  contentMarkdown?: string;
}

export interface PublishResult {
  success: boolean;
  id?: string;
  title?: string;
  url?: string;
  error?: string;
}

export type DraftAction = "create" | "update" | "delete" | "get";

export interface TagInput {
  name: string;
  slug?: string;
}

export interface PublishPostInput {
  title: string;
  contentMarkdown: string;
  publicationId?: string;
  tags?: TagInput[];
  coverImageUrl?: string;
  subtitle?: string;
}

export interface Draft {
  id: string;
  title: string;
  slug: string;
  contentMarkdown?: string;
}
