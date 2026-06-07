import { formatTime } from "../lib/datetime";
import type { SourceRadarValidationSummary, StrategyValidationMetric, StrategyValidationSummary } from "../types";
import { PanelTitle } from "./PanelTitle";

type ValidationMode = "fermentation" | "source";

export function StrategyValidationPanel(props: {
  summary: StrategyValidationSummary | null;
  sourceSummary: SourceRadarValidationSummary | null;
  activeMode: ValidationMode;
  onModeChange: (mode: ValidationMode) => void;
}) {
  return (
    <section className="panel strategy-validation-panel">
      <PanelTitle title="策略验证" meta="不同策略分开看，避免混淆胜率口径" />
      <div className="strategy-validation-tabs" role="tablist" aria-label="策略验证类型">
        <ValidationTab active={props.activeMode === "fermentation"} label="发酵确认" onClick={() => props.onModeChange("fermentation")} />
        <ValidationTab active={props.activeMode === "source"} label="源头雷达" onClick={() => props.onModeChange("source")} />
      </div>
      {props.activeMode === "source" ? (
        <SourceValidationBody summary={props.sourceSummary} />
      ) : (
        <FermentationValidationBody summary={props.summary} />
      )}
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

function SourceValidationBody({ summary }: { summary: SourceRadarValidationSummary | null }) {
  return summary && summary.signal_count > 0 ? (
    <div className="strategy-validation-body">
      <div className="strategy-validation-kpis">
        <ValidationKpi label="快照" value={summary.snapshot_count} />
        <ValidationKpi label="源头信号" value={summary.signal_count} />
        <ValidationKpi label="扩散" value={formatPercent(ratio(summary.spreading_count, summary.signal_count))} />
        <ValidationKpi label="绑定个股" value={formatPercent(ratio(summary.mapped_count, summary.signal_count))} />
      </div>
      <SourceMetricTable rows={summary.by_first_status} />
      <div className="strategy-validation-table">
        <strong>源头演化 Top</strong>
        {summary.top_signals.map((row) => (
          <article className="strategy-validation-row source" key={row.signal_id}>
            <span>{row.title}</span>
            <em>{row.mapped_stocks.length ? row.mapped_stocks.join(" / ") : "未绑定个股"}</em>
            <b>{row.mapped_days !== null && row.mapped_days !== undefined ? `${row.mapped_days}天绑定` : "未绑定"}</b>
            <small>
              {formatTime(row.first_as_of_time).slice(5, 16)} 到 {formatTime(row.latest_as_of_time).slice(5, 16)}
              {row.spread_days !== null && row.spread_days !== undefined ? ` · ${row.spread_days}天扩散` : ""}
            </small>
          </article>
        ))}
      </div>
    </div>
  ) : (
    <p className="strategy-validation-empty">暂无源头雷达验证样本。先在作业页按天生成多天“源头雷达快照”。</p>
  );
}

function SourceMetricTable({ rows }: { rows: SourceRadarValidationSummary["by_first_status"] }) {
  return (
    <div className="strategy-validation-table">
      <strong>首现状态转化</strong>
      {rows.length ? (
        rows.map((row) => (
          <article className="strategy-validation-row" key={row.label}>
            <span>{row.label}</span>
            <em>{row.sample_count} 样本</em>
            <b>{formatPercent(row.rate)}</b>
            <small>平均 {row.average_days !== null && row.average_days !== undefined ? `${row.average_days.toFixed(1)}天` : "-"}</small>
          </article>
        ))
      ) : (
        <p className="strategy-validation-empty">暂无样本</p>
      )}
    </div>
  );
}

function ValidationTab(props: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button className={props.active ? "active" : ""} type="button" role="tab" aria-selected={props.active} onClick={props.onClick}>
      {props.label}
    </button>
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
            <b>{formatPercent(row.average_excess_return, true)}</b>
            {!props.compact && <small>胜率 {formatPercent(row.win_rate)} · 回撤 {formatPercent(row.average_max_drawdown, true)}</small>}
          </article>
        ))
      ) : (
        <p className="strategy-validation-empty">暂无样本</p>
      )}
    </div>
  );
}

function ratio(count: number, total: number): number | null {
  return total > 0 ? count / total : null;
}

function formatPercent(value?: number | null, signed = false): string {
  if (value === undefined || value === null) {
    return "-";
  }
  const text = `${(value * 100).toFixed(1)}%`;
  return signed && value > 0 ? `+${text}` : text;
}
