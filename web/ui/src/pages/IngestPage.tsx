import { useEffect, useState } from "react";
import { Bot, CalendarDays, Play, RotateCcw } from "lucide-react";

import { fetchRuns, startClassifyMessagesJob, startIngestWechatJob } from "../api/radarApi";
import { DateField, SelectField } from "../components/FormFields";
import { JobRunCard } from "../components/JobRunCard";
import { PanelTitle } from "../components/PanelTitle";
import { toIso } from "../lib/datetime";
import type { ClassifyJobItem, IngestJobItem, IngestSource, RunItem } from "../types";

type RangePreset = "today" | "yesterday" | "last24h" | "last7d" | "custom";

type LocalRange = {
  startDate: string;
  startTime: string;
  endDate: string;
  endTime: string;
};

const PRESETS: Array<[RangePreset, string]> = [
  ["today", "今天"],
  ["yesterday", "昨天"],
  ["last24h", "近 24 小时"],
  ["last7d", "近 7 天"],
];

export function IngestPage() {
  const [source, setSource] = useState<IngestSource>("all");
  const [classifySource, setClassifySource] = useState<IngestSource>("all");
  const [range, setRange] = useState<LocalRange>(() => buildPresetRange("today"));
  const [preset, setPreset] = useState<RangePreset>("today");
  const [force, setForce] = useState(false);
  const [classifyForce, setClassifyForce] = useState(false);
  const [jobs, setJobs] = useState<IngestJobItem[]>([]);
  const [classifyJobs, setClassifyJobs] = useState<ClassifyJobItem[]>([]);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [classifySubmitting, setClassifySubmitting] = useState(false);

  const startValue = toLocalIso(range.startDate, range.startTime);
  const endValue = toLocalIso(range.endDate, range.endTime);
  const canSubmit = Boolean(startValue && endValue) && startValue <= endValue;
  const rows = jobs.map((job) => ({ job, run: runs.find((run) => run.run_id === job.run_id) }));
  const classifyRows = classifyJobs.map((job) => ({ job, run: runs.find((run) => run.run_id === job.run_id) }));
  const active = submitting || rows.some(({ run }) => !run || run.status === "running");
  const classifyActive = classifySubmitting || classifyRows.some(({ run }) => !run || run.status === "running");
  const anyActive = active || classifyActive;
  const trackedRuns = [...rows, ...classifyRows].map(({ run }) => run).filter((run): run is RunItem => Boolean(run));
  const finishedCount = trackedRuns.filter((run) => run.status !== "running").length;
  const runningCount = jobs.length + classifyJobs.length - finishedCount;

  useEffect(() => {
    const trackedJobs = [...jobs, ...classifyJobs];
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
  }, [jobs, classifyJobs]);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const items = await startIngestWechatJob({
        source,
        start_time: startValue,
        end_time: endValue,
        force,
        chunk_hours: 1,
        concurrency: 4,
      });
      setJobs(items);
      setRuns([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "拉取失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitClassify() {
    setClassifySubmitting(true);
    setError(null);
    try {
      const items = await startClassifyMessagesJob({
        source: classifySource,
        start_time: startValue,
        end_time: endValue,
        force: classifyForce,
        chunk_hours: 1,
        limit: 500,
        batch_size: 16,
        max_concurrency: 10,
        low_confidence_threshold: 0.65,
      });
      setClassifyJobs(items);
      setRuns([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "分类失败");
    } finally {
      setClassifySubmitting(false);
    }
  }

  function applyPreset(value: RangePreset) {
    setPreset(value);
    setRange(buildPresetRange(value));
  }

  function updateRange(key: keyof LocalRange, value: string) {
    setPreset("custom");
    setRange((current) => ({ ...current, [key]: value }));
  }

  function updateDateTime(target: "start" | "end", value: string) {
    const nextValue = toIso(value);
    const [date, time = ""] = nextValue.split("T");
    const dateKey = target === "start" ? "startDate" : "endDate";
    const timeKey = target === "start" ? "startTime" : "endTime";
    setPreset("custom");
    setRange((current) => ({ ...current, [dateKey]: date ?? "", [timeKey]: time.slice(0, 5) }));
  }

  return (
    <section className="ingest-page">
      <div className="ingest-header">
        <PanelTitle title="数据作业" meta="拉取 / 分类" />
        <div className="ingest-window-pill">
          <CalendarDays size={15} />
          {rangeLabel(range)}
        </div>
      </div>

      <div className="range-presets" aria-label="快捷时间窗口">
        {PRESETS.map(([value, label]) => (
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

      <div className="ingest-grid">
        <section className="content-panel ingest-control-panel">
          <div className="ingest-card-head">
            <PanelTitle title="微信数据源" meta="原始入库" />
          </div>
          <div className="ingest-form-v2">
            <SelectField
              label="来源"
              value={source}
              onChange={(value) => setSource(value as IngestSource)}
              options={[
                ["all", "全部"],
                ["personal_message", "个人消息"],
                ["group_message", "个人群"],
              ]}
            />

            <DateField
              label="开始"
              value={startValue}
              onChange={(value) => updateDateTime("start", value)}
            />
            <DateField
              label="结束"
              value={endValue}
              onChange={(value) => updateDateTime("end", value)}
            />

            <label className="toggle-field">
              <input checked={force} type="checkbox" onChange={(event) => setForce(event.target.checked)} />
              <span>强制重拉</span>
            </label>

            <button className="primary-button ingest-submit" type="button" disabled={active || !canSubmit} onClick={submit}>
              {active ? <RotateCcw size={16} /> : <Play size={16} />}
              {submitting ? "提交中" : active ? "拉取中" : "开始拉取"}
            </button>
          </div>
          {!canSubmit && <p className="error-line">请选择有效的开始和结束时间。</p>}
          {error && <p className="error-line">{error}</p>}
        </section>

        <aside className="ingest-side">
          <div className="ingest-stat">
            <span>拉取分片</span>
            <strong>1h</strong>
          </div>
          <div className="ingest-stat">
            <span>拉取并发</span>
            <strong>4</strong>
          </div>
          <div className="ingest-stat">
            <span>窗口</span>
            <strong>{preset === "custom" ? "自定义" : PRESETS.find(([value]) => value === preset)?.[1]}</strong>
          </div>
        </aside>
      </div>

      <div className="ingest-grid">
        <section className="content-panel ingest-control-panel">
          <div className="ingest-card-head">
            <PanelTitle title="消息分类" meta="LLM 派生" />
          </div>
          <div className="ingest-form-v2">
            <SelectField
              label="来源"
              value={classifySource}
              onChange={(value) => setClassifySource(value as IngestSource)}
              options={[
                ["all", "全部"],
                ["personal_message", "个人消息"],
                ["group_message", "个人群"],
              ]}
            />

            <DateField
              label="开始"
              value={startValue}
              onChange={(value) => updateDateTime("start", value)}
            />
            <DateField
              label="结束"
              value={endValue}
              onChange={(value) => updateDateTime("end", value)}
            />

            <label className="toggle-field">
              <input checked={classifyForce} type="checkbox" onChange={(event) => setClassifyForce(event.target.checked)} />
              <span>强制重跑</span>
            </label>
            <button
              className="primary-button ingest-submit"
              type="button"
              disabled={classifyActive || !canSubmit}
              onClick={submitClassify}
            >
              {classifyActive ? <RotateCcw size={16} /> : <Bot size={16} />}
              {classifySubmitting ? "提交中" : classifyActive ? "分类中" : "开始分类"}
            </button>
          </div>
        </section>

        <aside className="ingest-side">
          <div className="ingest-stat">
            <span>时间分片</span>
            <strong>1h</strong>
          </div>
          <div className="ingest-stat">
            <span>单批消息</span>
            <strong>16</strong>
          </div>
          <div className="ingest-stat">
            <span>LLM 并发</span>
            <strong>10</strong>
          </div>
        </aside>
      </div>

      <section className="content-panel ingest-results">
        <div className="ingest-result-head">
          <div>
            <h2>作业结果</h2>
            <p>{jobs.length || classifyJobs.length ? `${anyActive ? "运行中" : "已完成"} · 作业 ${jobs.length + classifyJobs.length} 个` : "等待执行"}</p>
          </div>
          {jobs.length + classifyJobs.length > 0 && (
            <div className="result-total">
              {runningCount} 个运行中 / {finishedCount} 个已结束
            </div>
          )}
        </div>
        <div className="job-list">
          {jobs.length + classifyJobs.length === 0 && (
            <p className="empty-line">暂无作业。选择时间窗口后，可以先拉取微信数据源，再执行消息分类。</p>
          )}
          {rows.map(({ job, run }) => (
            <JobRunCard
              key={`${job.source_key}-${job.run_id}`}
              kind="ingest"
              run={run}
              runId={job.run_id}
              source={job.source}
              reusedExisting={job.reused_existing}
            />
          ))}
          {classifyRows.map(({ job, run }) => (
            <JobRunCard
              key={`classify-${job.source_key}-${job.run_id}`}
              kind="classify"
              run={run}
              runId={job.run_id}
              source={job.source}
              reusedExisting={job.reused_existing}
            />
          ))}
        </div>
      </section>
    </section>
  );
}

function buildPresetRange(preset: RangePreset): LocalRange {
  const now = new Date();
  if (preset === "yesterday") {
    const day = addDays(startOfDay(now), -1);
    return buildRange(day, endOfDay(day));
  }
  if (preset === "last24h") {
    return buildRange(addHours(now, -24), now);
  }
  if (preset === "last7d") {
    return buildRange(addDays(now, -7), now);
  }
  return buildRange(startOfDay(now), now);
}

// 前端只负责生成本地时间窗口，后端继续按同一 ingest API 执行。
function buildRange(start: Date, end: Date): LocalRange {
  return {
    startDate: formatDate(start),
    startTime: formatTime(start),
    endDate: formatDate(end),
    endTime: formatTime(end),
  };
}

function toLocalIso(date: string, time: string): string {
  return date && time ? `${date}T${time}:00` : "";
}

function rangeLabel(range: LocalRange): string {
  return `${range.startDate} ${range.startTime} - ${range.endDate} ${range.endTime}`;
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 0, 0);
}

function endOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 23, 59);
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function addHours(date: Date, hours: number): Date {
  return new Date(date.getTime() + hours * 60 * 60 * 1000);
}

function formatDate(date: Date): string {
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function formatTime(date: Date): string {
  const hour = `${date.getHours()}`.padStart(2, "0");
  const minute = `${date.getMinutes()}`.padStart(2, "0");
  return `${hour}:${minute}`;
}
