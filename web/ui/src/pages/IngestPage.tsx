import { useEffect, useMemo, useState } from "react";
import { CalendarDays, Play, Square } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import {
  cancelRun,
  fetchLifecycleDigestPreview,
  fetchRuns,
} from "../api/radarApi";
import { DateField, SelectField, TextField } from "../components/FormFields";
import { JobRunCard } from "../components/JobRunCard";
import { PanelTitle } from "../components/PanelTitle";
import { toIso } from "../lib/datetime";
import { configHints, JOB_TEMPLATE_GROUPS, JOB_TEMPLATES, SOURCE_OPTIONS } from "../lib/jobTemplates";
import {
  JOB_RUN_KINDS,
  mergeRuns,
  mergeTrackedJobs,
  trackedJobFromRun,
  type JobTemplateKey,
  type TrackedJob,
} from "../lib/jobRuns";
import { startJob } from "../lib/jobStart";
import { panelMotionState } from "../lib/motion";
import {
  buildPresetRange,
  buildYesterdayCloseRange,
  rangeLabel,
  RANGE_PRESETS,
  toLocalIso,
  type LocalRange,
  type RangePreset,
} from "../lib/timeRange";
import type { IngestSource, LifecycleDigestPreview, RunItem } from "../types";

const INGEST_RANGE_PRESETS: Array<[RangePreset, string]> = [["yesterdayClose", "昨日 15:00"], ...RANGE_PRESETS];
const RECENT_RUN_LIMIT = 50;
const RUNNING_RUN_LIMIT = 50;
const RUNNING_REFRESH_MS = 4000;
const IDLE_REFRESH_MS = 30000;

