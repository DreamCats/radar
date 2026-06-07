export type StrategyAttentionLevel = "重点关注" | "继续验证" | "风险升高" | "样本不足" | "过度扩散";
export type StrategyStockLifecycleState = "初现" | "发酵中" | "已兑现" | "回调再看" | "缺少价格";
export type StrategyStockPricePosition = "趋势健康" | "可观察" | "震荡观察" | "回撤偏大" | "短线偏弱" | "首现后走弱" | "缺少价格";
export type StrategyEventCredibilityLevel = "高可信" | "中可信" | "低可信" | "待验证";
export type StrategyStockDecisionBucket = "今日可关注" | "观察等待" | "已兑现复盘";

export type StrategyEventCredibility = {
  score: number;
  level: StrategyEventCredibilityLevel;
  first_source_name?: string | null;
  first_group_name?: string | null;
  first_event_time?: string | null;
  first_message_stock_count: number;
  source_matured_event_count: number;
  source_win_rate_t5?: number | null;
  source_average_excess_return_t5?: number | null;
  logic_hit_count: number;
  hype_hit_count: number;
  reasons: string[];
  risks: string[];
};

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
  realtime_score: number;
  event_credibility?: StrategyEventCredibility | null;
  decision_bucket: StrategyStockDecisionBucket;
  decision_reason?: string | null;
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
  realtime_score: number;
  event_credibility?: StrategyEventCredibility | null;
  decision_bucket: StrategyStockDecisionBucket;
  decision_reason?: string | null;
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

export type StrategyValidationMetric = {
  label: string;
  sample_count: number;
  win_rate?: number | null;
  average_return?: number | null;
  average_excess_return?: number | null;
  average_max_drawdown?: number | null;
};

export type StrategyValidationSummary = {
  window_days: number;
  benchmark_ts_code: string;
  snapshot_count: number;
  matured_stock_count: number;
  latest_snapshot_time?: string | null;
  by_decision_bucket: StrategyValidationMetric[];
  by_credibility_level: StrategyValidationMetric[];
  top_sources: StrategyValidationMetric[];
};

export type LeadSignalWindow = {
  window_days: number;
  target_trade_date?: string | null;
  target_close?: number | null;
  return_rate?: number | null;
  excess_return_rate?: number | null;
};

export type LeadSignalBucket = {
  label: string;
  window_days: number;
  event_count: number;
  average_return?: number | null;
  average_excess_return?: number | null;
  up_rate?: number | null;
};

export type LeadSignalSourceStat = {
  source_name: string;
  event_count: number;
  non_hot_event_count: number;
  pre_rise_event_count: number;
  strong_pre_rise_event_count: number;
  limit_like_event_count: number;
  pre_rise_rate?: number | null;
  average_t1_return?: number | null;
  average_t1_excess_return?: number | null;
  latest_message_time?: string | null;
};

export type LeadSignalSample = {
  event_date: string;
  signal_label: string;
  stock_name: string;
  ts_code: string;
  message_day_pct_chg?: number | null;
  base_trade_date?: string | null;
  base_close?: number | null;
  first_message_time: string;
  event_count: number;
  source_names: string[];
  windows: LeadSignalWindow[];
};

export type LeadSignalSummary = {
  start_time: string;
  end_time: string;
  generated_at: string;
  as_of_date: string;
  available_dates: string[];
  validation_days: number;
  benchmark_ts_code: string;
  message_day_max_pct: number;
  strong_return_pct: number;
  limit_like_pct: number;
  day_event_count: number;
  day_stock_day_count: number;
  day_non_hot_event_count: number;
  day_non_hot_stock_day_count: number;
  day_limit_like_event_count: number;
  day_limit_like_stock_day_count: number;
  event_count: number;
  stock_day_count: number;
  non_hot_event_count: number;
  non_hot_stock_day_count: number;
  pre_rise_event_count: number;
  pre_rise_stock_day_count: number;
  strong_pre_rise_event_count: number;
  strong_pre_rise_stock_day_count: number;
  limit_like_event_count: number;
  limit_like_stock_day_count: number;
  buckets: LeadSignalBucket[];
  source_stats: LeadSignalSourceStat[];
  samples: LeadSignalSample[];
};

export type StrategyQuery = {
  days?: number;
  recent_days?: number;
  limit?: number;
};

export type StrategyValidationQuery = {
  window_days?: number;
  benchmark?: string;
  source_limit?: number;
};

export type LeadSignalQuery = {
  as_of_date?: string;
  days?: number;
  limit?: number;
  source_limit?: number;
  benchmark?: string;
  message_day_max_pct?: number;
  strong_return_pct?: number;
  limit_like_pct?: number;
};

export type SourceRadarSignalStatus = "source_seed" | "spreading_watch" | "mapped" | "old_theme";

export type SourceRadarSignal = {
  snapshot_id: string;
  signal_id: string;
  status: SourceRadarSignalStatus;
  anchor_span: string;
  modifier_span: string;
  novel_span: string;
  relation_type: "A化B" | "prefix-anchor" | "modifier-anchor" | "anchor-extension" | "other";
  score: number;
  novelty_strength: number;
  earliness_score: number;
  askability_score: number;
  trade_score: number;
  first_message_id: string;
  first_seen_time: string;
  first_sender: string;
  first_group_name?: string | null;
  first_snippet: string;
  prior_anchor_mentions: number;
  prior_modifier_mentions: number;
  prior_exact_mentions: number;
  prior_combo_mentions: number;
  asof_mentions: number;
  asof_groups: number;
  asof_senders: number;
  followup_groups: number;
  followup_senders: number;
  mapped_stocks: string[];
  ask_question: string;
  evidence: string[];
  as_of_time: string;
  created_at: string;
};

export type SourceRadarSnapshot = {
  as_of_time?: string | null;
  latest_created_at?: string | null;
  item_count: number;
  available_as_of_times: string[];
  items: SourceRadarSignal[];
};

export type SourceRadarQuery = {
  limit?: number;
  as_of_time?: string;
};

export type SourceRadarValidationMetric = {
  label: string;
  sample_count: number;
  rate?: number | null;
  average_days?: number | null;
};

export type SourceRadarValidationRow = {
  signal_id: string;
  title: string;
  first_as_of_time: string;
  latest_as_of_time: string;
  first_status: SourceRadarSignalStatus;
  latest_status: SourceRadarSignalStatus;
  score: number;
  spread_days?: number | null;
  mapped_days?: number | null;
  mapped_stocks: string[];
  evidence: string[];
};

export type SourceRadarValidationSummary = {
  window_days: number;
  snapshot_count: number;
  signal_count: number;
  spreading_count: number;
  mapped_count: number;
  stale_count: number;
  latest_snapshot_time?: string | null;
  by_first_status: SourceRadarValidationMetric[];
  top_signals: SourceRadarValidationRow[];
};

export type SourceRadarValidationQuery = {
  window_days?: number;
  limit?: number;
};
