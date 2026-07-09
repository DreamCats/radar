import { useEffect, useMemo, useState } from "react";
import { PauseCircle, Play, RefreshCw, TimerReset } from "lucide-react";

import {
  disableSchedule,
  enableSchedule,
  fetchRuns,
  fetchSchedules,
  fetchScheduleTicks,
  runScheduleNow,
  updateScheduleRequest,
} from "../api/radarApi";
import { JobRunCard } from "../components/JobRunCard";
import { PanelTitle } from "../components/PanelTitle";
import { trackedJobFromRun } from "../lib/jobRuns";
import type { RunItem, ScheduleItem, ScheduleTickItem } from "../types";

const RECENT_RUN_LIMIT = 80;
type CatalystScheduleOption = "publish" | "notify" | "auto_upside";

export function SchedulePage() {
  const [schedules, setSchedules] = useState<ScheduleItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [ticks, setTicks] = useState<ScheduleTickItem[]>([]);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [ticksLoading, setTicksLoading] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [requestAction, setRequestAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selected = useMemo(
    () => schedules.find((item) => item.schedule_id === selectedId) ?? schedules[0],
    [schedules, selectedId],
  );
  const runById = useMemo(() => new Map(runs.map((run) => [run.run_id, run])), [runs]);

  useEffect(() => {
    void refreshSchedules();
  }, []);

  useEffect(() => {
    if (!selected) {
      setTicks([]);
      return;
    }
    void refreshTicks(selected.schedule_id);
  }, [selected?.schedule_id]);

  async function refreshSchedules() {
    setLoading(true);
    setError(null);
    try {
      const [scheduleItems, runItems] = await Promise.all([
        fetchSchedules(),
        fetchRuns({ limit: RECENT_RUN_LIMIT }),
      ]);
      setSchedules(scheduleItems);
      setRuns(runItems);
      setSelectedId((current) => current ?? scheduleItems[0]?.schedule_id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载定时任务失败");
    } finally {
      setLoading(false);
    }
  }

  async function refreshTicks(scheduleId: string) {
    setTicksLoading(true);
    setError(null);
    try {
      const [tickItems, runItems] = await Promise.all([
        fetchScheduleTicks(scheduleId, 20),
        fetchRuns({ limit: RECENT_RUN_LIMIT }),
      ]);
      setTicks(tickItems);
      setRuns(runItems);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载触发记录失败");
    } finally {
      setTicksLoading(false);
    }
  }

  async function toggleSchedule(schedule: ScheduleItem) {
    setActionId(schedule.schedule_id);
    setError(null);
    try {
      const nextItems = schedule.enabled
        ? await disableSchedule(schedule.schedule_id)
        : await enableSchedule(schedule.schedule_id);
      setSchedules(nextItems);
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新定时任务失败");
    } finally {
      setActionId(null);
    }
  }

  async function runNow(schedule: ScheduleItem) {
    setActionId(schedule.schedule_id);
    setError(null);
    try {
      await runScheduleNow(schedule.schedule_id);
      await Promise.all([refreshSchedules(), refreshTicks(schedule.schedule_id)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "立即运行失败");
    } finally {
      setActionId(null);
    }
  }

  async function toggleCatalystOption(schedule: ScheduleItem, option: CatalystScheduleOption) {
    const actionKey = `${schedule.schedule_id}:${option}`;
    setRequestAction(actionKey);
    setError(null);
    try {
      const current = Boolean(schedule.request[option]);
      const nextRequest = { ...schedule.request, [option]: !current };
      if (option === "publish" && current) {
        nextRequest.notify = false;
      }
      if (option === "notify" && !current) {
        nextRequest.publish = true;
      }
      const nextItems = await updateScheduleRequest(schedule.schedule_id, nextRequest);
      setSchedules(nextItems);
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新任务开关失败");
    } finally {
      setRequestAction(null);
    }
  }

  return (
    <section className="schedule-page">
      <div className="schedule-header">
        <PanelTitle title="定时任务" meta={loading ? "同步中" : `${schedules.length} 个模板`} />
        <button className="btn btn-sm" type="button" onClick={() => void refreshSchedules()} disabled={loading}>
          <RefreshCw size={14} />
          {loading ? "刷新中" : "刷新"}
        </button>
      </div>
      {error && <p className="error-line">{error}</p>}

      <div className="schedule-grid">
        <aside className="content-panel schedule-list-panel">
          <PanelTitle title="模板" meta="默认关闭" />
          <div className="schedule-list">
            {schedules.map((schedule) => (
              <button
                className={selected?.schedule_id === schedule.schedule_id ? "schedule-item active" : "schedule-item"}
                key={schedule.schedule_id}
                type="button"
                onClick={() => setSelectedId(schedule.schedule_id)}
              >
                <span className={schedule.enabled ? "schedule-dot enabled" : "schedule-dot"} />
                <span>
                  <strong>{schedule.title}</strong>
                  <small>{cadenceText(schedule)}</small>
                </span>
              </button>
            ))}
            {schedules.length === 0 && <p className="empty-line">{loading ? "正在加载模板。" : "暂无定时模板。"}</p>}
          </div>
        </aside>

        <section className="content-panel schedule-detail-panel">
          {selected ? (
            <>
              <PanelTitle title={selected.title} meta={selected.enabled ? "已启用" : "已暂停"} />
              <div className="schedule-detail-grid">
                <Metric label="频率" value={cadenceText(selected)} />
                <Metric label="下次运行" value={dateTimeText(selected.next_tick_at)} />
                <Metric label="最近触发" value={dateTimeText(selected.last_tick_at)} />
                <Metric label="窗口" value={windowPresetText(selected.window_preset)} />
              </div>
              <div className="schedule-actions">
                <button
                  className={selected.enabled ? "btn schedule-stop-button" : "btn btn-primary"}
                  type="button"
                  disabled={actionId === selected.schedule_id}
                  onClick={() => void toggleSchedule(selected)}
                >
                  {selected.enabled ? <PauseCircle size={16} /> : <Play size={16} />}
                  {selected.enabled ? "暂停" : "启用"}
                </button>
                <button
                  className="btn"
                  type="button"
                  disabled={actionId === selected.schedule_id}
                  onClick={() => void runNow(selected)}
                >
                  <TimerReset size={16} />
                  立即运行
                </button>
              </div>
              {selected.job_key === "catalyst_valuation_report" && (
                <ScheduleRequestSwitches
                  disabledKey={requestAction}
                  onToggle={(option) => void toggleCatalystOption(selected, option)}
                  schedule={selected}
                />
              )}
              <div className="schedule-tags">
                {requestTags(selected).map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
            </>
          ) : (
            <p className="empty-line">请选择一个定时模板。</p>
          )}
        </section>

        <aside className="content-panel schedule-ticks-panel">
          <PanelTitle title="触发记录" meta={ticksLoading ? "同步中" : `${ticks.length} 条`} />
          <div className="schedule-tick-list">
            {ticks.map((tick) => (
              <div className="schedule-tick" key={tick.tick_id}>
                <div className="schedule-tick-main">
                  <span className={`schedule-tick-status ${tick.status}`}>{tickStatusText(tick)}</span>
                  <span>{dateTimeText(tick.fired_at ?? tick.planned_at)}</span>
                </div>
                {tick.run_ids.map((runId) => {
                  const run = runById.get(runId);
                  const job = run ? trackedJobFromRun(run, false) : null;
                  return run && job ? (
                    <JobRunCard
                      kind={job.kind}
                      key={runId}
                      run={run}
                      runId={runId}
                      source={job.source}
                      reusedExisting={job.reused_existing}
                    />
                  ) : (
                    <p className="schedule-run-id" key={runId}>{runId}</p>
                  );
                })}
              </div>
            ))}
            {ticks.length === 0 && <p className="empty-line">{ticksLoading ? "正在加载触发记录。" : "暂无触发记录。"}</p>}
          </div>
        </aside>
      </div>
    </section>
  );
}

function ScheduleRequestSwitches(props: {
  disabledKey: string | null;
  onToggle: (option: CatalystScheduleOption) => void;
  schedule: ScheduleItem;
}) {
  const options: Array<{ key: CatalystScheduleOption; label: string }> = [
    { key: "publish", label: "生成 HTML" },
    { key: "notify", label: "Bark 通知" },
    { key: "auto_upside", label: "自动测算" },
  ];
  return (
    <div className="schedule-switch-grid" aria-label="催化估值线索报告开关">
      {options.map((option) => {
        const checked = Boolean(props.schedule.request[option.key]);
        const disabled = props.disabledKey === `${props.schedule.schedule_id}:${option.key}`;
        return (
          <button
            aria-checked={checked}
            className={checked ? "schedule-switch on" : "schedule-switch"}
            disabled={disabled}
            key={option.key}
            onClick={() => props.onToggle(option.key)}
            role="switch"
            type="button"
          >
            <span className="schedule-switch-track">
              <span />
            </span>
            <strong>{option.label}</strong>
          </button>
        );
      })}
    </div>
  );
}

function Metric(props: { label: string; value: string }) {
  return (
    <div className="schedule-metric">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  );
}

function cadenceText(schedule: ScheduleItem): string {
  if (schedule.cadence_kind === "interval") {
    const minutes = Number(schedule.cadence.minutes ?? 30);
    const offset = Number(schedule.cadence.offset_minutes ?? 0);
    const base = offset > 0 ? `每 ${minutes} 分钟，延后 ${offset} 分钟` : `每 ${minutes} 分钟`;
    if (schedule.cadence.active_start && schedule.cadence.active_end) {
      return `${base} · ${String(schedule.cadence.active_start)}-${String(schedule.cadence.active_end)}`;
    }
    return base;
  }
  if (schedule.cadence_kind === "daily") {
    return `每天 ${String(schedule.cadence.time ?? "15:20")}`;
  }
  return schedule.cadence_kind;
}

function dateTimeText(value?: string | null): string {
  if (!value) {
    return "暂无";
  }
  return value.replace("T", " ").slice(0, 16);
}

function windowPresetText(value?: string | null): string {
  if (value === "yesterday_1500_to_now") {
    return "昨日 15:00 -> 当前";
  }
  if (value === "last_1h") {
    return "近 1 小时";
  }
  return value ?? "固定参数";
}

function requestTags(schedule: ScheduleItem): string[] {
  const tags = [schedule.job_key, schedule.catch_up_policy, `lag ${schedule.max_lag_minutes}m`];
  if (schedule.request.force === false) {
    tags.push("force=false");
  }
  if (schedule.request.source) {
    tags.push(`source=${String(schedule.request.source)}`);
  }
  if (schedule.request.publish === true) {
    tags.push("publish=true");
  }
  if (typeof schedule.request.notify === "boolean") {
    tags.push(`notify=${String(schedule.request.notify)}`);
  }
  if (typeof schedule.request.auto_upside === "boolean") {
    tags.push(`auto_upside=${String(schedule.request.auto_upside)}`);
  }
  return tags;
}

function tickStatusText(tick: ScheduleTickItem): string {
  if (tick.status === "submitted") {
    return tick.skipped_reason === "reused_existing" ? "复用" : "已提交";
  }
  if (tick.status === "skipped") {
    return tick.skipped_reason === "previous_tick_running" ? "上轮运行中" : "已跳过";
  }
  if (tick.status === "failed") {
    return "失败";
  }
  if (tick.status === "running") {
    return "触发中";
  }
  return "待触发";
}
