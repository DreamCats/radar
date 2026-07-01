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

export type CatalystCategory = {
  id: string;
  name: string;
  color: string;
  terms: string[];
};

export type CatalystTermLibrary = {
  version: number;
  categories: CatalystCategory[];
};

export type CatalystTermHit = {
  category_id: string;
  category_name: string;
  color: string;
  term: string;
};

export type CatalystStockMention = {
  ts_code?: string | null;
  stock_name: string;
};

export type CatalystDuplicateSource = {
  message_id: string;
  source: MessageSource;
  sender: string;
  group_name?: string | null;
  message_time: string;
  latest_message_time?: string | null;
  message_count: number;
};

export type CatalystEvidenceMessage = {
  message_id: string;
  message_time: string;
  raw_content: string;
  matched_terms: CatalystTermHit[];
};

export type CatalystFeedItem = {
  key: string;
  message_id: string;
  source: MessageSource;
  sender: string;
  group_name?: string | null;
  first_message_time: string;
  latest_message_time: string;
  raw_content: string;
  normalized_content_hash: string;
  message_count: number;
  messages: CatalystEvidenceMessage[];
  matched_terms: CatalystTermHit[];
  stock_mentions: CatalystStockMention[];
  duplicate_count: number;
  duplicate_sources: CatalystDuplicateSource[];
};

export type CatalystFeedSummary = {
  total_items: number;
  total_messages: number;
  duplicate_messages: number;
  available_total_items: number;
  category_counts: Record<string, number>;
  term_counts: Record<string, Record<string, number>>;
};

export type CatalystFeedPage = {
  items: CatalystFeedItem[];
  summary: CatalystFeedSummary;
  next_cursor_time?: string | null;
  next_cursor_key?: string | null;
};

export type CatalystFeedQuery = {
  start_time: string;
  end_time: string;
  source?: string;
  group_name?: string;
  category_ids?: string[];
  keyword?: string;
  term_category_id?: string;
  term?: string;
  dedupe?: boolean;
  cursor_time?: string | null;
  cursor_key?: string | null;
  limit?: number;
};

export type CatalystValuationEvidence = {
  message_id: string;
  source: MessageSource;
  sender: string;
  group_name?: string | null;
  message_time: string;
  latest_message_time: string;
  content: string;
  matched_terms: string[];
  valuation_terms: string[];
  valuation_numbers: string[];
  stock_mentions_count: number;
  duplicate_count: number;
};

export type CatalystValuationStockContext = {
  stock_key: string;
  ts_code?: string | null;
  stock_name: string;
  first_message_time: string;
  latest_message_time: string;
  evidence: CatalystValuationEvidence[];
};

export type CatalystValuationReportData = {
  generated_at: string;
  start_time: string;
  end_time: string;
  total_feed_items: number;
  total_candidate_stocks: number;
  total_stocks: number;
  stocks: CatalystValuationStockContext[];
};

export type CatalystValuationReportStockSummary = {
  stock_key: string;
  ts_code?: string | null;
  stock_name: string;
  evidence_count: number;
  latest_message_time: string;
};

export type ReportNotificationRecord = {
  notification_id: string;
  report_id: string;
  channel: string;
  status: "succeeded" | "failed";
  sent_at: string;
  error_message?: string | null;
  created_at: string;
};

export type CatalystValuationReportArchiveItem = {
  report_id: string;
  run_id?: string | null;
  kind: string;
  status: "succeeded" | "skipped" | "partial_failed" | "failed";
  generated_at: string;
  start_time: string;
  end_time: string;
  granularity_minutes?: number | null;
  local_html_path: string;
  published_url?: string | null;
  total_feed_items: number;
  total_candidate_stocks: number;
  total_stocks: number;
  bark_sent_at?: string | null;
  bark_error?: string | null;
  upside_chat_run_id?: string | null;
  upside_chat_session_id?: string | null;
  upside_chat_status?: "running" | "completed" | "failed" | "cancelled" | null;
  upside_chat_updated_at?: string | null;
  upside_chat_error?: string | null;
  top_stocks: CatalystValuationReportStockSummary[];
  created_at: string;
  updated_at: string;
};

export type CatalystValuationReportArchiveDetail = CatalystValuationReportArchiveItem & {
  request: Record<string, unknown>;
  report: CatalystValuationReportData;
  rendered_html: string;
  notifications: ReportNotificationRecord[];
};

