import { formatTime } from "../lib/datetime";
import type { StrategyValidationMetric, StrategyValidationSummary } from "../types";
import { PanelTitle } from "./PanelTitle";

export function StrategyValidationPanel(props: { summary: StrategyValidationSummary | null }) {
  return (
    <section className="panel strategy-validation-panel">
      <PanelTitle title="策略验证" meta="发酵确认快照回填后的 T+N 表现" />
      <FermentationValidationBody summary={props.summary} />
    </section>
  );
}

function FermentationValidationBody({ summary }: { summary: StrategyValidationSummary | null }) {
  const bucketRows = summary?.by_decision_bucket ?? [];
  const sourceRows = summary?.top_sources ?? [];
  return summary && summary.matured_stock_count > 0 ? (
    <div className="strategy-validation-body">
      <div className="strategy-validation-kpis">
        <ValidationKpi label="快照" value={summary.snapshot_count} />
        <ValidationKpi label="成熟样本" value={summary.matured_stock_count} />
        <ValidationKpi label="最新快照" value={summary.latest_snapshot_time ? formatTime(summary.latest_snapshot_time).slice(5, 16) : "-"} />
      </div>
      <ValidationTable title="分层表现" rows={bucketRows} />
      <ValidationTable title="首提来源 Top" rows={sourceRows.slice(0, 5)} compact />
    </div>
  ) : (
    <p className="strategy-validation-empty">暂无已回填快照。先在策略页保存当前快照，再到作业页回填已有快照。</p>
  );
}

function ValidationKpi(props: { label: string; value: number | string }) {
  return (
    <div className="strategy-validation-kpi">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  );
}

function ValidationTable(props: { title: string; rows: StrategyValidationMetric[]; compact?: boolean }) {
  return (
    <div className="strategy-validation-table">
      <strong>{props.title}</strong>
      {props.rows.length ? (
        props.rows.map((row) => (
          <article className="strategy-validation-row" key={row.label}>
            <span>{row.label}</span>
            <em>{row.sample_count} 样本</em>
            <b className={returnToneClass(row.average_excess_return)}>{formatPercent(row.average_excess_return, true)}</b>
            {!props.compact && <small>胜率 {formatPercent(row.win_rate)} · 回撤 {formatPercent(row.average_max_drawdown, true)}</small>}
          </article>
        ))
      ) : (
        <p className="strategy-validation-empty">暂无样本</p>
      )}
    </div>
  );
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
