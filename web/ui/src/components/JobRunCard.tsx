import { AlertCircle, CheckCircle2, Clock3, LoaderCircle } from "lucide-react";

import type { RunItem } from "../types";

type JobRunKind =
  | "ingest"
  | "analystBacktest"
  | "catalystValuationReport"
  | "marketStockRefresh"
  | "thsConceptRefresh";

type JobRunCardProps = {
  kind: JobRunKind;
  source: string;
  run?: RunItem;
  runId: string;
  reusedExisting?: boolean;
};

export function JobRunCard({ kind, source, run, runId, reusedExisting = false }: JobRunCardProps) {
  const status = run?.status ?? "running";
  const metadata = run?.metadata ?? {};
  const title = `${kindTitle(kind)} · ${source}`;
  const progress = progressPercent(kind, run);
  const stage = status === "failed" || status === "partial_failed"
    ? failedStage(run)
    : textValue(metadata.stage) || statusText(kind, status);
  const metrics = jobMetrics(kind, run);
  const detail = detailText(run);

  return (
    <article className={`job-card ${status}`}>
      <div className="job-card-main">
        <div className="job-card-title">
          <StatusIcon status={status} />
          <div>
            <h3>{title}</h3>
            <p>{stage}{reusedExisting ? " · 已复用运行中任务" : ""}</p>
          </div>
        </div>
        <span className={`job-status ${status}`}>{statusText(kind, status)}</span>
      </div>

      <div className="job-progress" aria-label="作业进度">
        <span style={{ width: `${progress}%` }} />
      </div>

      <div className="job-metrics">
        {metrics.map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>

      <details className="job-details">
        <summary>详情</summary>
        <p>{detail}</p>
        <p>run_id: {run?.run_id ?? runId}</p>
      </details>
    </article>
  );
}

function StatusIcon({ status }: { status: RunItem["status"] | "running" }) {
  if (status === "failed" || status === "partial_failed") {
    return <AlertCircle className="job-icon failed" size={17} />;
  }
  if (status === "succeeded" || status === "skipped") {
    return <CheckCircle2 className="job-icon succeeded" size={17} />;
  }
  if (status === "running") {
    return <LoaderCircle className="job-icon running" size={17} />;
  }
  return <Clock3 className="job-icon" size={17} />;
}

function progressPercent(kind: JobRunKind, run?: RunItem): number {
  if (!run || run.status === "running") {
    if (kind === "ingest") {
      return ingestProgress(run);
    }
    if (kind === "analystBacktest") {
      return analystBacktestProgress(run);
    }
    if (kind === "thsConceptRefresh") {
      return thsConceptRefreshProgress(run);
    }
    return 8;
  }
  return 100;
}

function ingestProgress(run?: RunItem): number {
  const metadata = run?.metadata ?? {};
  const total = numberValue(metadata.pending_chunk_count) || numberValue(metadata.chunk_count);
  if (!total) {
    return 8;
  }
  const done = Math.max(numberValue(metadata.written_chunk_count), numberValue(metadata.fetched_chunk_count));
  return boundedPercent(done, total);
}

function jobMetrics(kind: JobRunKind, run?: RunItem): string[] {
  if (kind === "ingest") {
    return ingestMetrics(run);
  }
  if (kind === "analystBacktest") {
    return analystBacktestMetrics(run);
  }
  if (kind === "marketStockRefresh") {
    return marketStockRefreshMetrics(run);
  }
  if (kind === "thsConceptRefresh") {
    return thsConceptRefreshMetrics(run);
  }
  if (kind === "catalystValuationReport") {
    return catalystValuationReportMetrics(run);
  }
  return [];
}

function ingestMetrics(run?: RunItem): string[] {
  const metadata = run?.metadata ?? {};
  const fetched = numberValue(metadata.fetched_chunk_count);
  const written = numberValue(metadata.written_chunk_count);
  const pending = numberValue(metadata.pending_chunk_count);
  const skipped = numberValue(metadata.skipped_count);
  const failed = numberValue(metadata.failed_chunk_count);
  const raw = run?.raw_count ?? numberValue(metadata.raw_count);
  const filtered = run?.filtered_count ?? numberValue(metadata.filtered_count);
  const stored = run?.stored_count ?? numberValue(metadata.stored_count);

  return [
    pending ? `分片 ${Math.max(written, fetched)}/${pending}` : `跳过 ${skipped} 个已覆盖分片`,
    `拉取 ${raw || numberValue(metadata.fetched_raw_count)} 条`,
    `过滤 ${filtered} 条`,
    `入库 ${stored} 条`,
    failed ? `失败分片 ${failed}` : "",
    durationText(run),
  ].filter(Boolean);
}

function analystBacktestProgress(run?: RunItem): number {
  const metadata = run?.metadata ?? {};
  const total = numberValue(metadata.effective_mention_count);
  const done = run?.raw_count || 0;
  if (!total) {
    return numberValue(metadata.prewarm_daily_row_count) > 0 ? 30 : 8;
  }
  return boundedPercent(done, total);
}

function analystBacktestMetrics(run?: RunItem): string[] {
  const metadata = run?.metadata ?? {};
  const scanned = numberValue(metadata.scanned_message_count) || run?.raw_count || 0;
  const rawMentions = numberValue(metadata.raw_mention_count);
  const effective = numberValue(metadata.effective_mention_count) || run?.stored_count || 0;
  const repeated = numberValue(metadata.repeated_mention_count) || run?.filtered_count || 0;
  const broadList = numberValue(metadata.broad_list_mention_count);
  const brokerFiltered = numberValue(metadata.source_broker_filtered_count);
  const prewarmRows = numberValue(metadata.prewarm_daily_row_count);
  const refreshed = numberValue(metadata.refreshed_count);
  const pending = numberValue(metadata.pending_count);
  const missing = numberValue(metadata.missing_price_count);
  return [
    `扫描消息 ${scanned} 条`,
    `股票提及 ${rawMentions} 条`,
    `有效样本 ${effective}`,
    `重复 ${repeated}`,
    `broad_list ${broadList}`,
    `券商源过滤 ${brokerFiltered}`,
    prewarmRows ? `补行情 ${prewarmRows} 行` : "",
    `已补齐窗口 ${refreshed}`,
    `待成熟 ${pending}`,
    `缺行情 ${missing}`,
    durationText(run),
  ].filter(Boolean);
}

function marketStockRefreshMetrics(run?: RunItem): string[] {
  const metadata = run?.metadata ?? {};
  const fetched = run?.raw_count ?? numberValue(metadata.fetched_count);
  const stored = run?.stored_count ?? numberValue(metadata.stored_count);
  const listed = numberValue(metadata.listed_count);
  const delisted = numberValue(metadata.delisted_count);
  const pending = numberValue(metadata.pending_count);
  return [
    `拉取 ${fetched} 条`,
    `入库 ${stored} 条`,
    `上市 ${listed}`,
    `退市 ${delisted}`,
    `待上市 ${pending}`,
    durationText(run),
  ].filter(Boolean);
}

function thsConceptRefreshProgress(run?: RunItem): number {
  const metadata = run?.metadata ?? {};
  const total = numberValue(metadata.concept_count);
  const done = numberValue(metadata.refreshed_member_count) + numberValue(metadata.skipped_member_count);
  return total ? boundedPercent(done, total) : 8;
}

function thsConceptRefreshMetrics(run?: RunItem): string[] {
  const metadata = run?.metadata ?? {};
  const concepts = run?.raw_count ?? numberValue(metadata.concept_count);
  const memberRows = run?.stored_count ?? numberValue(metadata.member_row_count);
  const refreshed = numberValue(metadata.refreshed_member_count);
  const skipped = run?.filtered_count ?? numberValue(metadata.skipped_member_count);
  return [
    `概念 ${concepts}`,
    `成员行 ${memberRows}`,
    `刷新 ${refreshed}`,
    `跳过 ${skipped}`,
    durationText(run),
  ].filter(Boolean);
}

function catalystValuationReportMetrics(run?: RunItem): string[] {
  const metadata = run?.metadata ?? {};
  const feedItems = run?.raw_count ?? numberValue(metadata.total_feed_items);
  const candidateStocks = numberValue(metadata.total_candidate_stocks);
  const stocks = run?.stored_count ?? numberValue(metadata.total_stocks);
  const metrics = [`线索 ${feedItems} 条`];
  if (candidateStocks !== undefined) {
    metrics.push(`候选 ${candidateStocks}`);
  }
  metrics.push(`保留 ${stocks}`);
  metrics.push(textValue(metadata.published_url) ? "已上传" : "本地报告");
  if (textValue(metadata.auto_upside_chat_run_id)) {
    metrics.push("已发起测算");
  } else if (metadata.auto_upside === true) {
    metrics.push("待发起测算");
  }
  const duration = durationText(run);
  if (duration) {
    metrics.push(duration);
  }
  return metrics;
}

function detailText(run?: RunItem): string {
  if (!run) {
    return "任务已提交，等待服务端返回运行状态。";
  }
  if (run.status === "failed" || run.status === "partial_failed") {
    return run.error_message ? `失败原因：${run.error_message}` : "任务失败。";
  }
  const metadata = run.metadata;
  const url = textValue(metadata.published_url);
  if (url) {
    return `报告：${url}`;
  }
  const start = textValue(metadata.start_time);
  const end = textValue(metadata.end_time);
  return start && end ? `时间窗口：${start} - ${end}` : `目标：${run.target}`;
}

function failedStage(run?: RunItem): string {
  const message = run?.error_message?.trim();
  if (!message) {
    return "失败";
  }
  return `失败：${message.slice(0, 48)}`;
}

function statusText(kind: JobRunKind, status: RunItem["status"] | "running"): string {
  if (status === "running") {
    return "运行中";
  }
  if (status === "succeeded") {
    return "已完成";
  }
  if (status === "skipped") {
    return kind === "ingest" ? "已覆盖" : "无需处理";
  }
  if (status === "partial_failed") {
    return "部分失败";
  }
  return "失败";
}

function kindTitle(kind: JobRunKind): string {
  if (kind === "ingest") {
    return "拉取";
  }
  if (kind === "analystBacktest") {
    return "分析师回测";
  }
  if (kind === "marketStockRefresh") {
    return "市场主数据";
  }
  if (kind === "thsConceptRefresh") {
    return "THS 概念";
  }
  if (kind === "catalystValuationReport") {
    return "催化估值线索";
  }
  return "作业";
}

function durationText(run?: RunItem): string {
  if (!run) {
    return "";
  }
  const startedAt = new Date(run.started_at).getTime();
  const endedAt = run.finished_at ? new Date(run.finished_at).getTime() : Date.now();
  if (!Number.isFinite(startedAt) || !Number.isFinite(endedAt) || endedAt < startedAt) {
    return "";
  }
  const seconds = Math.max(0, Math.round((endedAt - startedAt) / 1000));
  if (seconds < 60) {
    return `用时 ${seconds}s`;
  }
  return `用时 ${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function boundedPercent(done: number, total: number): number {
  if (total <= 0) {
    return 8;
  }
  return Math.max(8, Math.min(100, Math.round((done / total) * 100)));
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function textValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}