export type CatalystValuationReportListResponse = {
  items: CatalystValuationReportArchiveItem[];
};

export type CatalystValuationReportDetailResponse = {
  item: CatalystValuationReportArchiveDetail;
};

export type CatalystValuationReportNotifyResponse = {
  item: CatalystValuationReportArchiveDetail;
  notification: ReportNotificationRecord;
};

export type PremarketSignalQuery = {
  start_time: string;
  end_time: string;
  limit?: number;
};

export type PremarketEvidence = {
  message_id: string;
  source: MessageSource;
  sender: string;
  group_name?: string | null;
  message_time: string;
  raw_content: string;
  matched_terms: CatalystTermHit[];
  stock_mentions: CatalystStockMention[];
};

export type PremarketStockRank = {
  ts_code?: string | null;
  stock_name: string;
  mention_count: number;
  person_count: number;
  message_count: number;
  first_time: string;
  latest_time: string;
  catalyst_terms: CatalystTermHit[];
};

export type PremarketConceptSource = "ths" | "dc" | "none";

export type PremarketConceptRank = {
  concept_code: string;
  concept_name: string;
  source: PremarketConceptSource;
  score: number;
  velocity_score: number;
  early_mention_count: number;
  late_mention_count: number;
  stock_count: number;
  mention_count: number;
  person_count: number;
  message_count: number;
  top_stocks: PremarketStockRank[];
  catalyst_terms: CatalystTermHit[];
  evidence: PremarketEvidence[];
};

export type PremarketSignalSummary = {
  start_time: string;
  end_time: string;
  messages_scanned: number;
  catalyst_items: number;
  stock_mentions: number;
  dedup_person_stock_mentions: number;
  concept_source: PremarketConceptSource;
  concept_count: number;
  ranked_concept_count: number;
};

export type PremarketConcentrationItem = {
  concept_count: number;
  covered_dedup_person_stock_mentions: number;
  total_dedup_person_stock_mentions: number;
  coverage_pct: number;
};

export type PremarketTimeBucket = {
  start_time: string;
  end_time: string;
  catalyst_items: number;
  dedup_person_stock_mentions: number;
};

export type PremarketSignalResult = {
  query: PremarketSignalQuery;
  summary: PremarketSignalSummary;
  concepts: PremarketConceptRank[];
  top_concepts: PremarketConceptRank[];
  bottom_concepts: PremarketConceptRank[];
  velocity_concepts: PremarketConceptRank[];
  concentration: PremarketConcentrationItem[];
  time_buckets: PremarketTimeBucket[];
};

export type IndustryChainEvidenceStatus = "supported" | "weakly_supported" | "candidate" | "unsupported";

export type IndustryChainIndexItem = {
  chain_id: string;
  title: string;
  category: string;
  aliases: string[];
  status: string;
  sort_order: number;
  content_path: string;
  data_path: string;
  updated_at: string;
  entry_tags: string[];
  audience_level?: string | null;
  evidence_level?: string | null;
  summary: string;
};

export type IndustryChainList = {
  version: number;
  updated_at: string;
  items: IndustryChainIndexItem[];
};

export type IndustryChainNode = {
  id: string;
  label: string;
  layer: string;
  group: string;
  beginner_explanation: string;
  bottleneck_strength: number;
  evidence_status: IndustryChainEvidenceStatus;
  teach?: IndustryChainNodeTeach | null;
};

export type IndustryChainNodeTeach = {
  what: string;
  why_matters: string;
  benefit_logic: string;
  watch: string[];
  common_misread: string;
};

export type IndustryChainEdge = {
  source: string;
  target: string;
  relation_type: string;
  label: string;
  description: string;
  evidence_status: IndustryChainEvidenceStatus;
};

export type IndustryChainCompany = {
  name: string;
  ts_code: string;
  nodes: string[];
  role: string;
  tier: string;
  attention_level?: "leader" | "core_candidate" | "watch" | "candidate" | null;
  attention_label?: string | null;
  leader_reason?: string | null;
  current_view: string;
  evidence_status: IndustryChainEvidenceStatus;
  next_checks: string[];
  why_watch?: string | null;
  evidence_basis?: string[];
  verification_focus?: string[];
  risks?: string[];
  evidence_refs?: IndustryChainEvidenceRef[];
};

