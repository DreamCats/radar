import { useEffect, useState } from "react";
import { CalendarDays, CheckCircle2, Play, RotateCcw } from "lucide-react";

import { fetchRuns, startIngestWechatJob } from "../api/radarApi";
import { DateField, SelectField } from "../components/FormFields";
import { PanelTitle } from "../components/PanelTitle";
import { toIso } from "../lib/datetime";
import type { IngestJobItem, IngestSource, RunItem } from "../types";

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
  const [range, setRange] = useState<LocalRange>(() => buildPresetRange("today"));
  const [preset, setPreset] = useState<RangePreset>("today");
  const [force, setForce] = useState(false);
  const [jobs, setJobs] = useState<IngestJobItem[]>([]);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const startValue = toLocalIso(range.startDate, range.startTime);
  const endValue = toLocalIso(range.endDate, range.endTime);
  const canSubmit = Boolean(startValue && endValue) && startValue <= endValue;
  const rows = jobs.map((job) => ({ job, run: runs.find((run) => run.run_id === job.run_id) }));
  const active = submitting || rows.some(({ run }) => !run || run.status === "running");
  const totals = summarizeRuns(rows.map(({ run }) => run).filter((run): run is RunItem => Boolean(run)));

  useEffect(() => {
    if (jobs.length === 0) {
      return undefined;
    }

    let cancelled = false;
    let timer: number | undefined;
    const runIds = new Set(jobs.map((job) => job.run_id));

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
  }, [jobs]);

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
        <PanelTitle title="微信数据源" meta="窗口同步" />
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
            <span>分片</span>
            <strong>1h</strong>
          </div>
          <div className="ingest-stat">
            <span>并发</span>
            <strong>4</strong>
          </div>
          <div className="ingest-stat">
            <span>窗口</span>
            <strong>{preset === "custom" ? "自定义" : PRESETS.find(([value]) => value === preset)?.[1]}</strong>
          </div>
        </aside>
      </div>

      <section className="content-panel ingest-results">
        <div className="ingest-result-head">
          <div>
            <h2>拉取结果</h2>
            <p>{jobs.length ? `${active ? "运行中" : "已完成"} · 来源 ${jobs.length} 个` : "等待执行"}</p>
          </div>
          {jobs.length > 0 && (
            <div className="result-total">
              <CheckCircle2 size={16} />
              raw {totals.raw} / filtered {totals.filtered} / stored {totals.stored}
            </div>
          )}
        </div>
        <div className="run-list">
          {rows.map(({ job, run }) => (
            <p className="result-line" key={`${job.source_key}-${job.run_id}`}>
              {job.source}: {runStatusLabel(run)} raw={run?.raw_count ?? 0} filtered={run?.filtered_count ?? 0}
              stored={run?.stored_count ?? 0} run_id={job.run_id}
              {job.reused_existing ? " · 已复用运行中任务" : ""}
            </p>
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

function summarizeRuns(runs: RunItem[]) {
  return runs.reduce(
    (total, item) => ({
      raw: total.raw + item.raw_count,
      filtered: total.filtered + item.filtered_count,
      stored: total.stored + item.stored_count,
    }),
    { raw: 0, filtered: 0, stored: 0 },
  );
}

function runStatusLabel(run: RunItem | undefined): string {
  if (!run || run.status === "running") {
    return "运行中";
  }
  if (run.status === "succeeded") {
    return "成功";
  }
  if (run.status === "skipped") {
    return "已覆盖";
  }
  return `失败${run.error_message ? `：${run.error_message}` : ""}`;
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
