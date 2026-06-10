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

export type StrategyStockCandle = {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  pre_close?: number | null;
  change?: number | null;
  pct_chg?: number | null;
  vol?: number | null;
  amount?: number | null;
};

export type StrategyStockChart = {
  ts_code: string;
  candles: StrategyStockCandle[];
  latest_trade_date?: string | null;
  missing_reason?: string | null;
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

export type StockEvidenceMarketPoint = {
  trade_date: string;
  close?: number | null;
  pct_chg?: number | null;
  amount?: number | null;
  amount_ratio_5d?: number | null;
  tag?: string | null;
};

export type StockEvidenceMessage = {
  message_id?: string | null;
  time?: string | null;
  type?: string | null;
  evidence?: string | null;
  sender?: string | null;
  group_name?: string | null;
  raw_content?: string | null;
};

export type StockEvidenceChainItem = {
  ts_code: string;
  stock_name: string;
  stage: string;
  stage_label: string;
  confidence?: number | null;
  rank?: number | null;
  summary: string;
  trigger_count: number;
  unique_trigger_count: number;
  sender_count: number;
  conversation_count: number;
  evidence_count: number;
  channels: string[];
  family_counts: Record<string, number>;
  why: string[];
  incremental_valid?: boolean | null;
  incremental_points: string[];
  pricing_risk?: string | null;
  crowding_risk?: string | null;
  watch_next: string[];
  evidence_chain: StockEvidenceMessage[];
  market_summary: Record<string, unknown>;
  market_points: StockEvidenceMarketPoint[];
  updated_at: string;
};

export type StockEvidenceChainDashboard = {
  as_of_time?: string | null;
  window_start_time?: string | null;
  evidence_start_time?: string | null;
  generated_at: string;
  item_count: number;
  stage_counts: Record<string, number>;
  items: StockEvidenceChainItem[];
};

export type StrategyQuery = {
  days?: number;
  recent_days?: number;
  limit?: number;
};

export type StrategyStockChartQuery = {
  days?: number;
};

export type StrategyValidationQuery = {
  window_days?: number;
  benchmark?: string;
  source_limit?: number;
};