export function IngestPage() {
  const initialRange = useMemo(() => buildPresetRange("yesterdayClose"), []);
  const shouldReduceMotion = useReducedMotion();
  const [selectedJob, setSelectedJob] = useState<JobTemplateKey>("ingest");
  const [source, setSource] = useState<IngestSource>("all");
  const [range, setRange] = useState<LocalRange>(initialRange);
  const [preset, setPreset] = useState<RangePreset>("yesterdayClose");
  const [rangeOpen, setRangeOpen] = useState(false);
  const [tradeDate, setTradeDate] = useState(() => dateToTradeDate(initialRange.endDate));
  const [force, setForce] = useState(false);
  const [trackedJobs, setTrackedJobs] = useState<TrackedJob[]>([]);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [lifecyclePreview, setLifecyclePreview] = useState<LifecycleDigestPreview | null>(null);
  const [lifecyclePreviewLoading, setLifecyclePreviewLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [canceling, setCanceling] = useState(false);

  const startValue = toLocalIso(range.startDate, range.startTime);
  const endValue = toLocalIso(range.endDate, range.endTime);
  const validWindow = Boolean(startValue && endValue) && startValue <= endValue;
  const validTradeDate = /^\d{8}$/.test(tradeDate);
  const canSubmit = selectedJob === "anchor" ? validTradeDate : selectedJob === "lifecycleDigest" ? true : validWindow;
  const selectedTemplate = JOB_TEMPLATES.find((item) => item.key === selectedJob) ?? JOB_TEMPLATES[0];
  const rows = runs
    .map((run) => {
      const job = trackedJobs.find((item) => item.run_id === run.run_id) ?? trackedJobFromRun(run, false);
      return job ? { job, run } : null;
    })
    .filter((row): row is { job: TrackedJob; run: RunItem } => row !== null);
  const runningRows = rows.filter(({ run }) => run.status === "running");
  const selectedRunningRows = runningRows.filter(({ job }) => job.kind === selectedJob);
  const hasRunning = runningRows.length > 0;
  const selectedHasRunning = selectedRunningRows.length > 0;
  const runningCount = runningRows.length;
  const finishedCount = rows.length - runningCount;
  const jobMotion = panelMotionState(shouldReduceMotion);
  const rangePresets = selectedJob === "ingest" ? INGEST_RANGE_PRESETS : RANGE_PRESETS;
  const configGridClass = [
    "job-config-grid",
    selectedJob === "stockEvidenceChain" ? "strategy" : "",
    selectedJob === "lifecycleDigest" ? "strategy" : "",
  ].filter(Boolean).join(" ");
  const submitButtonClass = [
    "primary-button",
    "ingest-submit",
    selectedHasRunning ? "running" : "",
  ].filter(Boolean).join(" ");

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    async function refresh() {
      const hasRunningRuns = await refreshRunsAndResults();
      if (!cancelled) {
        timer = window.setTimeout(refresh, hasRunningRuns ? RUNNING_REFRESH_MS : IDLE_REFRESH_MS);
      }
    }

    void refresh();
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (selectedJob !== "lifecycleDigest") {
      setLifecyclePreview(null);
      return () => {
        cancelled = true;
      };
    }
    setLifecyclePreviewLoading(true);
    fetchLifecycleDigestPreview({ limit: 120, force })
      .then((preview) => {
        if (!cancelled) {
          setLifecyclePreview(preview);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "加载生命周期预览失败");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLifecyclePreviewLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [force, selectedJob]);

  async function refreshRunsAndResults(): Promise<boolean> {
    setRunsLoading(true);
    setError(null);
    try {
      const [runItems, runningItems] = await Promise.all([
        fetchRuns({ kinds: JOB_RUN_KINDS, limit: RECENT_RUN_LIMIT }),
        fetchRuns({ kinds: JOB_RUN_KINDS, status: "running", limit: RUNNING_RUN_LIMIT }),
      ]);
      const mergedRuns = mergeRuns(runItems, runningItems);
      setRuns(mergedRuns);
      const restoredRunningJobs = runningItems.map((item) => trackedJobFromRun(item)).filter((item): item is TrackedJob => item !== null);
      const restoredRecentJobs = runItems.map((item) => trackedJobFromRun(item, false)).filter((item): item is TrackedJob => item !== null);
      const restoredJobs = mergeTrackedJobs(restoredRunningJobs, restoredRecentJobs);
      if (restoredJobs.length > 0) {
        const knownRunIds = new Set(mergedRuns.map((item) => item.run_id));
        setTrackedJobs((current) => mergeTrackedJobs(restoredJobs, current.filter((item) => knownRunIds.has(item.run_id))));
      }
      return runningItems.length > 0;
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载作业数据失败");
      return false;
    } finally {
      setRunsLoading(false);
    }
  }

  async function submitSelectedJob() {
    setSubmitting(true);
    setError(null);
    try {
      const start_time = startValue;
      const end_time = endValue;
      const newJobs = await startJob({
        kind: selectedJob,
        source,
        force,
        tradeDate,
        range,
        window: { start_time, end_time },
      });
      setTrackedJobs((current) => mergeTrackedJobs(newJobs, current));
      await refreshRunsAndResults();
    } catch (err) {
      setError(err instanceof Error ? err.message : "作业提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function cancelRunningJobs() {
    if (selectedRunningRows.length === 0) {
      return;
    }
    setCanceling(true);
    setError(null);
    try {
      await Promise.all(selectedRunningRows.map(({ run }) => cancelRun(run.run_id)));
      await refreshRunsAndResults();
    } catch (err) {
      setError(err instanceof Error ? err.message : "终止作业失败");
    } finally {
      setCanceling(false);
    }
  }

  function handlePrimaryAction() {
    if (selectedHasRunning) {
      void cancelRunningJobs();
      return;
    }
    void submitSelectedJob();
  }

  function applyPreset(value: RangePreset) {
    const nextRange = buildPresetRange(value);
    setPreset(value);
    setRange(nextRange);
    setTradeDate(dateToTradeDate(nextRange.endDate));
  }

  function updateDateTime(target: "start" | "end", value: string) {
    const nextValue = toIso(value);
    const [date, time = ""] = nextValue.split("T");
    const dateKey = target === "start" ? "startDate" : "endDate";
    const timeKey = target === "start" ? "startTime" : "endTime";
    setPreset("custom");
    setRange((current) => ({ ...current, [dateKey]: date ?? "", [timeKey]: time.slice(0, 5) }));
    if (target === "end" && date) {
      setTradeDate(dateToTradeDate(date));
    }
  }

  function selectJob(kind: JobTemplateKey) {
    setSelectedJob(kind);
    const needsHistoryWindow = kind === "analystBacktest";
    if (!needsHistoryWindow && preset === "last30d") {
      const nextRange = buildYesterdayCloseRange();
      setPreset("yesterdayClose");
      setRange(nextRange);
      setTradeDate(dateToTradeDate(nextRange.endDate));
      return;
    }
    if (needsHistoryWindow && selectedJob !== kind && (preset === "today" || preset === "yesterdayClose")) {
      const nextRange = buildPresetRange("last30d");
      setPreset("last30d");
      setRange(nextRange);
      setTradeDate(dateToTradeDate(nextRange.endDate));
    }
  }

  return (
    <section className="ingest-page job-center-page">
      <div className="ingest-header">
        <PanelTitle title="作业中心" meta="执行 / 历史" />
        <div className="ingest-window-pill">
          <CalendarDays size={15} />
          {rangeLabel(range)}
        </div>
      </div>

      <div className={rangeOpen ? "ingest-range-stack mobile-filter-stack mobile-open" : "ingest-range-stack mobile-filter-stack"}>
        <button
          className="mobile-filter-toggle"
          type="button"
          aria-expanded={rangeOpen}
          onClick={() => setRangeOpen((value) => !value)}
        >
          时间窗口
          <span>{rangeLabel(range)}</span>
        </button>
        <div className="mobile-filter-fields">
          <div className="range-presets" aria-label="快捷时间窗口">
            {rangePresets.map(([value, label]) => (
              <button
                className={preset === value ? "preset-button active" : "preset-button"}
                key={value}
                type="button"
                onClick={() => {
                  applyPreset(value);
                  setRangeOpen(false);
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="job-center-grid">
        <aside className="content-panel job-template-panel">
          <PanelTitle title="作业类型" meta={`${JOB_TEMPLATES.length} 个模板`} />
          <div className="job-template-list">
            {JOB_TEMPLATE_GROUPS.map((group) => (
              <div className="job-template-group" key={group.title}>
                <p className="job-template-group-title">{group.title}</p>
                {group.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      className={selectedJob === item.key ? "job-template active" : "job-template"}
                      key={item.key}
                      type="button"
                      onClick={() => selectJob(item.key)}
                    >
                      <Icon size={16} />
                      <span>
                        <strong>{item.title}</strong>
                        <small>{item.meta}</small>
                        <small>{item.serves}</small>
                      </span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </aside>

        <section className="content-panel job-config-panel">
          <AnimatePresence initial={false} mode="wait">
            <motion.div
              animate={jobMotion.animate}
              className="job-config-motion"
              exit={jobMotion.exit}
              initial={jobMotion.initial}
              key={selectedJob}
              transition={jobMotion.transition}
            >
              <div className="ingest-card-head">
                <PanelTitle title={selectedTemplate.title} meta={`${selectedTemplate.meta} · ${selectedTemplate.serves}`} />
              </div>
              <div className={configGridClass}>
                {selectedJob !== "stockEvidenceChain" && selectedJob !== "lifecycleDigest" && selectedJob !== "anchor" && (
                  <SelectField label="来源" value={source} onChange={(value) => setSource(value as IngestSource)} options={SOURCE_OPTIONS} />
                )}
                {selectedJob !== "anchor" && selectedJob !== "lifecycleDigest" && (
                  <>
                    <DateField label="开始" value={startValue} onChange={(value) => updateDateTime("start", value)} />
                    <DateField label="结束" value={endValue} onChange={(value) => updateDateTime("end", value)} />
                  </>
                )}
                {selectedJob === "anchor" && (
                  <TextField label="交易日" value={tradeDate} onChange={setTradeDate} />
                )}
                <label className="toggle-field">
                  <input checked={force} type="checkbox" onChange={(event) => setForce(event.target.checked)} />
                  <span>{forceLabel(selectedJob)}</span>
                </label>
                <button
                  className={submitButtonClass}
                  type="button"
                  disabled={submitting || canceling || (!selectedHasRunning && !canSubmit)}
                  onClick={handlePrimaryAction}
                >
                  {selectedHasRunning ? <Square size={16} /> : <Play size={16} />}
                  {canceling ? "终止中" : submitting ? "提交中" : selectedHasRunning ? "终止任务" : "开始执行"}
                </button>
              </div>
              {selectedJob !== "anchor" && selectedJob !== "lifecycleDigest" && !validWindow && <p className="error-line">请选择有效的开始和结束时间。</p>}
              {selectedJob === "lifecycleDigest" && (
                <LifecyclePreviewCard preview={lifecyclePreview} loading={lifecyclePreviewLoading} />
              )}
              {selectedJob === "anchor" && !validTradeDate && <p className="error-line">交易日格式应为 YYYYMMDD。</p>}
              {error && <p className="error-line">{error}</p>}
              <div className="job-config-hints">
                {configHints(selectedJob).map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            </motion.div>
          </AnimatePresence>
        </section>

        <aside className="content-panel job-queue-panel">
          <PanelTitle title="运行历史" meta={runsLoading ? "同步中" : `${runningCount} 运行中`} />
          <div className="job-queue-summary">
            <span>{finishedCount} 已结束</span>
            <button className="btn btn-sm" type="button" onClick={() => void refreshRunsAndResults()} disabled={runsLoading}>
              {runsLoading ? "同步中" : "刷新"}
            </button>
          </div>
          <div className="job-list compact">
            {rows.length === 0 && <p className="empty-line">{runsLoading ? "正在加载历史作业。" : "暂无历史作业。"}</p>}
            <AnimatePresence initial={false}>
              {rows.slice(0, 8).map(({ job, run }) => (
                <motion.div
                  animate={jobMotion.animate}
                  exit={jobMotion.exit}
                  initial={jobMotion.initial}
                  key={`${job.kind}-${job.run_id}`}
                  layout
                  transition={jobMotion.transition}
                >
                  <JobRunCard
                    kind={job.kind}
                    run={run}
                    runId={job.run_id}
                    source={job.source}
                    reusedExisting={job.reused_existing}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </aside>
      </div>

    </section>
  );
}

function dateToTradeDate(value: string): string {
  return value.replace(/-/g, "");
}

function LifecyclePreviewCard({ preview, loading }: { preview: LifecycleDigestPreview | null; loading: boolean }) {
  if (loading) {
    return <p className="job-preview-muted">正在预览待处理机会。</p>;
  }
  if (!preview) {
    return <p className="job-preview-muted">暂无预览数据。</p>;
  }
  return (
    <section className="job-preview-card">
      <div className="job-preview-metrics">
        <span>扫描 {preview.scanned_count}</span>
        <span>可处理 {preview.processable_count}</span>
        <span>需调用 {preview.estimated_llm_calls}</span>
        <span>跳过 {preview.skipped_count}</span>
      </div>
    </section>
  );
}

function forceLabel(kind: JobTemplateKey): string {
  if (kind === "ingest") {
    return "强制重拉";
  }
  if (kind === "anchor") {
    return "强制刷新";
  }
  if (kind === "stockEvidenceChain") {
    return "强制重判 LLM";
  }
  if (kind === "lifecycleDigest") {
    return "强制重写摘要";
  }
  return "强制重跑";
}