export type IndustryChainEvidenceRef = {
  title: string;
  publisher: string;
  date?: string | null;
  url?: string | null;
  evidence_grade?: string | null;
  usage: string;
};

export type IndustryChainQuickRead = {
  headline: string;
  summary: string;
  logic_chain: string[];
  takeaways: string[];
};

export type IndustryChainCommonMisread = {
  title: string;
  correction: string;
};

export type IndustryChainFinancialTranslation = {
  node_id: string;
  title: string;
  watch: string;
  source_hint: string;
  risk?: string | null;
};

export type IndustryChainCatalyst = {
  horizon: string;
  title: string;
  why: string;
  watch: string;
  risk?: string | null;
};

export type IndustryChainConceptDiagramPart = {
  label: string;
  role: string;
  description: string;
};

export type IndustryChainConceptDiagram = {
  id: string;
  title: string;
  subtitle: string;
  icon?: "wind" | "liquid" | "chip" | "control" | "connector" | "system" | null;
  node_ids: string[];
  takeaway: string;
  parts: IndustryChainConceptDiagramPart[];
};

export type IndustryChainEvidencePolicyLabel = {
  status: IndustryChainEvidenceStatus;
  label: string;
  meaning: string;
  evidence_needed: string;
};

export type IndustryChainEvidencePolicy = {
  default_status: IndustryChainEvidenceStatus;
  status_values: IndustryChainEvidenceStatus[];
  upgrade_rule: string;
  labels?: IndustryChainEvidencePolicyLabel[];
};

export type IndustryChainTrackingMetric = {
  name: string;
  why: string;
  source_hint: string;
};

export type IndustryChainSource = {
  title: string;
  publisher: string;
  date?: string | null;
  url?: string | null;
  source_type: string;
  usage: string;
};

export type IndustryChainLearningStep = {
  id: string;
  title: string;
  subtitle: string;
  question: string;
  answer: string;
  node_ids: string[];
};

export type IndustryChainFlowColumn = {
  key: string;
  label: string;
  description: string;
  node_ids: string[];
};

export type IndustryChainData = {
  version: number;
  chain_id: string;
  title: string;
  category: string;
  status: string;
  updated_at: string;
  summary: string;
  quick_read?: IndustryChainQuickRead | null;
  learning_steps?: IndustryChainLearningStep[];
  evidence_policy?: IndustryChainEvidencePolicy | null;
  flow_columns?: IndustryChainFlowColumn[];
  nodes: IndustryChainNode[];
  edges: IndustryChainEdge[];
  companies: IndustryChainCompany[];
  concept_diagrams?: IndustryChainConceptDiagram[];
  common_misreads?: IndustryChainCommonMisread[];
  financial_translations?: IndustryChainFinancialTranslation[];
  catalysts?: IndustryChainCatalyst[];
  tracking_metrics: IndustryChainTrackingMetric[];
  sources: IndustryChainSource[];
};

export type IndustryChainDetail = {
  item: IndustryChainIndexItem;
  data: IndustryChainData;
  content_markdown: string;
};

export type AuthStatus = {
  auth_required: boolean;
  authenticated: boolean;
  username?: string | null;
};

