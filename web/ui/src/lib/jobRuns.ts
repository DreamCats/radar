import type { IngestSource, RunItem } from "../types";

export type JobTemplateKey = "ingest" | "classify" | "anchor" | "refine";

export type TrackedJob = {
  kind: JobTemplateKey;
  source: string;
  run_id: string;
  reused_existing: boolean;
};

const RUN_KIND_TO_JOB: Record<string, JobTemplateKey> = {
  wechat_ingest_range: "ingest",
  message_classify_range: "classify",
  message_anchor_range: "anchor",
  aggregate_refine: "refine",
};

const SOURCE_LABELS: Record<IngestSource, string> = {
  all: "全部",
  personal_message: "个人消息",
  group_message: "个人群",
};

export function trackedJobFromRun(run: RunItem): TrackedJob | null {
  const kind = RUN_KIND_TO_JOB[run.kind];
  if (!kind) {
    return null;
  }
  return {
    kind,
    source: sourceFromRun(run),
    run_id: run.run_id,
    reused_existing: true,
  };
}

export function mergeTrackedJobs(next: TrackedJob[], current: TrackedJob[], limit = 20): TrackedJob[] {
  const seen = new Set<string>();
  const merged: TrackedJob[] = [];
  for (const item of [...next, ...current]) {
    if (seen.has(item.run_id)) {
      continue;
    }
    seen.add(item.run_id);
    merged.push(item);
  }
  return merged.slice(0, limit);
}

export function mergeRuns(recentRuns: RunItem[], runningRuns: RunItem[]): RunItem[] {
  const seen = new Set<string>();
  const merged: RunItem[] = [];
  for (const run of [...runningRuns, ...recentRuns]) {
    if (seen.has(run.run_id)) {
      continue;
    }
    seen.add(run.run_id);
    merged.push(run);
  }
  return merged;
}

export function sourceLabel(value: IngestSource): string {
  return SOURCE_LABELS[value] ?? value;
}

function sourceFromRun(run: RunItem): string {
  const source = textValue(run.metadata.source);
  if (source && !isSourceKey(source)) {
    return source;
  }
  const sourceKey = source || textValue(run.metadata.source_key);
  if (isSourceKey(sourceKey)) {
    return sourceLabel(sourceKey);
  }
  return run.target;
}

function isSourceKey(value: string): value is IngestSource {
  return value === "all" || value === "personal_message" || value === "group_message";
}

function textValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}
