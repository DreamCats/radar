import { AlertCircle, CheckCircle2, Clock3, LoaderCircle } from "lucide-react";

import type { RunItem } from "../types";

type JobRunKind = "ingest" | "classify" | "anchor" | "refine" | "backtest";

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
  const stage = textValue(metadata.stage) || statusText(kind, status);
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
  if (status === "failed") {
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
    if (kind === "classify" || kind === "anchor") {
      return chunkProgress(run);
    }
    if (kind === "backtest") {
      return backtestProgress(run);
    }
    return refineProgress(run);
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

function chunkProgress(run?: RunItem): number {
  const metadata = run?.metadata ?? {};
  const total = numberValue(metadata.chunk_count);
  const done = numberValue(metadata.completed_chunk_count);
  if (!total) {
    return numberValue(metadata.scanned_count) > 0 ? 25 : 8;
  }
  return boundedPercent(done, total);
}

function refineProgress(run?: RunItem): number {
  const metadata = run?.metadata ?? {};
  const total = numberValue(metadata.llm_batch_count) || numberValue(metadata.batch_count);
  const done = numberValue(metadata.completed_batch_count);
  if (!total) {
    return numberValue(metadata.candidate_count) > 0 ? 35 : 8;
  }
  return boundedPercent(done, total);
}

function backtestProgress(run?: RunItem): number {
  const metadata = run?.metadata ?? {};
  const total = numberValue(metadata.event_count);
  const done = numberValue(metadata.completed_event_count) || run?.raw_count || 0;
  if (!total) {
    return run?.raw_count ? 25 : 8;
  }
  return boundedPercent(done, total);
}

function jobMetrics(kind: JobRunKind, run?: RunItem): string[] {
  if (kind === "ingest") {
    return ingestMetrics(run);
  }
  if (kind === "classify") {
    return classifyMetrics(run);
  }
  if (kind === "anchor") {
    return anchorMetrics(run);
  }
  if (kind === "backtest") {
    return backtestMetrics(run);
  }
  return refineMetrics(run);
}

function ingestMetrics(run?: RunItem): string[] {
  const metadata = run?.metadata ?? {};
  const fetched = numberValue(metadata.fetched_chunk_count);
  const written = numberValue(metadata.written_chunk_count);
  const pending = numberValue(metadata.pending_chunk_count);
  const skipped = numberValue(metadata.skipped_count);
  const raw = run?.raw_count ?? numberValue(metadata.raw_count);
  const filtered = run?.filtered_count ?? numberValue(metadata.filtered_count);
  const stored = run?.stored_count ?? numberValue(metadata.stored_count);

  return [
    pending ? `分片 ${Math.max(written, fetched)}/${pending}` : `跳过 ${skipped} 个已覆盖分片`,
    `拉取 ${raw || numberValue(metadata.fetched_raw_count)} 条`,
    `过滤 ${filtered} 条`,
    `入库 ${stored} 条`,
    durationText(run),
  ].filter(Boolean);
}

function classifyMetrics(run?: RunItem): string[] {
  const metadata = run?.metadata ?? {};
  const scanned = run?.raw_count || numberValue(metadata.scanned_count);
  const classified = numberValue(metadata.classified_count);
  const inserted = run?.stored_count || numberValue(metadata.inserted_count);
  const failed = numberValue(metadata.failed_llm_batches);
  const chunkCount = numberValue(metadata.chunk_count);
  const completedChunks = numberValue(metadata.completed_chunk_count);
  const distribution = distributionText(metadata.distribution);

  return [
    chunkCount ? `分片 ${completedChunks}/${chunkCount}` : "",
    `扫描 ${scanned} 条`,
    `分类 ${classified} 条`,
    `写入 ${inserted} 条`,
    failed ? `失败批次 ${failed}` : "失败批次 0",
    distribution,
    durationText(run),
  ].filter(Boolean);
}

function anchorMetrics(run?: RunItem): string[] {
  const metadata = run?.metadata ?? {};
  const scanned = run?.raw_count || numberValue(metadata.scanned_count);
  const anchors = run?.stored_count || numberValue(metadata.anchor_count);
  const anchored = numberValue(metadata.anchored_message_count);
  const chunkCount = numberValue(metadata.chunk_count);
  const completedChunks = numberValue(metadata.completed_chunk_count);
  return [
    chunkCount ? `分片 ${completedChunks}/${chunkCount}` : "",
    `扫描 ${scanned} 条`,
    `命中消息 ${anchored} 条`,
    `anchor ${anchors} 个`,
    durationText(run),
  ].filter(Boolean);
}

function refineMetrics(run?: RunItem): string[] {
  const metadata = run?.metadata ?? {};
  const candidates = run?.raw_count || numberValue(metadata.candidate_count);
  const themes = run?.stored_count || numberValue(metadata.theme_count);
  const batches = numberValue(metadata.llm_batch_count);
  const failed = run?.filtered_count || numberValue(metadata.failed_llm_batches);
  return [
    `候选 ${candidates} 个`,
    `主题 ${themes} 个`,
    batches ? `批次 ${batches}` : "",
    failed ? `失败批次 ${failed}` : "失败批次 0",
    durationText(run),
  ].filter(Boolean);
}

function backtestMetrics(run?: RunItem): string[] {
  const metadata = run?.metadata ?? {};
  const events = numberValue(metadata.event_count) || run?.raw_count || 0;
  const inserted = numberValue(metadata.inserted_event_count);
  const refreshed = numberValue(metadata.refreshed_count) || run?.stored_count || 0;
  const skipped = numberValue(metadata.skipped_complete_count);
  const pending = numberValue(metadata.pending_count);
  const missing = numberValue(metadata.missing_price_count);
  const failed = numberValue(metadata.failed_count);
  return [
    `推荐事件 ${events} 条`,
    `新增事件 ${inserted} 条`,
    `已补齐窗口 ${refreshed}`,
    `已完成跳过 ${skipped}`,
    `待成熟 ${pending}`,
    `缺行情 ${missing}`,
    `失败 ${failed}`,
    durationText(run),
  ].filter(Boolean);
}

function detailText(run?: RunItem): string {
  if (!run) {
    return "任务已提交，等待服务端返回运行状态。";
  }
  if (run.status === "failed") {
    return run.error_message ? `失败原因：${run.error_message}` : "任务失败。";
  }
  const start = textValue(run.metadata.start_time);
  const end = textValue(run.metadata.end_time);
  return start && end ? `时间窗口：${start} - ${end}` : `目标：${run.target}`;
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
  return "失败";
}

function kindTitle(kind: JobRunKind): string {
  if (kind === "ingest") {
    return "拉取";
  }
  if (kind === "classify") {
    return "分类";
  }
  if (kind === "anchor") {
    return "Anchor";
  }
  if (kind === "backtest") {
    return "推荐回测补齐";
  }
  return "聚合 refine";
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

function distributionText(value: unknown): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return "";
  }
  const parts = Object.entries(value)
    .filter(([, count]) => typeof count === "number" && count > 0)
    .slice(0, 3)
    .map(([category, count]) => `${category} ${count}`);
  return parts.length ? `类别 ${parts.join(" / ")}` : "";
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
