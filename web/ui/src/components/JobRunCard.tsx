import { AlertCircle, CheckCircle2, Clock3, LoaderCircle } from "lucide-react";

import type { RunItem } from "../types";

type JobRunKind = "ingest" | "classify";

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
  const title = `${kind === "ingest" ? "拉取" : "分类"} · ${source}`;
  const progress = progressPercent(kind, run);
  const stage = textValue(metadata.stage) || statusText(kind, status);
  const metrics = kind === "ingest" ? ingestMetrics(run) : classifyMetrics(run);
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
    return kind === "ingest" ? ingestProgress(run) : classifyProgress(run);
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

function classifyProgress(run?: RunItem): number {
  const metadata = run?.metadata ?? {};
  const total = numberValue(metadata.chunk_count);
  const done = numberValue(metadata.completed_chunk_count);
  if (!total) {
    return numberValue(metadata.scanned_count) > 0 ? 25 : 8;
  }
  return boundedPercent(done, total);
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
