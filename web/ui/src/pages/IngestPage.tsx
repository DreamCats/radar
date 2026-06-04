import { useState } from "react";
import { CalendarDays, CheckCircle2, Play, RotateCcw } from "lucide-react";

import { ingestWechat } from "../api/radarApi";
import { SelectField } from "../components/FormFields";
import { PanelTitle } from "../components/PanelTitle";
import type { IngestResultItem, IngestSource } from "../types";

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
  const [result, setResult] = useState<IngestResultItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const startValue = toLocalIso(range.startDate, range.startTime);
  const endValue = toLocalIso(range.endDate, range.endTime);
  const canSubmit = Boolean(startValue && endValue) && startValue <= endValue;
  const totals = summarizeResult(result);

  async function submit() {
    setLoading(true);
    setError(null);
    try {
      const items = await ingestWechat({
        source,
        start_time: startValue,
        end_time: endValue,
        force,
        chunk_hours: 1,
        concurrency: 4,
      });
      setResult(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "拉取失败");
    } finally {
      setLoading(false);
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

            <DateTimeGroup
              label="开始"
              date={range.startDate}
              time={range.startTime}
              onDateChange={(value) => updateRange("startDate", value)}
              onTimeChange={(value) => updateRange("startTime", value)}
            />
            <DateTimeGroup
              label="结束"
              date={range.endDate}
              time={range.endTime}
              onDateChange={(value) => updateRange("endDate", value)}
              onTimeChange={(value) => updateRange("endTime", value)}
            />

            <label className="toggle-field">
              <input checked={force} type="checkbox" onChange={(event) => setForce(event.target.checked)} />
              <span>强制重拉</span>
            </label>

            <button className="primary-button ingest-submit" type="button" disabled={loading || !canSubmit} onClick={submit}>
              {loading ? <RotateCcw size={16} /> : <Play size={16} />}
              {loading ? "拉取中" : "开始拉取"}
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
            <p>{result.length ? `来源 ${result.length} 个` : "等待执行"}</p>
          </div>
          {result.length > 0 && (
            <div className="result-total">
              <CheckCircle2 size={16} />
              raw {totals.raw} / filtered {totals.filtered} / stored {totals.stored}
            </div>
          )}
        </div>
        <div className="run-list">
          {result.map((item) => (
            <p className="result-line" key={`${item.source_key}-${item.run_id}`}>
              {item.source}: chunks={item.chunk_count} skipped={item.skipped_count} raw={item.raw_count}
              filtered={item.filtered_count} stored={item.stored_count} run_id={item.run_id}
            </p>
          ))}
        </div>
      </section>
    </section>
  );
}

function DateTimeGroup(props: {
  label: string;
  date: string;
  time: string;
  onDateChange: (value: string) => void;
  onTimeChange: (value: string) => void;
}) {
  return (
    <div className="date-time-group">
      <span>{props.label}</span>
      <div>
        <input type="date" value={props.date} onChange={(event) => props.onDateChange(event.target.value)} />
        <input type="time" value={props.time} onChange={(event) => props.onTimeChange(event.target.value)} />
      </div>
    </div>
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

function summarizeResult(items: IngestResultItem[]) {
  return items.reduce(
    (total, item) => ({
      raw: total.raw + item.raw_count,
      filtered: total.filtered + item.filtered_count,
      stored: total.stored + item.stored_count,
    }),
    { raw: 0, filtered: 0, stored: 0 },
  );
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
