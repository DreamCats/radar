import { AlertCircle, CheckCircle2, Clock3, LoaderCircle } from "lucide-react";

import type { RunItem } from "../types";

type JobRunKind = "ingest" | "classify" | "anchor" | "backtest" | "stockEvidenceChain";

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
  const stage = status === "failed" ? failedStage(run) : textValue(metadata.stage) || statusText(kind, status);
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
    if (kind === "classify") {
      return chunkProgress(run);
    }
    if (kind === "anchor") {
      return run?.stored_count || numberValue(run?.metadata.dictionary_anchor_count) ? 70 : 12;
    }
    if (kind === "backtest") {
      return backtestProgress(run);
    }
    if (kind === "stockEvidenceChain") {
      return evidenceChainProgress(run);
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

function chunkProgress(run?: RunItem): number {
  const metadata = run?.metadata ?? {};
  const total = numberValue(metadata.chunk_count);
  const done = numberValue(metadata.completed_chunk_count);
  if (!total) {
    return numberValue(metadata.scanned_count) > 0 ? 25 : 8;
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

function evidenceChainProgress(run?: RunItem): number {
  const metadata = run?.metadata ?? {};
  if (numberValue(metadata.candidate_count) > 0 || run?.stored_count) {
    return 65;
  }
  return numberValue(metadata.indexed_messages) > 0 ? 35 : 8;
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
  if (kind === "stockEvidenceChain") {
    return evidenceChainMetrics(run);
  }
  return [];
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
  const anchors = run?.stored_count || numberValue(metadata.dictionary_anchor_count) || numberValue(metadata.anchor_count);
  const members = run?.raw_count || numberValue(metadata.market_anchor_member_count) || numberValue(metadata.member_count);
  const failedSources = recordKeys(metadata.failed_sources).length;
  return [
    anchorTradeDateText(metadata),
    `词库 ${anchors} 个`,
    `成分 ${members} 条`,
    metadata.market_anchor_refreshed === false ? "已复用" : "",
    failedSources ? `失败源 ${failedSources}` : "",
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
    `证据事件 ${events} 条`,
    `新增事件 ${inserted} 条`,
    `已补齐窗口 ${refreshed}`,
    `已完成跳过 ${skipped}`,
    `待成熟 ${pending}`,
    `缺行情 ${missing}`,
    `失败 ${failed}`,
    durationText(run),
  ].filter(Boolean);
}

function evidenceChainMetrics(run?: RunItem): string[] {
  const metadata = run?.metadata ?? {};
  const indexed = numberValue(metadata.indexed_messages) || run?.raw_count || 0;
  const mentions = numberValue(metadata.mention_count);
  const candidates = numberValue(metadata.candidate_count) || run?.stored_count || 0;
  const judged = numberValue(metadata.judged_count);
  const reused = numberValue(metadata.reused_count);
  const failed = numberValue(metadata.failed_count) || run?.filtered_count || 0;
  return [
    `索引消息 ${indexed} 条`,
    `股票命中 ${mentions} 条`,
    `候选 ${candidates} 只`,
    `LLM 新判 ${judged}`,
    `复用 ${reused}`,
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
  const metadata = run.metadata;
  const start = textValue(metadata.start_time);
  const end = textValue(metadata.end_time);
  const base = start && end ? `时间窗口：${start} - ${end}` : `目标：${run.target}`;
  const anchorReason = textValue(metadata.market_anchor_skipped_reason);
  return anchorReason ? `${base}；${anchorReason}` : base;
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
    return "Anchor 更新";
  }
  if (kind === "backtest") {
    return "证据回测补齐";
  }
  if (kind === "stockEvidenceChain") {
    return "个股证据链";
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

function anchorTradeDateText(metadata: Record<string, unknown>): string {
  const requested = textValue(metadata.requested_trade_date);
  const actual = textValue(metadata.trade_date);
  return requested && actual && requested !== actual ? `词库 ${actual}` : "";
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

function recordKeys(value: unknown): string[] {
  return value && typeof value === "object" && !Array.isArray(value) ? Object.keys(value) : [];
}

function textValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}
