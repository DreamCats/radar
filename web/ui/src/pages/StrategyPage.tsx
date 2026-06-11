import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { fetchStockEvidenceChainLatest } from "../api/radarApi";
import { PageLoadingState, PageRefreshProgress } from "../components/PageLoadingState";
import { StockEvidenceChainPanel } from "../components/StockEvidenceChainPanel";
import { StrategyStockDrawer, type StrategyStockDrawerStock } from "../components/StrategyStockDrawer";
import { formatTime } from "../lib/datetime";
import type { StockEvidenceChainDashboard, StockEvidenceChainItem } from "../types";

export function StrategyPage() {
  const [data, setData] = useState<StockEvidenceChainDashboard | null>(null);
  const [selectedStock, setSelectedStock] = useState<StrategyStockDrawerStock | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchStockEvidenceChainLatest({ limit: 120 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const initialLoading = loading && !data;

  return (
    <section className="strategy-page">
      <div className="dashboard-actions">
        <p>{strategyHeaderText(initialLoading, data)}</p>
        <div>
          {loading && !initialLoading && <PageRefreshProgress label="正在刷新策略" />}
          <button className="btn btn-sm" type="button" onClick={() => void refresh()} disabled={loading}>
            <RefreshCw size={15} />
            刷新
          </button>
        </div>
      </div>
      <div className="strategy-mode-tabs" role="tablist" aria-label="策略模式">
        <button className="active" type="button" role="tab" aria-selected="true">
          个股证据链
        </button>
      </div>
      {initialLoading ? (
        <PageLoadingState label="正在加载个股证据链" variant="strategy" />
      ) : (
        <StockEvidenceChainPanel data={data} error={error} onSelectStock={(stock) => setSelectedStock(drawerStock(stock))} />
      )}
      <StrategyStockDrawer stock={selectedStock} onClose={() => setSelectedStock(null)} />
    </section>
  );
}

function strategyHeaderText(loading: boolean, data: StockEvidenceChainDashboard | null): string {
  if (loading) {
    return "正在加载个股证据链";
  }
  if (!data?.as_of_time) {
    return "暂无个股证据链判断";
  }
  return `个股证据链 ${formatTime(data.as_of_time)} · ${data.item_count} 个候选`;
}

function drawerStock(item: StockEvidenceChainItem): StrategyStockDrawerStock {
  return {
    stock_name: item.stock_name,
    ts_code: item.ts_code,
    event_count: item.trigger_count,
    source_count: item.conversation_count,
    latest_message_time: item.updated_at,
    price_return_since_first_seen: numberValue(item.market_summary.return_since_first_point),
    drawdown_from_high_since_first_seen: numberValue(item.market_summary.drawdown_from_selected_high),
    drawer_badge: item.stage_label,
    drawer_metrics: [
      { label: "区间收益", value: numberValue(item.market_summary.return_since_first_point) },
      { label: "高点回撤", value: numberValue(item.market_summary.drawdown_from_selected_high) },
      { label: "置信度", value: item.confidence },
    ],
    evidence_title: "证据链判断",
    evidence_lines: [
      item.summary,
      item.primary_theme ? `主题位置：${item.primary_theme.theme_name} / ${item.primary_theme.role}` : "主题位置：未确认",
      `市场认可：${item.recognition.state_label}`,
      item.lifecycle_digest ? `生命周期：${item.lifecycle_digest.one_line}` : "",
      ...(item.lifecycle_digest?.stage_reason ?? []).map((line) => `生命周期依据：${line}`),
      ...(item.lifecycle_digest?.missing_evidence ?? []).map((line) => `生命周期缺口：${line}`),
      ...item.recognition.reasons,
      ...item.recognition.missing_evidence.map((line) => `缺口：${line}`),
      ...item.why,
      item.pricing_risk ? `定价风险：${item.pricing_risk}` : "",
      item.crowding_risk ? `拥挤风险：${item.crowding_risk}` : "",
      ...item.evidence_chain.slice(0, 5).map((point) => `${point.time ?? "-"} ${point.type ?? "证据"}：${point.evidence ?? ""}`),
    ].filter((line) => line),
  };
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
