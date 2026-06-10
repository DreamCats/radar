type SourceKey = "personal_message" | "group_message";
type IngestSource = "all" | SourceKey;
type MessageSource = "个人消息" | "个人群";
type MessageCategory = "research" | "recommendation" | "event" | "industry" | "tool_ad" | "chat" | "unknown";
type ClassificationRetryMode = "needs_review" | "unknown" | "low_confidence";

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

export type StrategySnapshotSaveRequest = {
  days: number;
  recent_days: number;
  limit: number;
  force: boolean;
};

export type StrategySnapshotBackfillJobRequest = {
  start_time: string;
  end_time: string;
  windows: number[];
  benchmark_ts_code: string;
};

export type StockEvidenceChainJobRequest = {
  start_time: string;
  end_time: string;
  evidence_days: number;
  limit: number;
  run_llm: boolean;
  llm_workers: number;
  force_llm: boolean;
};

export type DerivedJobItem = {
  job_type: "anchor" | "aggregate_refine" | "recommendation_backtest" | "strategy_backfill" | "stock_evidence_chain";
  run_id: string;
  reused_existing: boolean;
  status: "running";
};
