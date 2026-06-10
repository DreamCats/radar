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

export type StockEvidenceStockChartQuery = {
  days?: number;
};
