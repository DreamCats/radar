import { Activity, Clock3, Gauge, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";

import { formatTime } from "../lib/datetime";
import type { LeadSignalBucket, LeadSignalSample, LeadSignalSourceStat, LeadSignalSummary } from "../types";
import { PanelTitle } from "./PanelTitle";

export function LeadSignalPanel(props: {
  summary: LeadSignalSummary | null;
  selectedDate: string;
  onDateChange: (value: string) => void;
}) {
  const { summary, selectedDate, onDateChange } = props;
  const buckets = summary?.buckets ?? [];
  const samples = summary?.samples ?? [];
  const sources = summary?.source_stats ?? [];

  return (
    <>
      <div className="statbar metric-grid">
        <Metric label="当日股票" value={summary?.day_stock_day_count ?? 0} detail="选定日期去重股票" />
        <Metric label="当日未热" value={summary?.day_non_hot_stock_day_count ?? 0} detail="T日未明显上涨" />
        <Metric
          label="验证涨前"
          value={summary?.pre_rise_stock_day_count ?? 0}
          detail={`近 ${summary?.validation_days ?? 30} 天 T+1 上涨`}
        />
        <Metric
          label="验证近涨停"
          value={summary?.limit_like_stock_day_count ?? 0}
          detail={`T日 >= ${summary?.limit_like_pct ?? 9.5}%`}
        />
      </div>
      <div className="strategy-grid">
        <section className="panel strategy-main-panel">
          <PanelTitle
            title="当日信号"
            meta={
              summary
                ? `${summary.as_of_date} · ${summary.benchmark_ts_code} · ${summary.day_event_count} 条推荐事件`
                : "等待涨前验证数据"
            }
          />
          <div className="lead-date-toolbar">
            <label>
              <span>查看日期</span>
              <input type="date" value={selectedDate} onChange={(event) => onDateChange(event.target.value)} />
            </label>
            {summary?.available_dates.length ? (
              <span>最近有数据：{summary.available_dates.slice(0, 3).join(" / ")}</span>
            ) : null}
          </div>
          <div className="strategy-opportunity-list">
            {samples.length ? (
              samples.map((item) => <LeadSampleCard item={item} key={`${item.event_date}-${item.ts_code}`} />)
            ) : (
              <p className="empty-line">暂无涨前候选。</p>
            )}
          </div>
        </section>
        <aside className="strategy-side-stack">
          <section className="panel">
            <PanelTitle title="来源画像" meta={`近 ${summary?.validation_days ?? 30} 天成熟样本`} />
            <div className="strategy-compact-list">
              {sources.length ? (
                sources.map((item) => <LeadSourceRow item={item} key={item.source_name} />)
              ) : (
                <p className="empty-line">暂无来源样本。</p>
              )}
            </div>
          </section>
          <section className="panel">
            <PanelTitle title="策略回测" meta={`近 ${summary?.validation_days ?? 30} 天 · T日状态 x 后续窗口`} />
            <div className="lead-bucket-list">
              {buckets.length ? (
                buckets.map((item) => <BucketRow item={item} key={`${item.label}-${item.window_days}`} />)
              ) : (
                <p className="empty-line">暂无分桶数据。</p>
              )}
            </div>
          </section>
        </aside>
      </div>
    </>
  );
}

function LeadSampleCard({ item }: { item: LeadSignalSample }) {
  const t1 = windowValue(item, 1);
  const t3 = windowValue(item, 3);
  const t5 = windowValue(item, 5);
  return (
    <article className="strategy-opportunity-card">
      <div className="strategy-opportunity-head">
        <div>
          <span className="strategy-level strategy-level-重点关注">涨前信号</span>
          <span className={labelClass(item.signal_label)}>{item.signal_label}</span>
          <h2>{item.stock_name}</h2>
        </div>
        <div className="strategy-score">
          <strong className={returnToneClass(t1?.return_rate)}>{formatPercent(t1?.return_rate, true)}</strong>
          <span>T+1</span>
        </div>
      </div>
      <p className="strategy-reason">
        {item.event_date} · T日 {formatPctNumber(item.message_day_pct_chg)} · 收盘 {formatPrice(item.base_close)} ·{" "}
        {item.event_count} 条推荐
      </p>
      <div className="strategy-signal-grid">
        <Signal label="首条" value={formatTime(item.first_message_time).slice(5, 16)} icon={<Clock3 size={15} />} />
        <Signal label="T日涨幅" value={formatPctNumber(item.message_day_pct_chg)} icon={<Activity size={15} />} tone={item.message_day_pct_chg} />
        <Signal label="T+3" value={formatPercent(t3?.return_rate, true)} icon={<TrendingUp size={15} />} tone={t3?.return_rate} />
        <Signal label="T+5" value={formatPercent(t5?.return_rate, true)} icon={<Gauge size={15} />} tone={t5?.return_rate} />
      </div>
      <div className="strategy-backtest-strip">
        {[t1, t3, t5].filter(Boolean).map((window) => (
          <div className="strategy-backtest-metric" key={window?.window_days}>
            <span>T+{window?.window_days}</span>
            <strong className={returnToneClass(window?.return_rate)}>{formatPercent(window?.return_rate, true)}</strong>
            <em className={returnToneClass(window?.excess_return_rate)}>超额 {formatPercent(window?.excess_return_rate, true)}</em>
          </div>
        ))}
      </div>
      <div className="strategy-tag-row">
        <span className="strategy-chip">{item.ts_code}</span>
        {item.source_names.slice(0, 6).map((source) => (
          <span className="strategy-chip positive" key={source}>
            {source}
          </span>
        ))}
      </div>
    </article>
  );
}

function LeadSourceRow({ item }: { item: LeadSignalSourceStat }) {
  return (
    <article className="strategy-compact-row lead-source-row">
      <div className="strategy-compact-main">
        <strong>{item.source_name}</strong>
        <span>{item.non_hot_event_count} 未热</span>
      </div>
      <span>
        涨前 {item.pre_rise_event_count} · 强涨前 {item.strong_pre_rise_event_count} · 近涨停 {item.limit_like_event_count}
      </span>
      <em className={returnToneClass(item.average_t1_excess_return)}>
        胜率 {formatPercent(item.pre_rise_rate)} · T+1 {formatPercent(item.average_t1_excess_return, true)}
      </em>
    </article>
  );
}

function BucketRow({ item }: { item: LeadSignalBucket }) {
  return (
    <article className="lead-bucket-row">
      <strong>{item.label}</strong>
      <span>T+{item.window_days}</span>
      <em>{item.event_count} 事件</em>
      <b className={returnToneClass(item.average_excess_return)}>{formatPercent(item.average_excess_return, true)}</b>
      <small>上涨 {formatPercent(item.up_rate)}</small>
    </article>
  );
}

function Metric(props: { label: string; value: number | string; detail: string }) {
  return (
    <article className="stat metric-card">
      <p className="k">{props.label}</p>
      <strong className="v">{props.value}</strong>
      <span className="sub">{props.detail}</span>
    </article>
  );
}

function Signal(props: { label: string; value: string; icon: ReactNode; tone?: number | null }) {
  return (
    <div className="strategy-signal">
      <span>
        {props.icon}
        {props.label}
      </span>
      <strong className={props.tone !== undefined ? returnToneClass(props.tone) : ""}>{props.value}</strong>
    </div>
  );
}

function windowValue(item: LeadSignalSample, windowDays: number) {
  return item.windows.find((window) => window.window_days === windowDays);
}

function formatPercent(value?: number | null, signed = false): string {
  if (value === undefined || value === null) {
    return "-";
  }
  const text = `${(value * 100).toFixed(1)}%`;
  return signed && value > 0 ? `+${text}` : text;
}

function returnToneClass(value?: number | null): string {
  if (value === undefined || value === null || value === 0) {
    return "return-flat";
  }
  return value > 0 ? "return-up" : "return-down";
}

function formatPctNumber(value?: number | null): string {
  if (value === undefined || value === null) {
    return "-";
  }
  const text = `${value.toFixed(1)}%`;
  return value > 0 ? `+${text}` : text;
}

function formatPrice(value?: number | null): string {
  return value === undefined || value === null ? "-" : value.toFixed(2);
}

function labelClass(label: string): string {
  return `strategy-lead-label strategy-lead-label-${label}`;
}