export type ChatTurnRequest = {
  session_id?: string | null;
  title?: string | null;
  content: string;
  provider_name?: string | null;
  context?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

export type ChatContinueRequest = {
  provider_name?: string | null;
};

export type ChatMessageItem = {
  message_id: string;
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  created_at: string;
  metadata: Record<string, unknown>;
};

export type ChatTurnResponse = {
  session_id: string;
  user_message: ChatMessageItem;
  assistant_message: ChatMessageItem;
  tool_messages: ChatMessageItem[];
};

export type ChatRunItem = {
  run_id: string;
  session_id: string;
  status: "running" | "completed" | "failed" | "cancelled";
  created_at: string;
  updated_at: string;
  display_title?: string | null;
  display_subtitle?: string | null;
  last_seq: number;
  cancel_requested: boolean;
  error?: string | null;
  metadata: Record<string, unknown>;
};

export type ChatRunResponse = {
  run: ChatRunItem;
};

export type ChatActiveRunResponse = {
  run?: ChatRunItem | null;
};

export type ChatRunListResponse = {
  items: ChatRunItem[];
};

export type ChatSessionItem = {
  session_id: string;
  created_at: string;
  updated_at: string;
  title?: string | null;
  metadata: Record<string, unknown>;
  message_count: number;
  preview: string;
  can_continue: boolean;
};

export type ChatSessionDetail = {
  session: ChatSessionItem;
  messages: ChatMessageItem[];
};

export type ChatToolMessageDetail = ChatMessageItem;

export type ChatModelOption = {
  provider_name: string;
  label: string;
  protocol: "openai" | "anthropic";
  model: string;
  context_window_tokens: number;
  is_default: boolean;
  thinking_enabled: boolean;
};

export type ChatModelOptions = {
  default_provider_name?: string | null;
  items: ChatModelOption[];
};

export type ChatStreamEvent =
  | { type: "ping"; sequence_number?: number; run_id?: string }
  | { type: "session"; session_id: string; sequence_number?: number; run_id?: string }
  | { type: "user_message"; message: ChatMessageItem; sequence_number?: number; run_id?: string }
  | { type: "assistant_reasoning_delta"; content: string; sequence_number?: number; run_id?: string }
  | { type: "assistant_candidate_delta"; content: string; sequence_number?: number; run_id?: string }
  | { type: "assistant_candidate_commit"; content: string; sequence_number?: number; run_id?: string }
  | { type: "assistant_candidate_discard"; content: string; sequence_number?: number; run_id?: string }
  | { type: "assistant_progress_delta"; content: string; sequence_number?: number; run_id?: string }
  | { type: "assistant_delta"; content: string; sequence_number?: number; run_id?: string }
  | { type: "assistant_message"; message: ChatMessageItem; sequence_number?: number; run_id?: string }
  | { type: "tool_message"; message: ChatMessageItem; sequence_number?: number; run_id?: string }
  | { type: "agent_event"; event: Record<string, unknown>; sequence_number?: number; run_id?: string }
  | { type: "error"; message: string; status_code?: number; sequence_number?: number; run_id?: string };

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
  status: "running" | "succeeded" | "skipped" | "partial_failed" | "failed";
  raw_count: number;
  stored_count: number;
  filtered_count: number;
  error_message?: string | null;
  metadata: Record<string, unknown>;
};

export type AnalystBacktestSummaryRow = {
  analyst_id: string;
  analyst_display_name: string;
  event_count: number;
  latest_event_time?: string | null;
  metrics: Record<string, number>;
};

export type AnalystBacktestSummary = {
  start_time: string;
  end_time: string;
  windows: number[];
  row_count: number;
  rows: AnalystBacktestSummaryRow[];
};

export type AnalystBacktestEvidenceItem = {
  mention_id: string;
  message_id: string;
  analyst_id: string;
  analyst_display_name: string;
  ts_code: string;
  stock_name: string;
  message_time: string;
  evidence_snippet: string;
  stock_count_in_message: number;
  quality_flags: string[];
  window_days: number;
  status?: "pending" | "succeeded" | "missing_price" | "failed" | null;
  target_trade_date?: string | null;
  return_rate?: number | null;
  positive?: boolean | null;
  excess_return_rate?: number | null;
};

export type AnalystBacktestEvidence = {
  start_time: string;
  end_time: string;
  window_days: number;
  row_count: number;
  rows: AnalystBacktestEvidenceItem[];
};

export type AnalystBacktestMessageEvidenceItem = {
  message_id: string;
  analyst_id: string;
  analyst_display_name: string;
  message_time: string;
  raw_content: string;
  stock_count: number;
  mentioned_stock_count: number;
  quality_flags: string[];
  window_days: number;
  metrics: Record<string, number>;
  items: AnalystBacktestEvidenceItem[];
};

export type AnalystBacktestMessageEvidence = {
  start_time: string;
  end_time: string;
  window_days: number;
  row_count: number;
  rows: AnalystBacktestMessageEvidenceItem[];
};

export type {
  AnalystBacktestRequest,
  CatalystValuationReportJobRequest,
  DerivedJobItem,
  IngestJobItem,
  IngestRequest,
  IngestResultItem,
  MarketStockRefreshRequest,
  ScheduleItem,
  ScheduleTickItem,
  ThsConceptRefreshRequest,
} from "./types/jobs";
