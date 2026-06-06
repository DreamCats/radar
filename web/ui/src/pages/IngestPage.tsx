import { useEffect, useMemo, useState } from "react";
import { CalendarDays, Play, RotateCcw } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import {
  fetchRuns,
  startAggregateRefineJob,
  startAnchorMessagesJob,
  startClassifyMessagesJob,
  startIngestWechatJob,
  startRecommendationBacktestJob,
  startStrategyBackfillJob,
} from "../api/radarApi";
import { DateField, SelectField, TextField } from "../components/FormFields";
import { JobRunCard } from "../components/JobRunCard";
import { PanelTitle } from "../components/PanelTitle";
import { toIso } from "../lib/datetime";
import { configHints, DEFAULT_CATEGORIES, JOB_TEMPLATES, SOURCE_OPTIONS } from "../lib/jobTemplates";
import {
  mergeRuns,
  mergeTrackedJobs,
  sourceLabel,
  trackedJobFromRun,
  type JobTemplateKey,
  type TrackedJob,
} from "../lib/jobRuns";
import { panelMotionState } from "../lib/motion";
import { buildPresetRange, rangeLabel, RANGE_PRESETS, toLocalIso, type LocalRange, type RangePreset } from "../lib/timeRange";
import type { IngestSource, RunItem } from "../types";

