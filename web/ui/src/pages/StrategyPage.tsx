import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";

import {
  fetchSourceRadarSnapshot,
  fetchSourceRadarValidation,
  fetchStrategyOpportunities,
  fetchStrategyValidation,
} from "../api/radarApi";
import { PageLoadingState, PageRefreshProgress } from "../components/PageLoadingState";
import { PanelTitle } from "../components/PanelTitle";
import { SourceRadarPanel } from "../components/SourceRadarPanel";
import {
  DecisionStockGroup,
  OpportunityCard,
  SourceRow,
  groupStocksByDecision,
} from "../components/StrategyFermentationCards";
import { StrategyStockDrawer, type StrategyStockDrawerStock } from "../components/StrategyStockDrawer";
import { StrategyValidationPanel } from "../components/StrategyValidationPanel";
import { formatTime } from "../lib/datetime";
import type {
  SourceRadarSnapshot,
  SourceRadarValidationSummary,
  StrategyDashboard,
  StrategyValidationSummary,
} from "../types";
type StrategyMode = "source" | "fermentation" | "validation";
type ValidationMode = "fermentation" | "source";

const SHOW_SOURCE_RADAR_ENTRY = false;
const SHOW_STRATEGY_VALIDATION_ENTRY = false;

export function StrategyPage() {
  const sourceAsOfReadyRef = useRef(false);
  const [activeMode, setActiveMode] = useState<StrategyMode>("fermentation");
  const [activeValidationMode, setActiveValidationMode] = useState<ValidationMode>("source");
  const [sourceAsOfTime, setSourceAsOfTime] = useState("");
  const [sourceRadar, setSourceRadar] = useState<SourceRadarSnapshot | null>(null);
  const [sourceValidation, setSourceValidation] = useState<SourceRadarValidationSummary | null>(null);
  const [data, setData] = useState<StrategyDashboard | null>(null);
  const [validation, setValidation] = useState<StrategyValidationSummary | null>(null);
  const [selectedStock, setSelectedStock] = useState<StrategyStockDrawerStock | null>(null);
  const [loading, setLoading] = useState(false);
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

  const opportunities = data?.opportunities ?? [];
  const focusCount = opportunities.filter((item) => item.attention_level === "重点关注").length;
  const riskCount = opportunities.filter((item) => item.attention_level === "风险升高").length;
  const stockGroups = groupStocksByDecision(data?.stock_candidates ?? []);
  const actionableStockGroup = stockGroups[0];
  const secondaryStockGroups = stockGroups.slice(1);
  const actionableStockCount = stockGroups[0].items.length;
  const activeDataLoaded =
    activeMode === "source"
      ? sourceRadar
      : activeMode === "validation"
        ? validation || sourceValidation
        : data;
  const initialLoading = loading && !activeDataLoaded;

  return (
    <section className="strategy-page">
      <div className="dashboard-actions">
        <p>{strategyHeaderText(activeMode, initialLoading, sourceRadar, data, validation)}</p>
        <div>
          {loading && !initialLoading && <PageRefreshProgress label="正在刷新策略" />}
          <button className="btn btn-sm" type="button" onClick={() => void refresh(activeMode)} disabled={loading}>
            <RefreshCw size={15} />
            刷新
          </button>
        </div>
      </div>
      <div className="strategy-mode-tabs" role="tablist" aria-label="策略模式">
        {SHOW_SOURCE_RADAR_ENTRY && <ModeTab active={activeMode === "source"} label="源头雷达" onClick={() => setActiveMode("source")} />}
        <ModeTab active={activeMode === "fermentation"} label="发酵确认" onClick={() => setActiveMode("fermentation")} />
        {SHOW_STRATEGY_VALIDATION_ENTRY && (
          <ModeTab active={activeMode === "validation"} label="策略验证" onClick={() => setActiveMode("validation")} />
        )}
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
          {error && <p className="error-line">{error}</p>}
          <div className="strategy-fermentation-stack">
            <section className="panel strategy-focus-stocks-panel">
              <PanelTitle title="今日可关注股票" meta="发酵中/初现，位置未过热 · 非买入建议" />
              <div className="strategy-stock-groups strategy-stock-groups-featured">
                <DecisionStockGroup group={actionableStockGroup} onStockOpen={setSelectedStock} />
              </div>
            </section>

            <section className="panel strategy-main-panel">
              <PanelTitle title="发酵主题" meta="主题拐点 x 来源质量 x T+5 回测 x 催化/风险" />
              <div className="strategy-opportunity-list">
                {opportunities.length ? (
                  opportunities.map((item) => <OpportunityCard item={item} key={item.key} onStockOpen={setSelectedStock} />)
                ) : (
                  <p className="empty-line">暂无发酵确认信号。</p>
                )}
              </div>
            </section>

            <div className="strategy-grid strategy-support-grid">
              <section className="panel">
                <PanelTitle title="来源质量" meta="T+5 超额 · 近 30 天" />
                <div className="strategy-compact-list">
                  {(data?.source_quality ?? []).map((item) => (
                    <SourceRow item={item} key={item.name} />
                  ))}
                </div>
              </section>
              <section className="panel">
                <PanelTitle title="观察与复盘股票" meta="等待确认 / 已兑现复盘" />
                <div className="strategy-stock-groups">
                  {secondaryStockGroups.map((group) => (
                    <DecisionStockGroup group={group} key={group.bucket} onStockOpen={setSelectedStock} />
                  ))}
                </div>
              </section>
            </div>
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
      <StrategyStockDrawer stock={selectedStock} onClose={() => setSelectedStock(null)} />
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

function Metric(props: { label: string; value: number | string; detail: string }) {
  return (
    <article className="stat metric-card">
      <p className="k">{props.label}</p>
      <strong className="v">{props.value}</strong>
      <span className="sub">{props.detail}</span>
    </article>
  );
}
