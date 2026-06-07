import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Gauge, RefreshCw, Save, ShieldAlert, TrendingUp, Users } from "lucide-react";

import {
  fetchSourceRadarSnapshot,
  fetchSourceRadarValidation,
  fetchStrategyOpportunities,
  fetchStrategyValidation,
  saveStrategySnapshot,
} from "../api/radarApi";
import { PageLoadingState, PageRefreshProgress } from "../components/PageLoadingState";
import { PanelTitle } from "../components/PanelTitle";
import { SourceRadarPanel } from "../components/SourceRadarPanel";
import { StrategyValidationPanel } from "../components/StrategyValidationPanel";
import { formatTime } from "../lib/datetime";
import type {
  SourceRadarSnapshot,
  SourceRadarValidationSummary,
  StrategyDashboard,
  StrategyOpportunity,
  StrategyRelatedStock,
  StrategySourceSignal,
  StrategyStockCandidate,
  StrategyValidationSummary,
} from "../types";
type StrategyMode = "source" | "fermentation" | "validation";
type ValidationMode = "fermentation" | "source";

export function StrategyPage() {
  const sourceAsOfReadyRef = useRef(false);
  const [activeMode, setActiveMode] = useState<StrategyMode>("source");
  const [activeValidationMode, setActiveValidationMode] = useState<ValidationMode>("source");
  const [sourceAsOfTime, setSourceAsOfTime] = useState("");
  const [sourceRadar, setSourceRadar] = useState<SourceRadarSnapshot | null>(null);
  const [sourceValidation, setSourceValidation] = useState<SourceRadarValidationSummary | null>(null);
  const [data, setData] = useState<StrategyDashboard | null>(null);
  const [validation, setValidation] = useState<StrategyValidationSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const [snapshotMessage, setSnapshotMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh(mode: StrategyMode = activeMode) {
    setLoading(true);
    setError(null);
    try {
      if (mode === "source") {
        setSourceRadar(await fetchSourceRadarSnapshot({ limit: 20, as_of_time: sourceAsOfTime || undefined }));
      } else if (mode === "validation") {
        const [strategyResult, sourceResult] = await Promise.all([
          fetchStrategyValidation({ window_days: 5, source_limit: 8 }),
          fetchSourceRadarValidation({ window_days: 5, limit: 12 }),
        ]);
        setValidation(strategyResult);
        setSourceValidation(sourceResult);
      } else {
        setData(await fetchStrategyOpportunities({ days: 30, recent_days: 7, limit: 12 }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (activeMode === "source" && !sourceRadar) {
      void refresh("source");
    } else if (activeMode === "fermentation" && !data) {
      void refresh("fermentation");
    } else if (activeMode === "validation" && (!validation || !sourceValidation)) {
      void refresh("validation");
    }
  }, [activeMode]);

  useEffect(() => {
    if (!sourceAsOfReadyRef.current) {
      sourceAsOfReadyRef.current = true;
      return;
    }
    if (activeMode === "source") {
      void refresh("source");
    }
  }, [sourceAsOfTime]);

  async function saveCurrentSnapshot() {
    setSavingSnapshot(true);
    setSnapshotMessage(null);
    setError(null);
    try {
      const result = await saveStrategySnapshot({ days: 30, recent_days: 7, limit: 12, force: false });
      setSnapshotMessage(result.reused_existing ? `已复用快照 ${result.snapshot_id.slice(0, 8)}` : `已保存快照 ${result.snapshot_id.slice(0, 8)}`);
      setValidation(await fetchStrategyValidation({ window_days: 5, source_limit: 8 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存快照失败");
    } finally {
      setSavingSnapshot(false);
    }
  }

  const opportunities = data?.opportunities ?? [];
  const focusCount = opportunities.filter((item) => item.attention_level === "重点关注").length;
  const riskCount = opportunities.filter((item) => item.attention_level === "风险升高").length;
  const stockGroups = groupStocksByDecision(data?.stock_candidates ?? []);
  const actionableStockCount = stockGroups[0].items.length;
  const activeDataLoaded = activeMode === "source" ? sourceRadar : activeMode === "validation" ? validation || sourceValidation : data;
  const initialLoading = loading && !activeDataLoaded;

  return (
    <section className="strategy-page">
      <div className="dashboard-actions">
        <p>{strategyHeaderText(activeMode, initialLoading, sourceRadar, data, validation)}</p>
        <div>
          {loading && !initialLoading && <PageRefreshProgress label="正在刷新策略" />}
          {activeMode === "fermentation" && (
            <button className="btn btn-sm" type="button" onClick={() => void saveCurrentSnapshot()} disabled={savingSnapshot || loading}>
              <Save size={15} />
              {savingSnapshot ? "保存中" : "保存当前快照"}
            </button>
          )}
          <button className="btn btn-sm" type="button" onClick={() => void refresh(activeMode)} disabled={loading}>
            <RefreshCw size={15} />
            刷新
          </button>
        </div>
      </div>
      <div className="strategy-mode-tabs" role="tablist" aria-label="策略模式">
        <ModeTab active={activeMode === "source"} label="源头雷达" onClick={() => setActiveMode("source")} />
        <ModeTab active={activeMode === "fermentation"} label="发酵确认" onClick={() => setActiveMode("fermentation")} />
        <ModeTab active={activeMode === "validation"} label="策略验证" onClick={() => setActiveMode("validation")} />
      </div>
      {initialLoading && <PageLoadingState label={loadingLabel(activeMode)} variant="strategy" />}
      {!initialLoading && activeMode === "source" && (
        <>
          {error && <p className="error-line">{error}</p>}
          <SourceRadarPanel snapshot={sourceRadar} selectedAsOfTime={sourceAsOfTime} onAsOfTimeChange={setSourceAsOfTime} />
        </>
      )}
      {!initialLoading && activeMode === "fermentation" && (
        <>
      <div className="statbar metric-grid">
        <Metric label="机会候选" value={data?.opportunity_count ?? 0} detail="近 30 天派生信号" />
        <Metric label="重点关注" value={focusCount} detail="高分且可靠性足够" />
        <Metric label="今日可看" value={actionableStockCount} detail="未过热的股票信号" />
        <Metric label="风险升高" value={riskCount} detail="反证或风险词偏高" />
      </div>
      {snapshotMessage && <p className="success-line">{snapshotMessage}</p>}
      {error && <p className="error-line">{error}</p>}
      <div className="strategy-grid">
        <section className="panel strategy-main-panel">
          <PanelTitle title="发酵确认" meta="主题拐点 x 来源质量 x T+5 回测 x 催化/风险" />
          <div className="strategy-opportunity-list">
            {opportunities.length ? (
              opportunities.map((item) => <OpportunityCard item={item} key={item.key} />)
            ) : (
              <p className="empty-line">暂无发酵确认信号。</p>
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
            <PanelTitle title="决策股票池" meta="按可操作性分层 · 非买入建议" />
            <div className="strategy-stock-groups">
              {stockGroups.map((group) => (
                <DecisionStockGroup group={group} key={group.bucket} />
              ))}
            </div>
          </section>
        </aside>
      </div>
        </>
      )}
      {!initialLoading && activeMode === "validation" && (
        <>
          {error && <p className="error-line">{error}</p>}
          <StrategyValidationPanel
            summary={validation}
            sourceSummary={sourceValidation}
            activeMode={activeValidationMode}
            onModeChange={setActiveValidationMode}
          />
        </>
      )}
    </section>
  );
}

function ModeTab(props: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button className={props.active ? "active" : ""} type="button" role="tab" aria-selected={props.active} onClick={props.onClick}>
      {props.label}
    </button>
  );
}

function strategyHeaderText(
  mode: StrategyMode,
  loading: boolean,
  sourceRadar: SourceRadarSnapshot | null,
  data: StrategyDashboard | null,
  validation: StrategyValidationSummary | null,
): string {
  if (loading) {
    return loadingLabel(mode);
  }
  if (mode === "source") {
    return sourceRadar?.as_of_time ? `源头快照 ${formatTime(sourceRadar.as_of_time)} · 早期概念雷达` : "暂无源头雷达快照";
  }
  if (mode === "validation") {
    return validation ? `策略验证工作台 · T+${validation.window_days} · 发酵确认 ${validation.matured_stock_count} 个成熟样本` : "暂无策略验证数据";
  }
  return data ? `策略信号窗口 ${formatTime(data.start_time)} - ${formatTime(data.end_time)}` : "暂无策略信号数据";
}

function loadingLabel(mode: StrategyMode): string {
  if (mode === "source") {
    return "正在加载源头雷达快照";
  }
  if (mode === "validation") {
    return "正在加载策略验证";
  }
  return "正在加载策略信号";
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
                  <span className={decisionClass(stock.decision_bucket)}>{stock.decision_bucket}</span>
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
                  {stock.event_credibility && (
                    <span className={credibilityClass(stock.event_credibility.level)}>
                      {stock.event_credibility.level}
                    </span>
                  )}
                </div>
                <em>实时 {stock.realtime_score.toFixed(0)} · T+5 {formatPercent(stock.average_excess_return_t5, true)}</em>
                <small>
                  首现后 {formatPercent(stock.price_return_since_first_seen, true)}
                  {stock.signal_age_days !== undefined && stock.signal_age_days !== null ? ` · ${stock.signal_age_days}天` : ""}
                </small>
                {stock.event_credibility?.first_source_name && (
                  <small>
                    首提 {stock.event_credibility.first_source_name}
                    {stock.event_credibility.risks[0] ? ` · ${stock.event_credibility.risks[0]}` : ""}
                  </small>
                )}
                {stock.decision_reason && <small>{stock.decision_reason}</small>}
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
        <span className={decisionClass(item.decision_bucket)}>{item.decision_bucket}</span>
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
        {item.event_credibility && (
          <span className={credibilityClass(item.event_credibility.level)}>{item.event_credibility.level}</span>
        )}
      </div>
      <span>
        实时 {item.realtime_score.toFixed(0)} · {item.source_count} 来源 · {item.event_count} 事件
      </span>
      <em>T+5 {formatPercent(item.average_excess_return_t5, true)}</em>
      {item.event_credibility?.first_source_name && (
        <small>
          首提 {item.event_credibility.first_source_name}
          {item.event_credibility.reasons[0] ? ` · ${item.event_credibility.reasons[0]}` : ""}
        </small>
      )}
      {item.decision_reason && <small>{item.decision_reason}</small>}
      {item.lifecycle_reason && <small>{item.lifecycle_reason}</small>}
    </article>
  );
}

type StockDecisionGroup = {
  bucket: StrategyStockCandidate["decision_bucket"];
  meta: string;
  items: StrategyStockCandidate[];
};

function DecisionStockGroup({ group }: { group: StockDecisionGroup }) {
  return (
    <section className="strategy-stock-group">
      <div className="strategy-stock-group-head">
        <strong>{group.bucket}</strong>
        <span>
          {group.items.length} 个 · {group.meta}
        </span>
      </div>
      {group.items.length ? (
        <div className="strategy-compact-list">
          {group.items.map((item) => (
            <StockRow item={item} key={item.ts_code} />
          ))}
        </div>
      ) : (
        <p className="strategy-stock-group-empty">暂无</p>
      )}
    </section>
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

function credibilityClass(level: NonNullable<StrategyRelatedStock["event_credibility"]>["level"]): string {
  return `strategy-credibility strategy-credibility-${level}`;
}

function decisionClass(bucket: StrategyRelatedStock["decision_bucket"]): string {
  return `strategy-decision strategy-decision-${bucket}`;
}

function groupStocksByDecision(stocks: StrategyStockCandidate[]): StockDecisionGroup[] {
  return [
    {
      bucket: "今日可关注",
      meta: "发酵中/初现，位置未过热",
      items: stocks.filter((item) => item.decision_bucket === "今日可关注"),
    },
    {
      bucket: "观察等待",
      meta: "逻辑或价格还需确认",
      items: stocks.filter((item) => item.decision_bucket === "观察等待"),
    },
    {
      bucket: "已兑现复盘",
      meta: "不追高，用来验证来源",
      items: stocks.filter((item) => item.decision_bucket === "已兑现复盘"),
    },
  ];
}

function formatPercent(value?: number | null, signed = false): string {
  if (value === undefined || value === null) {
    return "-";
  }
  const text = `${(value * 100).toFixed(1)}%`;
  return signed && value > 0 ? `+${text}` : text;
}
