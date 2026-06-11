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
    source_count: item.sender_count,
    first_seen_time: firstEvidenceTime(item),
    latest_message_time: item.updated_at,
    price_return_since_first_seen: numberValue(item.market_summary.return_since_first_point),
    drawdown_from_high_since_first_seen: numberValue(item.market_summary.drawdown_from_selected_high),
    drawer_context: [
      { label: "首现", value: firstEvidenceTime(item) },
      { label: "最近", value: item.updated_at },
      { label: "发送人", value: item.sender_count },
      { label: "会话", value: item.conversation_count },
    ],
    drawer_metrics: [
      { label: "区间收益", value: numberValue(item.market_summary.return_since_first_point) },
      { label: "高点回撤", value: numberValue(item.market_summary.drawdown_from_selected_high) },
      { label: "5日强弱", value: numberValue(item.primary_theme?.stock_return_5d) },
      { label: "量能", value: volumeRatioText(item.primary_theme?.amount_ratio_5d) },
    ],
  };
}

function firstEvidenceTime(item: StockEvidenceChainItem): string | null {
  return item.evidence_chain[0]?.time ?? null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function volumeRatioText(value: unknown): string | null {
  const ratio = numberValue(value);
  return ratio === null ? null : `${ratio.toFixed(1)}x`;
}
