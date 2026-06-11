import { Suspense, lazy, useEffect, useState } from "react";
import { X } from "lucide-react";

import { fetchStockEvidenceStockChart } from "../api/radarApi";
import { ChatLauncher } from "./ChatLauncher";
import type { StockEvidenceStockChart } from "../types";

export type StrategyStockDrawerMetric = {
  label: string;
  value?: number | string | null;
  tone?: "up" | "down" | "flat";
};

export type StrategyStockDrawerContextItem = {
  label: string;
  value?: string | number | null;
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
  drawer_context?: StrategyStockDrawerContextItem[];
  evidence_title?: string;
  evidence_lines?: string[];
};

type StrategyStock = StrategyStockDrawerStock;

const StrategyStockCandlestickChart = lazy(() =>
  import("./StrategyStockCandlestickChart").then((module) => ({ default: module.StrategyStockCandlestickChart })),
);

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
  const evidenceLines = stockEvidenceLines(stock);

  return (
    <div className="strategy-stock-drawer-shell" role="dialog" aria-modal="true" aria-label={`${stock.stock_name} K线`}>
      <button className="strategy-stock-drawer-scrim" type="button" aria-label="关闭K线抽屉" onClick={onClose} />
      <aside className="strategy-stock-drawer">
        <header className="strategy-stock-drawer-head">
          <div className="strategy-stock-drawer-title">
            <strong>{stock.stock_name}</strong>
            <span>{stock.ts_code}</span>
          </div>
          <div className="strategy-stock-drawer-head-actions">
            <ChatLauncher
              title={stock.stock_name}
              subtitle={drawerSubtitle(stock) || stock.ts_code}
              surface="个股深挖"
              entityId={stock.ts_code}
              buttonLabel="AI"
              buttonClassName="btn btn-primary btn-sm strategy-stock-ai-action"
              context={[
                { label: "代码", value: stock.ts_code },
                { label: "视图", value: stock.drawer_badge ?? "K线复盘" },
                { label: "首现", value: stock.first_seen_time },
                { label: "最近", value: stock.latest_message_time },
                { label: "样本", value: drawerSubtitle(stock) },
              ]}
              evidence={evidenceLines}
              suggestedQuestions={[
                "只看这张K线，当前价格位置和量能有什么风险？",
                "从首现到最近消息，股价是提前反映、刚启动，还是已经兑现？",
                "后续应该盯哪些均线、成交量和回撤位置？",
              ]}
            />
            <button className="icon-btn" type="button" aria-label="关闭" onClick={onClose}>
              <X size={16} />
            </button>
          </div>
        </header>

        <div className="strategy-stock-drawer-tags">
          {stock.drawer_badge && <span className="strategy-stock-context-tag">{stock.drawer_badge}</span>}
          <span>行情面板</span>
        </div>

        <div className="strategy-stock-drawer-body">
          <div className="strategy-stock-context-grid">
            {drawerContext(stock).map((item) => (
              <article key={item.label}>
                <span>{item.label}</span>
                <strong>{formatContextValue(item.value)}</strong>
              </article>
            ))}
          </div>

          {loading && <MarketChartLoading stockName={stock.stock_name} />}
          {!loading && error && <p className="error-line">{error}</p>}
          {!loading && !error && candles.length === 0 && (
            <p className="strategy-stock-chart-empty">{chart?.missing_reason ?? "本地暂无日线缓存"}</p>
          )}
          {!loading && !error && candles.length > 0 && (
            <Suspense fallback={<p className="strategy-stock-chart-empty">正在加载图表</p>}>
              <StrategyStockCandlestickChart candles={candles} stock={stock} latestIsRealtime={chart?.latest_is_realtime ?? false} />
            </Suspense>
          )}

          <div className="strategy-stock-decision-grid">
            {drawerMetrics(stock).map((metric) => (
              <DecisionMetric label={metric.label} tone={metric.tone} value={metric.value} key={metric.label} />
            ))}
          </div>

          {evidenceLines.length > 0 && (
            <section className="strategy-stock-evidence-panel">
              <strong>{stock.evidence_title ?? "策略证据"}</strong>
              {drawerSubtitle(stock) && <span>{drawerSubtitle(stock)}</span>}
              {evidenceLines.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </section>
          )}
        </div>
      </aside>
    </div>
  );
}

