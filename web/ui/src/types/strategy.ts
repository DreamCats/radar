export type StrategyAttentionLevel = "重点关注" | "继续验证" | "风险升高" | "样本不足" | "过度扩散";
export type StrategyStockLifecycleState = "初现" | "发酵中" | "已兑现" | "回调再看" | "缺少价格";
export type StrategyStockPricePosition = "趋势健康" | "可观察" | "震荡观察" | "回撤偏大" | "短线偏弱" | "首现后走弱" | "缺少价格";
export type StrategyEventCredibilityLevel = "高可信" | "中可信" | "低可信" | "待验证";

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