export function IngestPage() {
  const initialRange = useMemo(() => buildPresetRange("today"), []);
  const shouldReduceMotion = useReducedMotion();
  const [selectedJob, setSelectedJob] = useState<JobTemplateKey>("ingest");
  const [source, setSource] = useState<IngestSource>("all");
  const [range, setRange] = useState<LocalRange>(initialRange);
  const [preset, setPreset] = useState<RangePreset>("today");
  const [tradeDate, setTradeDate] = useState(() => dateToTradeDate(initialRange.endDate));
  const [force, setForce] = useState(false);
  const [trackedJobs, setTrackedJobs] = useState<TrackedJob[]>([]);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const startValue = toLocalIso(range.startDate, range.startTime);
  const endValue = toLocalIso(range.endDate, range.endTime);
  const validWindow = Boolean(startValue && endValue) && startValue <= endValue;
  const canSubmit = validWindow;
  const selectedTemplate = JOB_TEMPLATES.find((item) => item.key === selectedJob) ?? JOB_TEMPLATES[0];
  const rows = trackedJobs.map((job) => ({ job, run: runs.find((run) => run.run_id === job.run_id) }));
  const active = submitting || rows.some(({ run }) => !run || run.status === "running");
  const runningCount = rows.filter(({ run }) => !run || run.status === "running").length;
  const finishedCount = rows.length - runningCount;
  const jobMotion = panelMotionState(shouldReduceMotion);

  useEffect(() => {
    void refreshRunsAndResults();
  }, []);

  useEffect(() => {
    if (trackedJobs.length === 0) {
      return undefined;
    }

    let cancelled = false;
    let timer: number | undefined;
    const runIds = new Set(trackedJobs.map((job) => job.run_id));

    async function refresh() {
      try {
        const items = await fetchRuns();
        if (cancelled) {
          return;
        }
        setRuns(items);
        const tracked = items.filter((item) => runIds.has(item.run_id));
        const hasRunning = tracked.length < runIds.size || tracked.some((item) => item.status === "running");
        if (hasRunning) {
          timer = window.setTimeout(refresh, 4000);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "刷新运行状态失败");
          timer = window.setTimeout(refresh, 4000);
        }
      }
    }

    void refresh();
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [trackedJobs]);

  async function refreshRunsAndResults() {
    setError(null);
    try {
      const [runItems, runningItems] = await Promise.all([
        fetchRuns(),
        fetchRuns({ status: "running", limit: 50 }),
      ]);
      setRuns(mergeRuns(runItems, runningItems));
      const restoredJobs = runningItems.map(trackedJobFromRun).filter((item): item is TrackedJob => item !== null);
      if (restoredJobs.length > 0) {
        setTrackedJobs((current) => mergeTrackedJobs(restoredJobs, current));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载作业数据失败");
    }
  }

  async function submitSelectedJob() {
    setSubmitting(true);
    setError(null);
    try {
      const start_time = startValue;
      const end_time = endValue;
      const newJobs = await startJob(selectedJob, { start_time, end_time });
      setTrackedJobs((current) => mergeTrackedJobs(newJobs, current));
      await refreshRunsAndResults();
    } catch (err) {
      setError(err instanceof Error ? err.message : "作业提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function startJob(kind: JobTemplateKey, window: { start_time: string; end_time: string }): Promise<TrackedJob[]> {
    if (kind === "ingest") {
      const items = await startIngestWechatJob({
        source,
        start_time: window.start_time,
        end_time: window.end_time,
        force,
        chunk_hours: 1,
        concurrency: 4,
      });
      return items.map((item) => ({
        kind,
        source: item.source,
        run_id: item.run_id,
        reused_existing: item.reused_existing,
      }));
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
      return items.map((item) => ({
        kind,
        source: item.source,
        run_id: item.run_id,
        reused_existing: item.reused_existing,
      }));
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
      return items.map((item) => ({
        kind,
        source: sourceLabel(source),
        run_id: item.run_id,
        reused_existing: item.reused_existing,
      }));
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
      return items.map((item) => ({
        kind,
        source: sourceLabel(source),
        run_id: item.run_id,
        reused_existing: item.reused_existing,
      }));
    }
    if (kind === "strategyBackfill") {
      const items = await startStrategyBackfillJob({
        start_time: window.start_time,
        end_time: window.end_time,
        windows: [1, 3, 5, 10],
        benchmark_ts_code: "000300.SH",
      });
      return items.map((item) => ({
        kind,
        source: "机会信号",
        run_id: item.run_id,
        reused_existing: item.reused_existing,
      }));
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
    return items.map((item) => ({
      kind,
      source: sourceLabel(source),
      run_id: item.run_id,
      reused_existing: item.reused_existing,
    }));
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
    const needsHistoryWindow = kind === "backtest" || kind === "strategyBackfill";
    if (needsHistoryWindow && selectedJob !== kind && preset === "today") {
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

      <div className="range-presets" aria-label="快捷时间窗口">
        {RANGE_PRESETS.map(([value, label]) => (
          <button
            className={preset === value ? "preset-button active" : "preset-button"}
            key={value}
            type="button"
            onClick={() => applyPreset(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="job-center-grid">
        <aside className="content-panel job-template-panel">
          <PanelTitle title="作业类型" meta={`${JOB_TEMPLATES.length} 个模板`} />
          <div className="job-template-list">
            {JOB_TEMPLATES.map((item) => {
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
                  </span>
                </button>
              );
            })}
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
                <PanelTitle title={selectedTemplate.title} meta={selectedTemplate.meta} />
              </div>
              <div className="job-config-grid">
                {selectedJob !== "strategyBackfill" && (
                  <SelectField label="来源" value={source} onChange={(value) => setSource(value as IngestSource)} options={SOURCE_OPTIONS} />
                )}
                <DateField label="开始" value={startValue} onChange={(value) => updateDateTime("start", value)} />
                <DateField label="结束" value={endValue} onChange={(value) => updateDateTime("end", value)} />
                {(selectedJob === "anchor" || selectedJob === "refine") && (
                  <TextField label="交易日" value={tradeDate} onChange={setTradeDate} />
                )}
                {selectedJob !== "strategyBackfill" && (
                  <label className="toggle-field">
                    <input checked={force} type="checkbox" onChange={(event) => setForce(event.target.checked)} />
                    <span>{forceLabel(selectedJob)}</span>
                  </label>
                )}
                <button className="primary-button ingest-submit" type="button" disabled={active || !canSubmit} onClick={submitSelectedJob}>
                  {active ? <RotateCcw size={16} /> : <Play size={16} />}
                  {submitting ? "提交中" : active ? "运行中" : "开始执行"}
                </button>
              </div>
              {!validWindow && <p className="error-line">请选择有效的开始和结束时间。</p>}
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
          <PanelTitle title="运行队列" meta={`${runningCount} 运行中`} />
          <div className="job-queue-summary">
            <span>{finishedCount} 已结束</span>
            <button className="btn btn-sm" type="button" onClick={() => void refreshRunsAndResults()}>
              刷新
            </button>
          </div>
          <div className="job-list compact">
            {rows.length === 0 && <p className="empty-line">暂无跟踪作业。</p>}
            <AnimatePresence initial={false}>
              {rows.slice(0, 5).map(({ job, run }) => (
                <motion.div
                  animate={jobMotion.animate}
                  exit={jobMotion.exit}
                  initial={jobMotion.initial}
                  key={`${job.kind}-${job.run_id}`}
                  layout
                  transition={jobMotion.transition}
                >
                  <JobRunCard
                    kind={job.kind === "refine" ? "refine" : job.kind}
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

function backtestWindowDays(startDate: string, endDate: string): number {
  const start = new Date(`${startDate}T00:00:00`).getTime();
  const end = new Date(`${endDate}T00:00:00`).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
    return 30;
  }
  return Math.max(1, Math.round((end - start) / 86400000) + 1);
}

function forceLabel(kind: JobTemplateKey): string {
  if (kind === "ingest") {
    return "强制重拉";
  }
  return "强制重跑";
}
