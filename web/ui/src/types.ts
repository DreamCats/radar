export type MessageSource = "个人消息" | "个人群";
export type SourceKey = "personal_message" | "group_message";
export type IngestSource = "all" | SourceKey;
export type MessageCategory = "research" | "recommendation" | "event" | "industry" | "tool_ad" | "chat" | "unknown";
export type ClassificationRetryMode = "needs_review" | "unknown" | "low_confidence";

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

export type MessageOverviewSummary = {
  total_count: number;
  group_message_count: number;
  personal_message_count: number;
  group_count: number;
  sender_count: number;
  first_message_time?: string | null;
  latest_message_time?: string | null;
};

export type MessageOverviewBucket = {
  date: string;
  total_count: number;
  group_message_count: number;
  personal_message_count: number;
};

export type MessageOverviewSource = {
  source: MessageSource;
  count: number;
};

export type MessageOverviewGroup = {
  group_name: string;
  count: number;
  last_message_time: string;
};

export type MessageOverviewHour = {
  hour: number;
  count: number;
};

export type MessageOverview = {
  summary: MessageOverviewSummary;
  date_buckets: MessageOverviewBucket[];
  source_breakdown: MessageOverviewSource[];
  top_groups: MessageOverviewGroup[];
  hourly_buckets: MessageOverviewHour[];
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

export type ClassifyRequest = {
  source: IngestSource;
  start_time: string;
  end_time: string;
  force: boolean;
  chunk_hours: number;
  limit: number;
  batch_size: number;
  max_concurrency: number;
  retry?: ClassificationRetryMode;
  low_confidence_threshold: number;
};

export type ClassifyJobItem = {
  source_key: IngestSource;
  source: string;
  run_id: string;
  reused_existing: boolean;
  status: "running";
};

export type OrganizeEvidenceMessage = {
  message_id: string;
  source: MessageSource;
  sender: string;
  group_name?: string | null;
  message_time: string;
  raw_content: string;
  category: MessageCategory;
  confidence: number;
  reason: string;
  status: string;
};

export type OrganizeClassificationCluster = {
  category: MessageCategory;
  label: string;
  count: number;
  average_confidence: number;
  low_confidence_count: number;
  latest_time: string;
  evidence: OrganizeEvidenceMessage[];
};

export type OrganizeClassificationSummary = {
  classified_count: number;
  total_count: number;
  cluster_count: number;
  low_confidence_count: number;
  noise_count: number;
  hidden_count: number;
  average_confidence: number;
};

export type OrganizeClassificationPage = {
  summary: OrganizeClassificationSummary;
  clusters: OrganizeClassificationCluster[];
};

export type OrganizeClassificationQuery = {
  source?: SourceKey;
  keyword?: string;
  start_time?: string;
  end_time?: string;
  evidence_limit?: number;
  low_confidence_threshold?: number;
};

export type OrganizeEvidencePage = {
  items: OrganizeEvidenceMessage[];
  next_cursor_time?: string | null;
  next_cursor_id?: string | null;
};

export type OrganizeEvidenceQuery = Omit<OrganizeClassificationQuery, "evidence_limit"> & {
  category: MessageCategory;
  cursor_time?: string;
  cursor_id?: string;
  limit?: number;
};
