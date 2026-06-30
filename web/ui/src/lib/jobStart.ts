import {
  startAnalystBacktestJob,
  startCatalystValuationReportJob,
  startIngestWechatJob,
  startMarketStockRefreshJob,
  startThsConceptRefreshJob,
} from "../api/radarApi";
import type { IngestSource } from "../types";
import { sourceLabel, type JobTemplateKey, type TrackedJob } from "./jobRuns";
import type { LocalRange } from "./timeRange";

type StartJobParams = {
  kind: JobTemplateKey;
  source: IngestSource;
  force: boolean;
  range: LocalRange;
  window: {
    start_time: string;
    end_time: string;
  };
};

export async function startJob(params: StartJobParams): Promise<TrackedJob[]> {
  const { kind, source, force, range, window } = params;
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
  if (kind === "analystBacktest") {
    const items = await startAnalystBacktestJob({
      as_of: range.endDate,
      lookback_days: Math.min(120, Math.max(1, backtestWindowDays(range.startDate, range.endDate))),
      start_time: window.start_time,
      end_time: window.end_time,
      windows: [1, 3, 5],
      source,
      cooldown_trade_days: 5,
      benchmark_ts_code: "000300.SH",
      remote_price_fetch: true,
    });
    return derivedJobs(kind, sourceLabel(source), items);
  }
  if (kind === "marketStockRefresh") {
    const items = await startMarketStockRefreshJob({ force: true });
    return derivedJobs(kind, "A股股票主数据", items);
  }
  if (kind === "thsConceptRefresh") {
    const items = await startThsConceptRefreshJob({ force: true });
    return derivedJobs(kind, "THS 概念全量", items);
  }
  if (kind === "catalystValuationReport") {
    const items = await startCatalystValuationReportJob({
      start_time: window.start_time,
      end_time: window.end_time,
      limit: 200,
      max_stocks: 12,
      publish: true,
      notify: true,
    });
    return derivedJobs(kind, "催化估值线索", items);
  }
  throw new Error(`未知作业类型：${kind}`);
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
