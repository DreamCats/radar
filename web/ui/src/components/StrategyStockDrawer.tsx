import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { fetchStockEvidenceStockChart } from "../api/radarApi";
import { ChatLauncher } from "./ChatLauncher";
import { StrategyStockCandlestickChart } from "./StrategyStockCandlestickChart";
import type { StockEvidenceStockChart } from "../types";

export type StrategyStockDrawerMetric = {
  label: string;
  value?: number | null;
};

export type StrategyStockDrawerStock = {
  stock_name: string;
  ts_code: string;
  event_count?: number;
  source_count?: number;
  first_seen_time?: string | null;
  latest_message_time?: string | null;
  price_return_since_first_seen?: number | null;
  recent_price_return_3d?: number | null;
  drawdown_from_high_since_first_seen?: number | null;
  average_excess_return_t5?: number | null;
  realtime_score?: number | null;
  drawer_badge?: string;
  drawer_metrics?: StrategyStockDrawerMetric[];
  evidence_title?: string;
  evidence_lines?: string[];
};

type StrategyStock = StrategyStockDrawerStock;

type Props = {
  stock: StrategyStock | null;
  onClose: () => void;
};

export function StrategyStockDrawer({ stock, onClose }: Props) {
  const [chart, setChart] = useState<StockEvidenceStockChart | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!stock) {
      setChart(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetchStockEvidenceStockChart(stock.ts_code, { days: 120 })
      .then((result) => {
        if (!cancelled) {
          setChart(result);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "行情加载失败");
          setChart(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [stock?.ts_code]);

  useEffect(() => {
    if (!stock) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [stock, onClose]);

  if (!stock) {
    return null;
  }

  const candles = chart?.candles ?? [];

  return (
    <div className="strategy-stock-drawer-shell" role="dialog" aria-modal="true" aria-label={`${stock.stock_name} K线`}>
      <button className="strategy-stock-drawer-scrim" type="button" aria-label="关闭K线抽屉" onClick={onClose} />
      <aside className="strategy-stock-drawer">
        <header className="strategy-stock-drawer-head">
          <div>
            <strong>{stock.stock_name}</strong>
            <span>{stock.ts_code}</span>
          </div>
          <button className="icon-btn" type="button" aria-label="关闭" onClick={onClose}>
            <X size={16} />
          </button>
        </header>

        <div className="strategy-stock-drawer-tags">
          {stock.drawer_badge && <span className="strategy-stock-context-tag">{stock.drawer_badge}</span>}
        </div>

        <div className="strategy-stock-drawer-body">
          {loading && <p className="strategy-stock-chart-empty">正在加载本地行情</p>}
          {!loading && error && <p className="error-line">{error}</p>}
          {!loading && !error && candles.length === 0 && (
            <p className="strategy-stock-chart-empty">{chart?.missing_reason ?? "本地暂无日线缓存"}</p>
          )}
          {!loading && !error && candles.length > 0 && (
            <StrategyStockCandlestickChart candles={candles} stock={stock} latestIsRealtime={chart?.latest_is_realtime ?? false} />
          )}

          <div className="strategy-stock-decision-grid">
            {drawerMetrics(stock).map((metric) => (
              <DecisionMetric label={metric.label} value={metric.value} key={metric.label} />
            ))}
          </div>

          <div className="strategy-stock-drawer-chat-row">
            <ChatLauncher
              title={stock.stock_name}
              subtitle={evidenceSummary(stock) || stock.ts_code}
              surface="个股深挖"
              entityId={stock.ts_code}
              buttonLabel="深挖这个标的"
              buttonClassName="btn btn-primary btn-sm chat-inline-action"
              context={[
                { label: "代码", value: stock.ts_code },
                { label: "阶段", value: stock.drawer_badge },
                { label: "首现", value: stock.first_seen_time },
                { label: "最近", value: stock.latest_message_time },
                { label: "样本", value: evidenceSummary(stock) },
              ]}
              evidence={stockEvidenceLines(stock)}
              suggestedQuestions={[
                "这个标的现在还能不能看？请结合消息证据、价格位置和风险。",
                "首提来源可靠吗？这条股票信号有没有过热或反证？",
                "如果不追高，后续应该盯哪些价格、消息和来源变化？",
              ]}
            />
          </div>

          <section className="strategy-stock-evidence-panel">
            <strong>{stock.evidence_title ?? "策略证据"}</strong>
            {evidenceSummary(stock) && <span>{evidenceSummary(stock)}</span>}
            {stock.evidence_lines?.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </section>
        </div>
      </aside>
    </div>
  );
}

function DecisionMetric({ label, value }: { label: string; value?: number | null }) {
  return (
    <article>
      <span>{label}</span>
      <strong className={returnToneClass(value)}>{formatPercent(value, true)}</strong>
    </article>
  );
}

function stockEvidenceLines(stock: StrategyStock): string[] {
  return stock.evidence_lines ?? [];
}

function drawerMetrics(stock: StrategyStock): StrategyStockDrawerMetric[] {
  return stock.drawer_metrics?.length
    ? stock.drawer_metrics
    : [
        { label: "首现以来", value: stock.price_return_since_first_seen },
        { label: "近3日", value: stock.recent_price_return_3d },
        { label: "首现回撤", value: stock.drawdown_from_high_since_first_seen },
        { label: "T+5超额", value: stock.average_excess_return_t5 },
      ];
}

function evidenceSummary(stock: StrategyStock): string {
  return [
    stock.source_count !== undefined ? `${stock.source_count} 来源` : "",
    stock.event_count !== undefined ? `${stock.event_count} 事件` : "",
    stock.realtime_score !== undefined && stock.realtime_score !== null ? `实时 ${stock.realtime_score.toFixed(0)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
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
