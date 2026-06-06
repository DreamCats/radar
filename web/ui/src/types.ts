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

export type MessageAnchorHeat = {
  name: string;
  anchor_type: "stock" | "concept" | "industry" | "theme";
  mention_count: number;
  message_count: number;
  high_value_count: number;
  average_confidence: number;
  latest_message_time: string;
};

export type MessageOverview = {
  summary: MessageOverviewSummary;
  date_buckets: MessageOverviewBucket[];
  source_breakdown: MessageOverviewSource[];
  top_groups: MessageOverviewGroup[];
  hourly_buckets: MessageOverviewHour[];
  anchor_heat: MessageAnchorHeat[];
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

export type AnchorRequest = {
  trade_date: string;
  source: IngestSource;
  start_time: string;
  end_time: string;
  force: boolean;
  chunk_hours: number;
  limit: number;
  categories: MessageCategory[];
  min_classification_confidence: number;
  max_anchors: number;
};

export type AggregateRefineRequest = {
  trade_date: string;
  source: IngestSource;
  start_time: string;
  end_time: string;
  force: boolean;
  categories: MessageCategory[];
  min_classification_confidence: number;
  min_messages: number;
  candidate_limit: number;
  evidence_limit: number;
  batch_size: number;
  max_concurrency: number;
};

export type RecommendationBacktestRequest = {
  as_of: string;
  window_days: number;
  start_time: string;
  end_time: string;
  windows: number[];
  source: IngestSource;
  min_classification_confidence: number;
  benchmark_ts_code: string;
  force: boolean;
};

export type DerivedJobItem = {
  job_type: "anchor" | "aggregate_refine" | "recommendation_backtest";
  run_id: string;
  reused_existing: boolean;
  status: "running";
};

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

export type RefinedThemeStock = {
  name: string;
  reason: string;
  confidence: number;
};

export type RefinedTheme = {
  theme_name: string;
  aliases: string[];
  summary: string;
  investment_logic: string;
  catalysts: string[];
  related_stocks: RefinedThemeStock[];
  evidence_message_ids: string[];
  novelty: string;
  confidence: number;
  actionability_score: number;
  risk_notes: string[];
  merge_from_candidate_ids: string[];
};

export type AggregateRefineResult = {
  run_id: string;
  input_hash: string;
  status: string;
  trade_date: string;
  extractor_version: string;
  prompt_version: string;
  candidate_count: number;
  theme_count: number;
  llm_batch_count: number;
  failed_llm_batches: number;
  max_concurrency: number;
  themes: RefinedTheme[];
};

export type OrganizeAggregateSummary = {
  run_id: string;
  input_hash: string;
  status: string;
  trade_date: string;
  start_time: string;
  end_time: string;
  candidate_count: number;
  theme_count: number;
  llm_batch_count: number;
  failed_llm_batches: number;
  max_concurrency: number;
  evidence_message_count: number;
};

export type OrganizeAggregateTheme = RefinedTheme & {
  theme_index: number;
  priority_score: number;
  evidence: OrganizeEvidenceMessage[];
};

export type OrganizeAggregatePage = {
  result?: OrganizeAggregateSummary | null;
  themes: OrganizeAggregateTheme[];
};

export type OrganizeAggregateQuery = {
  source?: SourceKey;
  keyword?: string;
  start_time?: string;
  end_time?: string;
  evidence_limit?: number;
};

export type OrganizeAggregateEvidencePage = {
  items: OrganizeEvidenceMessage[];
  next_cursor_time?: string | null;
  next_cursor_id?: string | null;
};

export type OrganizeAggregateEvidenceQuery = Omit<OrganizeAggregateQuery, "evidence_limit"> & {
  run_id: string;
  theme_index: number;
  cursor_time?: string;
  cursor_id?: string;
  limit?: number;
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

export type StrategyAttentionLevel = "重点关注" | "继续验证" | "风险升高" | "样本不足" | "过度扩散";
export type StrategyStockLifecycleState = "初现" | "发酵中" | "已兑现" | "回调再看" | "缺少价格";
export type StrategyStockPricePosition = "趋势健康" | "可观察" | "震荡观察" | "回撤偏大" | "短线偏弱" | "首现后走弱" | "缺少价格";

export type StrategyRelatedStock = {
  stock_name: string;
  ts_code: string;
  event_count: number;
  source_count: number;
  win_rate_t5?: number | null;
  average_excess_return_t5?: number | null;
  first_seen_time?: string | null;
  latest_message_time?: string | null;
  lifecycle_state?: StrategyStockLifecycleState | null;
  lifecycle_reason?: string | null;
  signal_age_days?: number | null;
  price_return_since_first_seen?: number | null;
  recent_price_return_3d?: number | null;
  drawdown_from_high_since_first_seen?: number | null;
  price_position?: StrategyStockPricePosition | null;
};

export type StrategySourceSignal = {
  name: string;
  mention_count: number;
  event_count: number;
  win_rate_t5?: number | null;
  average_excess_return_t5?: number | null;
  latest_message_time?: string | null;
};

export type StrategyThemeBrief = {
  theme_name: string;
  confidence: number;
  actionability_score: number;
  catalysts: string[];
  risk_notes: string[];
};

export type StrategyBacktestMetric = {
  event_count: number;
  matured_event_count: number;
  pending_event_count: number;
  win_rate_t5?: number | null;
  average_excess_return_t5?: number | null;
};

export type StrategyOpportunity = {
  key: string;
  name: string;
  anchor_type: "stock" | "concept" | "industry" | "theme";
  attention_level: StrategyAttentionLevel;
  score: number;
  reliability_score: number;
  reason: string;
  risk_summary: string;
  recent_message_count: number;
  previous_message_count: number;
  acceleration: number;
  sender_count: number;
  group_count: number;
  high_value_count: number;
  high_value_ratio: number;
  recommendation_count: number;
  research_count: number;
  industry_count: number;
  catalyst_count: number;
  risk_count: number;
  catalyst_terms: string[];
  risk_terms: string[];
  t5_event_count: number;
  win_rate_t5?: number | null;
  average_excess_return_t5?: number | null;
  opportunity_backtest: StrategyBacktestMetric;
  selected_stock_backtest: StrategyBacktestMetric;
  latest_message_time: string;
  related_stocks: StrategyRelatedStock[];
  top_sources: StrategySourceSignal[];
  matched_themes: StrategyThemeBrief[];
};

export type StrategyStockCandidate = {
  stock_name: string;
  ts_code: string;
  event_count: number;
  source_count: number;
  sector_names: string[];
  win_rate_t5?: number | null;
  average_excess_return_t5?: number | null;
  first_seen_time?: string | null;
  latest_message_time?: string | null;
  lifecycle_state?: StrategyStockLifecycleState | null;
  lifecycle_reason?: string | null;
  signal_age_days?: number | null;
  price_return_since_first_seen?: number | null;
  recent_price_return_3d?: number | null;
  drawdown_from_high_since_first_seen?: number | null;
  price_position?: StrategyStockPricePosition | null;
};

export type StrategyDashboard = {
  start_time: string;
  end_time: string;
  recent_start_time: string;
  generated_at: string;
  opportunity_count: number;
  opportunities: StrategyOpportunity[];
  source_quality: StrategySourceSignal[];
  stock_candidates: StrategyStockCandidate[];
};

export type StrategyQuery = {
  days?: number;
  recent_days?: number;
  limit?: number;
};
