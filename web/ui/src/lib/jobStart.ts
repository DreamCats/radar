import {
  startAggregateRefineJob,
  startAnchorMessagesJob,
  startClassifyMessagesJob,
  startIngestWechatJob,
  startRecommendationBacktestJob,
  startStockEvidenceChainJob,
} from "../api/radarApi";
import type { IngestSource } from "../types";
import { DEFAULT_CATEGORIES } from "./jobTemplates";
import { sourceLabel, type JobTemplateKey, type TrackedJob } from "./jobRuns";
import type { LocalRange } from "./timeRange";

type StartJobParams = {
  kind: JobTemplateKey;
  source: IngestSource;
  force: boolean;
  tradeDate: string;
  range: LocalRange;
  window: {
    start_time: string;
    end_time: string;
  };
};

export async function startJob(params: StartJobParams): Promise<TrackedJob[]> {
  const { kind, source, force, tradeDate, range, window } = params;
  if (kind === "ingest") {
    const items = await startIngestWechatJob({
      source,
      start_time: window.start_time,
      end_time: window.end_time,
      force,
      chunk_hours: 1,
      concurrency: 4,
    });
    return items.map((item) => ({ kind, source: item.source, run_id: item.run_id, reused_existing: item.reused_existing }));
  }
  if (kind === "classify") {
    const items = await startClassifyMessagesJob({
      source,
      start_time: window.start_time,
      end_time: window.end_time,
      force,
      chunk_hours: 1,
      limit: 500,
      batch_size: 16,
      max_concurrency: 10,
      low_confidence_threshold: 0.65,
    });
    return items.map((item) => ({ kind, source: item.source, run_id: item.run_id, reused_existing: item.reused_existing }));
  }
  if (kind === "anchor") {
    const items = await startAnchorMessagesJob({
      trade_date: tradeDate,
      source,
      start_time: window.start_time,
      end_time: window.end_time,
      force,
      chunk_hours: 1,
      limit: 500,
      categories: DEFAULT_CATEGORIES,
      min_classification_confidence: 0.7,
      max_anchors: 7,
    });
    return derivedJobs(kind, sourceLabel(source), items);
  }
  if (kind === "backtest") {
    const items = await startRecommendationBacktestJob({
      as_of: range.endDate,
      window_days: backtestWindowDays(range.startDate, range.endDate),
      start_time: window.start_time,
      end_time: window.end_time,
      windows: [1, 2, 3, 5],
      source,
      min_classification_confidence: 0.7,
      benchmark_ts_code: "000300.SH",
      force,
    });
    return derivedJobs(kind, sourceLabel(source), items);
  }
  if (kind === "stockEvidenceChain") {
    const items = await startStockEvidenceChainJob({
      start_time: window.start_time,
      end_time: window.end_time,
      evidence_days: 40,
      limit: 120,
      run_llm: true,
      llm_workers: 16,
      force_llm: force,
    });
    return derivedJobs(kind, "全库证据", items);
  }
  const items = await startAggregateRefineJob({
    trade_date: tradeDate,
    source,
    start_time: window.start_time,
    end_time: window.end_time,
    force,
    categories: DEFAULT_CATEGORIES,
    min_classification_confidence: 0.7,
    min_messages: 2,
    candidate_limit: 50,
    evidence_limit: 3,
    batch_size: 5,
    max_concurrency: 10,
  });
  return derivedJobs(kind, sourceLabel(source), items);
}

function derivedJobs(kind: JobTemplateKey, source: string, items: Array<{ run_id: string; reused_existing: boolean }>): TrackedJob[] {
  return items.map((item) => ({ kind, source, run_id: item.run_id, reused_existing: item.reused_existing }));
}

function backtestWindowDays(startDate: string, endDate: string): number {
  const start = new Date(`${startDate}T00:00:00`).getTime();
  const end = new Date(`${endDate}T00:00:00`).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
    return 30;
  }
  return Math.max(1, Math.round((end - start) / 86400000) + 1);
}
