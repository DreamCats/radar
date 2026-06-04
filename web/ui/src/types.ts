export type MessageSource = "个人消息" | "个人群";
export type SourceKey = "personal_message" | "group_message";
export type IngestSource = "all" | SourceKey;

export type MessageItem = {
  message_id: string;
  source: MessageSource;
  sender: string;
  message_time: string;
  raw_content: string;
  fetch_time: string;
  fetch_window: string;
  group_name?: string | null;
};

export type MessagePage = {
  items: MessageItem[];
  next_cursor_time?: string | null;
  next_cursor_id?: string | null;
};

export type MessageConversationItem = {
  key: string;
  title: string;
  source: MessageSource;
  latest_sender: string;
  latest_time: string;
  latest_content: string;
  latest_message_id: string;
};

export type MessageConversationPage = {
  items: MessageConversationItem[];
  next_cursor_time?: string | null;
  next_cursor_key?: string | null;
};

export type MessageGroupItem = {
  group_name: string;
  message_count: number;
  first_seen_at: string;
  last_seen_at: string;
};

export type MessageQuery = {
  source?: string;
  group_name?: string;
  sender?: string;
  keyword?: string;
  start_time?: string;
  end_time?: string;
  cursor_time?: string;
  cursor_id?: string;
  limit?: number;
};

export type MessageConversationQuery = Omit<MessageQuery, "cursor_id" | "sender"> & {
  cursor_key?: string;
};

export type RunItem = {
  run_id: string;
  kind: string;
  target: string;
  started_at: string;
  finished_at?: string | null;
  status: "running" | "succeeded" | "skipped" | "failed";
  raw_count: number;
  stored_count: number;
  filtered_count: number;
  error_message?: string | null;
  metadata: Record<string, unknown>;
};

export type IngestRequest = {
  source: IngestSource;
  start_time: string;
  end_time: string;
  force: boolean;
  chunk_hours: number;
  concurrency: number;
};

export type IngestResultItem = {
  source_key: SourceKey;
  source: MessageSource;
  chunk_count: number;
  skipped_count: number;
  raw_count: number;
  filtered_count: number;
  stored_count: number;
  run_id?: string | null;
};

export type IngestJobItem = {
  source_key: SourceKey;
  source: MessageSource;
  run_id: string;
  reused_existing: boolean;
  status: "running";
};
