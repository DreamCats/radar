import { ArrowRight, TrendingUp } from "lucide-react";

import { formatTime } from "../lib/datetime";
import type { StrategyDashboard, StrategyOpportunity } from "../types";
import { PanelTitle } from "./PanelTitle";

export function StrategyTopSummary(props: { data: StrategyDashboard | null; onOpenStrategy?: () => void }) {
  const opportunities = props.data?.opportunities.slice(0, 3) ?? [];
  return (
    <section className="panel strategy-summary-panel">
      <PanelTitle
        title="发酵确认 Top3"
        meta={props.data ? `${formatTime(props.data.recent_start_time)} 起 · 策略信号` : "等待策略数据"}
      >
        {props.onOpenStrategy && (
          <button className="btn btn-sm" type="button" onClick={props.onOpenStrategy}>
            <ArrowRight size={15} />
            策略
          </button>
        )}
      </PanelTitle>
      {opportunities.length ? (
        <div className="strategy-summary-list">
          {opportunities.map((item) => (
            <SummaryCard item={item} key={item.key} />
          ))}
        </div>
      ) : (
        <p className="empty-line">暂无策略机会。</p>
      )}
    </section>
  );
}

function SummaryCard({ item }: { item: StrategyOpportunity }) {
  return (
    <article className="strategy-summary-card">
      <div className="strategy-summary-card-head">
        <span className={levelClass(item.attention_level)}>{item.attention_level}</span>
        <strong>{item.name}</strong>
        <em>{item.score.toFixed(0)}</em>
      </div>
      <p>{item.reason}</p>
      <div className="strategy-summary-metrics">
        <span>
          <TrendingUp size={13} />
          {item.acceleration.toFixed(1)}x
        </span>
        <span>{formatPercent(item.opportunity_backtest.average_excess_return_t5, true)}</span>
        <span>
          {item.opportunity_backtest.matured_event_count}/{item.opportunity_backtest.event_count || item.recent_message_count}成熟
        </span>
      </div>
    </article>
  );
}

function levelClass(level: StrategyOpportunity["attention_level"]): string {
  return `strategy-level strategy-level-${level}`;
}

function formatPercent(value?: number | null, signed = false): string {
  if (value === undefined || value === null) {
    return "无回测";
  }
  const text = `${(value * 100).toFixed(1)}%`;
  return signed && value > 0 ? `+${text}` : text;
}
