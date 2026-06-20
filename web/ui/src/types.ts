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

export type DashboardSummary = {
  overview: MessageOverview;
  classifications: OrganizeClassificationPage;
  backtest: RecommendationBacktestSummary;
  runs: RunItem[];
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

export type ChatSessionList = {
  items: ChatSessionItem[];
};

export type ChatSessionDetail = {
  session: ChatSessionItem;
  messages: ChatMessageItem[];
};

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
  | { type: "session"; session_id: string }
  | { type: "user_message"; message: ChatMessageItem }
  | { type: "assistant_reasoning_delta"; content: string }
  | { type: "assistant_delta"; content: string }
  | { type: "assistant_message"; message: ChatMessageItem }
  | { type: "tool_message"; message: ChatMessageItem }
  | { type: "agent_event"; event: Record<string, unknown> }
  | { type: "error"; message: string; status_code?: number };

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

export type {
  AnchorRequest,
  ClassifyJobItem,
  ClassifyRequest,
  DerivedJobItem,
  IngestJobItem,
  IngestRequest,
  IngestResultItem,
  LifecycleDigestJobRequest,
  RecommendationBacktestRequest,
  StockEvidenceChainJobRequest,
} from "./types/jobs";

export type BacktestGroupBy =
  | "source"
  | "source_stock"
  | "stock"
  | "analyst"
  | "analyst_stock"
  | "sector"
  | "analyst_sector";

export type RecommendationBacktestSummaryRow = {
  key: string;
  source_candidate?: string | null;
  analyst_id?: string | null;
  analyst_display_name?: string | null;
  ts_code?: string | null;
  stock_name?: string | null;
  sector_anchor_type?: string | null;
  sector_name?: string | null;
  event_count: number;
  metrics: Record<string, number>;
};

export type RecommendationBacktestSummary = {
  start_time: string;
  end_time: string;
  group_by: BacktestGroupBy;
  windows: number[];
  row_count: number;
  rows: RecommendationBacktestSummaryRow[];
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

export type {
  StockEvidenceChainDashboard,
  StockEvidenceChainItem,
  StockEvidenceChainSnapshot,
  StockEvidenceChainSnapshotList,
  StockEvidenceFinancialMetric,
  StockEvidenceFinancials,
  StockEvidenceLifecycleDigestContext,
  StockEvidenceMarketPoint,
  StockEvidenceMarketValidation,
  StockEvidenceMessage,
  StockEvidenceRecognitionContext,
  StockEvidenceReviewContext,
  StockEvidenceStockCandle,
  StockEvidenceStockChart,
  StockEvidenceStockChartQuery,
  StockEvidenceThemeContext,
  LifecycleDigestHashes,
  LifecycleDigestPreview,
  LifecycleDigestPreviewItem,
} from "./types/strategy";
