import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Gauge, RefreshCw, ShieldAlert, TrendingUp, Users } from "lucide-react";

import { fetchStrategyOpportunities } from "../api/radarApi";
import { PageLoadingState, PageRefreshProgress } from "../components/PageLoadingState";
import { PanelTitle } from "../components/PanelTitle";
import { formatTime } from "../lib/datetime";
import type { StrategyDashboard, StrategyOpportunity, StrategySourceSignal, StrategyStockCandidate } from "../types";

export function StrategyPage() {
  const [data, setData] = useState<StrategyDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchStrategyOpportunities({ days: 30, recent_days: 7, limit: 12 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const opportunities = data?.opportunities ?? [];
  const focusCount = opportunities.filter((item) => item.attention_level === "重点关注").length;
  const riskCount = opportunities.filter((item) => item.attention_level === "风险升高").length;
  const initialLoading = loading && !data;

  return (
    <section className="strategy-page">
      <div className="dashboard-actions">
        <p>{initialLoading ? "正在加载机会信号策略" : data ? `策略窗口 ${formatTime(data.start_time)} - ${formatTime(data.end_time)}` : "暂无策略数据"}</p>
        <div>
          {loading && !initialLoading && <PageRefreshProgress label="正在刷新策略" />}
          <button className="btn btn-sm" type="button" onClick={() => void refresh()} disabled={loading}>
            <RefreshCw size={15} />
            刷新
          </button>
        </div>
      </div>
      {initialLoading && <PageLoadingState label="正在计算机会、来源质量和股票池" variant="strategy" />}
      {!initialLoading && (
        <>
      <div className="statbar metric-grid">
        <Metric label="机会候选" value={data?.opportunity_count ?? 0} detail="近 30 天派生信号" />
        <Metric label="重点关注" value={focusCount} detail="高分且可靠性足够" />
        <Metric label="风险升高" value={riskCount} detail="反证或风险词偏高" />
        <Metric label="更新时间" value={data ? formatTime(data.generated_at).slice(5, 16) : "-"} detail="本地只读聚合" />
      </div>
      {error && <p className="error-line">{error}</p>}
      <div className="strategy-grid">
        <section className="panel strategy-main-panel">
          <PanelTitle title="今日机会" meta="主题拐点 x 来源质量 x T+5 回测 x 催化/风险" />
          <div className="strategy-opportunity-list">
            {opportunities.length ? (
              opportunities.map((item) => <OpportunityCard item={item} key={item.key} />)
            ) : (
              <p className="empty-line">暂无机会信号。</p>
            )}
          </div>
        </section>
        <aside className="strategy-side-stack">
          <section className="panel">
            <PanelTitle title="来源质量" meta="T+5 超额 · 近 30 天" />
            <div className="strategy-compact-list">
              {(data?.source_quality ?? []).map((item) => (
                <SourceRow item={item} key={item.name} />
              ))}
            </div>
          </section>
          <section className="panel">
            <PanelTitle title="优质股票池" meta="回测事件聚合 · 非买入建议" />
            <div className="strategy-compact-list">
              {(data?.stock_candidates ?? []).map((item) => (
                <StockRow item={item} key={item.ts_code} />
              ))}
            </div>
          </section>
        </aside>
      </div>
        </>
      )}
    </section>
  );
}

function OpportunityCard({ item }: { item: StrategyOpportunity }) {
  const topStocks = item.related_stocks.slice(0, 4);
  const sources = item.top_sources.slice(0, 3);
  return (
    <article className="strategy-opportunity-card">
      <div className="strategy-opportunity-head">
        <div>
          <span className={levelClass(item.attention_level)}>{item.attention_level}</span>
          <h2>{item.name}</h2>
        </div>
        <div className="strategy-score">
          <strong>{item.score.toFixed(0)}</strong>
          <span>机会分</span>
        </div>
      </div>
      <p className="strategy-reason">{item.reason}</p>
      <div className="strategy-signal-grid">
        <Signal label="拐点" value={`${item.acceleration.toFixed(1)}x`} icon={<TrendingUp size={15} />} />
        <Signal label="广度" value={`${item.sender_count}人/${item.group_count}群`} icon={<Users size={15} />} />
        <Signal label="全量T+5" value={formatPercent(item.opportunity_backtest.average_excess_return_t5, true)} icon={<Gauge size={15} />} />
        <Signal label="风险" value={`${item.risk_count}条`} icon={<ShieldAlert size={15} />} />
      </div>
      <div className="strategy-backtest-strip">
        <BacktestMetric label="全量机会" metric={item.opportunity_backtest} />
        <BacktestMetric label="精选股票" metric={item.selected_stock_backtest} />
      </div>
      <div className="strategy-tag-row">
        {item.catalyst_terms.slice(0, 5).map((term) => (
          <span className="strategy-chip positive" key={term}>
            {term}
          </span>
        ))}
        {item.risk_terms.slice(0, 3).map((term) => (
          <span className="strategy-chip risk" key={term}>
            {term}
          </span>
        ))}
      </div>
      <p className="strategy-risk">{item.risk_summary}</p>
      {topStocks.length > 0 && (
        <div className="strategy-card-section">
          <span className="strategy-section-label">相关股票</span>
          <div className="strategy-stock-strip">
            {topStocks.map((stock) => (
              <article className="strategy-stock-pill" key={stock.ts_code}>
                <div>
                  <strong>{stock.stock_name}</strong>
                  {stock.lifecycle_state && (
                    <span className={`strategy-stock-state strategy-stock-state-${stock.lifecycle_state}`}>
                      {stock.lifecycle_state}
                    </span>
                  )}
                  {stock.lifecycle_state === "发酵中" && stock.price_position && (
                    <span className={`strategy-price-position strategy-price-position-${stock.price_position}`}>
                      {stock.price_position}
                    </span>
                  )}
                </div>
                <em>T+5 {formatPercent(stock.average_excess_return_t5, true)}</em>
                <small>
                  首现后 {formatPercent(stock.price_return_since_first_seen, true)}
                  {stock.signal_age_days !== undefined && stock.signal_age_days !== null ? ` · ${stock.signal_age_days}天` : ""}
                </small>
                {stock.lifecycle_reason && <small>{stock.lifecycle_reason}</small>}
              </article>
            ))}
          </div>
        </div>
      )}
      {sources.length > 0 && (
        <div className="strategy-card-section">
          <span className="strategy-section-label">主要来源</span>
          <div className="strategy-source-strip">
            {sources.map((source) => (
              <span key={source.name}>{source.name}</span>
            ))}
          </div>
        </div>
      )}
    </article>
  );
}

function BacktestMetric(props: { label: string; metric: StrategyOpportunity["opportunity_backtest"] }) {
  return (
    <div className="strategy-backtest-metric">
      <span>{props.label}</span>
      <strong>{formatPercent(props.metric.average_excess_return_t5, true)}</strong>
      <em>
        T+5 {formatPercent(props.metric.win_rate_t5)} · 成熟 {props.metric.matured_event_count}/{props.metric.event_count}
        {props.metric.pending_event_count > 0 ? ` · 待 ${props.metric.pending_event_count}` : ""}
      </em>
    </div>
  );
}

function Signal(props: { label: string; value: string; icon: ReactNode }) {
  return (
    <div className="strategy-signal">
      <span>
        {props.icon}
        {props.label}
      </span>
      <strong>{props.value}</strong>
    </div>
  );
}

function SourceRow({ item }: { item: StrategySourceSignal }) {
  return (
    <article className="strategy-compact-row">
      <strong>{item.name}</strong>
      <span>{item.event_count} 事件</span>
      <em>{formatPercent(item.average_excess_return_t5, true)}</em>
    </article>
  );
}

function StockRow({ item }: { item: StrategyStockCandidate }) {
  return (
    <article className="strategy-compact-row stock">
      <div className="strategy-compact-main">
        <strong>{item.stock_name}</strong>
        {item.lifecycle_state && (
          <span className={`strategy-stock-state strategy-stock-state-${item.lifecycle_state}`}>
            {item.lifecycle_state}
          </span>
        )}
        {item.lifecycle_state === "发酵中" && item.price_position && (
          <span className={`strategy-price-position strategy-price-position-${item.price_position}`}>
            {item.price_position}
          </span>
        )}
      </div>
      <span>
        {item.source_count} 来源 · {item.event_count} 事件 · 首现后 {formatPercent(item.price_return_since_first_seen, true)}
      </span>
      <em>T+5 {formatPercent(item.average_excess_return_t5, true)}</em>
      {item.lifecycle_reason && <small>{item.lifecycle_reason}</small>}
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

function levelClass(level: StrategyOpportunity["attention_level"]): string {
  return `strategy-level strategy-level-${level}`;
}

function formatPercent(value?: number | null, signed = false): string {
  if (value === undefined || value === null) {
    return "-";
  }
  const text = `${(value * 100).toFixed(1)}%`;
  return signed && value > 0 ? `+${text}` : text;
}
