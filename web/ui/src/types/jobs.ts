type SourceKey = "personal_message" | "group_message";
type IngestSource = "all" | SourceKey;
type MessageSource = "个人消息" | "个人群";

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
  failed_count: number;
  run_id?: string | null;
};

export type IngestJobItem = {
  source_key: SourceKey;
  source: MessageSource;
  run_id: string;
  reused_existing: boolean;
  status: "running";
};

export type AnalystBacktestRequest = {
  as_of: string;
  lookback_days: number;
  start_time: string;
  end_time: string;
  windows: number[];
  source: IngestSource;
  cooldown_trade_days: number;
  benchmark_ts_code: string;
  remote_price_fetch: boolean;
};

export type MarketStockRefreshRequest = {
  force: boolean;
};

export type ThsConceptRefreshRequest = {
  force: boolean;
};

export type CatalystValuationReportJobRequest = {
  start_time: string;
  end_time: string;
  limit: number;
  max_stocks?: number | null;
  publish: boolean;
  notify: boolean;
};

export type DerivedJobItem = {
  job_type: "analyst_backtest" | "catalyst_valuation_report" | "market_stock_refresh" | "ths_concept_refresh";
  run_id: string;
  reused_existing: boolean;
  status: "running";
};

export type ScheduleItem = {
  schedule_id: string;
  job_key: string;
  title: string;
  enabled: boolean;
  timezone: string;
  cadence_kind: string;
  cadence: Record<string, unknown>;
  window_preset?: string | null;
  request: Record<string, unknown>;
  catch_up_policy: string;
  max_lag_minutes: number;
  last_tick_at?: string | null;
  next_tick_at?: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

export type ScheduleTickItem = {
  tick_id: string;
  schedule_id: string;
  planned_at: string;
  fired_at?: string | null;
  status: "planned" | "running" | "submitted" | "skipped" | "failed";
  run_ids: string[];
  request: Record<string, unknown>;
  skipped_reason?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
};
