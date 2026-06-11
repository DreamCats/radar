export type StockEvidenceStockCandle = {
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

export type StockEvidenceStockChart = {
  ts_code: string;
  candles: StockEvidenceStockCandle[];
  latest_trade_date?: string | null;
  latest_source?: string | null;
  latest_is_realtime: boolean;
  missing_reason?: string | null;
};

export type StockEvidenceMarketPoint = {
  trade_date: string;
  close?: number | null;
  pct_chg?: number | null;
  amount?: number | null;
  amount_ratio_5d?: number | null;
  tag?: string | null;
};

export type StockEvidenceThemeContext = {
  theme_id: string;
  theme_name: string;
  theme_type: string;
  role: string;
  confidence: number;
  source_count: number;
  reasons: string[];
  first_seen_date?: string | null;
  last_seen_date?: string | null;
  latest_trade_date?: string | null;
  member_count?: number | null;
  covered_member_count?: number | null;
  return_rank_5d?: number | null;
  stock_return_5d?: number | null;
  stock_return_20d?: number | null;
  amount_ratio_5d?: number | null;
  theme_return_median_5d?: number | null;
  is_theme_leader: boolean;
  is_theme_laggard: boolean;
  is_broad_theme: boolean;
  quality_score: number;
  quality_label: string;
  quality_reasons: string[];
  quality_warnings: string[];
  missing_evidence: string[];
};

export type StockEvidenceRecognitionContext = {
  state: string;
  state_label: string;
  reasons: string[];
  missing_evidence: string[];
};

export type StockEvidenceReviewContext = {
  state: string;
  label: string;
  tone: "success" | "warning" | "danger" | "info" | "muted";
  action_label: string;
  headline: string;
  reasons: string[];
};

export type StockEvidenceLifecycleDigestContext = {
  scope_key: string;
  theme_id?: string | null;
  theme_name?: string | null;
  stage_label?: string | null;
  recognition_label?: string | null;
  one_line: string;
  timeline: string[];
  stage_reason: string[];
  missing_evidence: string[];
  risk: string[];
  next_watch: string[];
  evidence_signature: string;
  message_hash?: string | null;
  market_hash?: string | null;
  theme_hash?: string | null;
  recognition_hash?: string | null;
  backtest_hash?: string | null;
  lifecycle_package_hash?: string | null;
  updated_at: string;
};

export type LifecycleDigestHashes = {
  message_hash: string;
  market_hash: string;
  theme_hash: string;
  recognition_hash: string;
  backtest_hash: string;
  lifecycle_package_hash: string;
};

export type LifecycleDigestPreviewItem = {
  scope_key: string;
  ts_code: string;
  stock_name: string;
  theme_id?: string | null;
  theme_name?: string | null;
  stage_label: string;
  recognition_label: string;
  action: string;
  reason: string;
  evidence_signature: string;
  hashes: LifecycleDigestHashes;
  changed_hashes: string[];
};

export type LifecycleDigestPreview = {
  as_of_time?: string | null;
  scanned_count: number;
  processable_count: number;
  pending_count: number;
  skipped_count: number;
  estimated_llm_calls: number;
  items: LifecycleDigestPreviewItem[];
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
  themes: StockEvidenceThemeContext[];
  primary_theme?: StockEvidenceThemeContext | null;
  recognition: StockEvidenceRecognitionContext;
  review: StockEvidenceReviewContext;
  lifecycle_digest?: StockEvidenceLifecycleDigestContext | null;
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

export type StockEvidenceStockChartQuery = {
  days?: number;
};