function DecisionMetric({ label, value, tone }: StrategyStockDrawerMetric) {
  const formatted = formatMetricValue(value);
  return (
    <article>
      <span>{label}</span>
      <strong className={metricToneClass(value, tone)}>{formatted}</strong>
    </article>
  );
}

function MarketChartLoading({ stockName }: { stockName: string }) {
  const candleBars = [
    { className: "is-down", height: 46 },
    { className: "is-up", height: 72 },
    { className: "is-up", height: 58 },
    { className: "is-down", height: 88 },
    { className: "is-up", height: 104 },
    { className: "is-down", height: 64 },
    { className: "is-up", height: 92 },
    { className: "is-up", height: 76 },
    { className: "is-down", height: 52 },
  ];
  const volumeBars = [34, 58, 42, 76, 94, 62, 84, 48, 66];

  return (
    <section className="strategy-market-loading" role="status" aria-live="polite" aria-label={`正在同步${stockName}本地行情`}>
      <div className="strategy-market-loading-head">
        <span className="strategy-market-loading-dot" />
        <div>
          <strong>正在同步本地行情</strong>
          <span>读取日线缓存与盘中快照</span>
        </div>
      </div>
      <div className="strategy-market-loading-chart" aria-hidden="true">
        <div className="strategy-market-loading-grid" />
        <div className="strategy-market-loading-price-line" />
        <div className="strategy-market-loading-candles">
          {candleBars.map((bar, index) => (
            <span className={`strategy-market-loading-candle ${bar.className}`} style={{ height: `${bar.height}px` }} key={index} />
          ))}
        </div>
        <div className="strategy-market-loading-volumes">
          {volumeBars.map((height, index) => (
            <span style={{ height: `${height}%` }} key={index} />
          ))}
        </div>
      </div>
    </section>
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

function drawerContext(stock: StrategyStock): StrategyStockDrawerContextItem[] {
  if (stock.drawer_context?.length) {
    return stock.drawer_context;
  }
  return [
    { label: "首现", value: stock.first_seen_time },
    { label: "最近", value: stock.latest_message_time },
    { label: "事件", value: stock.event_count },
    { label: "来源", value: stock.source_count },
  ];
}

function drawerSubtitle(stock: StrategyStock): string {
  return [
    stock.source_count !== undefined ? `${stock.source_count} 来源` : "",
    stock.event_count !== undefined ? `${stock.event_count} 事件` : "",
    stock.realtime_score !== undefined && stock.realtime_score !== null ? `实时 ${stock.realtime_score.toFixed(0)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function formatContextValue(value?: string | number | null): string {
  if (value === undefined || value === null || value === "") {
    return "-";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(value) : "-";
  }
  return compactDateTime(value);
}

function compactDateTime(value: string): string {
  const match = value.match(/^(\d{4})[-/](\d{2})[-/](\d{2})(?:[T\s](\d{2}):(\d{2}))?/);
  if (!match) {
    return value;
  }
  const [, , month, day, hour, minute] = match;
  return hour && minute ? `${month}/${day} ${hour}:${minute}` : `${month}/${day}`;
}

function formatMetricValue(value?: number | string | null): string {
  if (typeof value === "string") {
    return value;
  }
  return formatPercent(value, true);
}

function formatPercent(value?: number | null, signed = false): string {
  if (value === undefined || value === null) {
    return "-";
  }
  const text = `${(value * 100).toFixed(1)}%`;
  return signed && value > 0 ? `+${text}` : text;
}

function metricToneClass(value?: number | string | null, tone?: StrategyStockDrawerMetric["tone"]): string {
  if (tone) {
    return tone === "up" ? "return-up" : tone === "down" ? "return-down" : "return-flat";
  }
  if (typeof value === "string") {
    return "return-flat";
  }
  if (value === undefined || value === null || value === 0) {
    return "return-flat";
  }
  return value > 0 ? "return-up" : "return-down";
}
