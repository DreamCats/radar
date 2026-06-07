import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";

import { fetchStrategyStockChart } from "../api/radarApi";
import type { StrategyRelatedStock, StrategyStockCandidate, StrategyStockChart, StrategyStockCandle } from "../types";

type StrategyStock = StrategyRelatedStock | StrategyStockCandidate;

type Props = {
  stock: StrategyStock | null;
  onClose: () => void;
};

export function StrategyStockDrawer({ stock, onClose }: Props) {
  const [chart, setChart] = useState<StrategyStockChart | null>(null);
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
    void fetchStrategyStockChart(stock.ts_code, { days: 120 })
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
          <span className={decisionClass(stock.decision_bucket)}>{stock.decision_bucket}</span>
          {stock.lifecycle_state && <span className={`strategy-stock-state strategy-stock-state-${stock.lifecycle_state}`}>{stock.lifecycle_state}</span>}
          {stock.price_position && <span className={`strategy-price-position strategy-price-position-${stock.price_position}`}>{stock.price_position}</span>}
          {stock.event_credibility && <span className={credibilityClass(stock.event_credibility.level)}>{stock.event_credibility.level}</span>}
        </div>

        <div className="strategy-stock-drawer-body">
          {loading && <p className="strategy-stock-chart-empty">正在加载本地行情</p>}
          {!loading && error && <p className="error-line">{error}</p>}
          {!loading && !error && candles.length === 0 && (
            <p className="strategy-stock-chart-empty">{chart?.missing_reason ?? "本地暂无日线缓存"}</p>
          )}
          {!loading && !error && candles.length > 0 && <CandlestickChart candles={candles} stock={stock} />}

          <div className="strategy-stock-decision-grid">
            <DecisionMetric label="首现以来" value={stock.price_return_since_first_seen} />
            <DecisionMetric label="近3日" value={stock.recent_price_return_3d} />
            <DecisionMetric label="首现回撤" value={stock.drawdown_from_high_since_first_seen} />
            <DecisionMetric label="T+5超额" value={stock.average_excess_return_t5} />
          </div>

          <section className="strategy-stock-evidence-panel">
            <strong>策略证据</strong>
            <span>
              {stock.source_count} 来源 · {stock.event_count} 事件 · 实时 {stock.realtime_score.toFixed(0)}
            </span>
            {stock.event_credibility?.first_source_name && (
              <p>
                首提 {stock.event_credibility.first_source_name}
                {stock.event_credibility.first_group_name ? ` · ${stock.event_credibility.first_group_name}` : ""}
              </p>
            )}
            {stock.decision_reason && <p>{stock.decision_reason}</p>}
            {stock.lifecycle_reason && <p>{stock.lifecycle_reason}</p>}
            {stock.event_credibility?.risks.slice(0, 2).map((risk) => (
              <p key={risk}>{risk}</p>
            ))}
          </section>
        </div>
      </aside>
    </div>
  );
}

function CandlestickChart({ candles, stock }: { candles: StrategyStockCandle[]; stock: StrategyStock }) {
  const chart = useMemo(() => buildChart(candles), [candles]);
  const markers = useMemo(() => signalMarkers(candles, stock), [candles, stock]);

  return (
    <section className="strategy-stock-chart-panel">
      <div className="strategy-stock-chart-title">
        <strong>日K · 120交易日</strong>
        <span>MA5 / MA10 / MA20 · 成交量</span>
      </div>
      <svg className="strategy-stock-chart" viewBox={`0 0 ${chart.width} ${chart.height}`} role="img" aria-label={`${stock.stock_name} 日K`}>
        {chart.grid.map((line) => (
          <line className="strategy-chart-grid" key={line.y} x1={chart.left} x2={chart.right} y1={line.y} y2={line.y} />
        ))}
        {chart.grid.map((line) => (
          <text className="strategy-chart-axis" key={`label-${line.y}`} x={chart.left - 8} y={line.y + 4} textAnchor="end">
            {line.label}
          </text>
        ))}
        {chart.candles.map((item) => (
          <g key={item.candle.trade_date}>
            <line
              className={item.up ? "strategy-candle-up" : "strategy-candle-down"}
              x1={item.x}
              x2={item.x}
              y1={item.highY}
              y2={item.lowY}
            />
            <rect
              className={item.up ? "strategy-candle-up" : "strategy-candle-down"}
              x={item.x - chart.candleWidth / 2}
              y={item.bodyY}
              width={chart.candleWidth}
              height={item.bodyHeight}
              rx={1}
            >
              <title>
                {formatTradeDate(item.candle.trade_date)} 开 {item.candle.open.toFixed(2)} 高 {item.candle.high.toFixed(2)} 低{" "}
                {item.candle.low.toFixed(2)} 收 {item.candle.close.toFixed(2)}
              </title>
            </rect>
            <rect
              className={item.up ? "strategy-volume-up" : "strategy-volume-down"}
              x={item.x - chart.candleWidth / 2}
              y={item.volumeY}
              width={chart.candleWidth}
              height={item.volumeHeight}
              rx={1}
            />
          </g>
        ))}
        {chart.maLines.map((line) => (
          <polyline className={`strategy-ma-line strategy-ma-line-${line.period}`} key={line.period} points={line.points} />
        ))}
        {markers.map((marker, index) => {
          const x = chart.xForIndex(marker.index);
          return (
            <g key={marker.label}>
              <line className="strategy-signal-marker-line" x1={x} x2={x} y1={chart.top} y2={chart.volumeBottom} />
              <text className="strategy-signal-marker-label" x={x + 4} y={chart.top + 14 + index * 16}>
                {marker.label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="strategy-stock-chart-foot">
        <span>{formatTradeDate(candles[0].trade_date)}</span>
        <span>{formatTradeDate(candles[candles.length - 1].trade_date)}</span>
      </div>
    </section>
  );
}

function buildChart(candles: StrategyStockCandle[]) {
  const width = 760;
  const height = 360;
  const left = 56;
  const right = width - 18;
  const top = 18;
  const priceBottom = 255;
  const volumeTop = 284;
  const volumeBottom = 338;
  const high = Math.max(...candles.map((item) => item.high));
  const low = Math.min(...candles.map((item) => item.low));
  const pad = Math.max((high - low) * 0.08, high * 0.005, 0.01);
  const maxPrice = high + pad;
  const minPrice = low - pad;
  const priceSpan = Math.max(maxPrice - minPrice, 0.01);
  const maxVol = Math.max(...candles.map((item) => item.vol ?? 0), 1);
  const step = candles.length > 1 ? (right - left) / (candles.length - 1) : 0;
  const candleWidth = Math.max(2, Math.min(8, (right - left) / Math.max(candles.length, 1) * 0.6));
  const yForPrice = (price: number) => priceBottom - ((price - minPrice) / priceSpan) * (priceBottom - top);
  const xForIndex = (index: number) => left + step * index;
  const renderedCandles = candles.map((candle, index) => {
    const openY = yForPrice(candle.open);
    const closeY = yForPrice(candle.close);
    const volumeHeight = ((candle.vol ?? 0) / maxVol) * (volumeBottom - volumeTop);
    return {
      candle,
      x: xForIndex(index),
      up: candle.close >= candle.open,
      highY: yForPrice(candle.high),
      lowY: yForPrice(candle.low),
      bodyY: Math.min(openY, closeY),
      bodyHeight: Math.max(Math.abs(closeY - openY), 1),
      volumeY: volumeBottom - volumeHeight,
      volumeHeight,
    };
  });
  const grid = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const price = maxPrice - ratio * priceSpan;
    return {
      y: top + ratio * (priceBottom - top),
      label: price.toFixed(2),
    };
  });
  return {
    width,
    height,
    left,
    right,
    top,
    volumeBottom,
    candleWidth,
    candles: renderedCandles,
    grid,
    xForIndex,
    maLines: [5, 10, 20].map((period) => ({ period, points: maPoints(candles, period, xForIndex, yForPrice) })),
  };
}

function maPoints(
  candles: StrategyStockCandle[],
  period: number,
  xForIndex: (index: number) => number,
  yForPrice: (price: number) => number,
): string {
  const points: string[] = [];
  candles.forEach((_, index) => {
    if (index + 1 < period) {
      return;
    }
    const slice = candles.slice(index + 1 - period, index + 1);
    const average = slice.reduce((sum, item) => sum + item.close, 0) / period;
    points.push(`${xForIndex(index).toFixed(1)},${yForPrice(average).toFixed(1)}`);
  });
  return points.join(" ");
}

function signalMarkers(candles: StrategyStockCandle[], stock: StrategyStock) {
  const markers: Array<{ label: string; index: number }> = [];
  const firstSeen = dateKey(stock.first_seen_time);
  const latest = dateKey(stock.latest_message_time);
  if (firstSeen) {
    markers.push({ label: "首现", index: nearestCandleIndex(candles, firstSeen) });
  }
  if (latest && latest !== firstSeen) {
    markers.push({ label: "最近消息", index: nearestCandleIndex(candles, latest) });
  }
  return markers;
}

function nearestCandleIndex(candles: StrategyStockCandle[], key: string): number {
  const index = candles.findIndex((item) => item.trade_date >= key);
  return index >= 0 ? index : candles.length - 1;
}

function DecisionMetric({ label, value }: { label: string; value?: number | null }) {
  return (
    <article>
      <span>{label}</span>
      <strong className={returnToneClass(value)}>{formatPercent(value, true)}</strong>
    </article>
  );
}

function dateKey(value?: string | null): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}${month}${day}`;
}

function formatTradeDate(value: string): string {
  if (value.length !== 8) {
    return value;
  }
  return `${value.slice(4, 6)}/${value.slice(6, 8)}`;
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

function decisionClass(bucket: StrategyStock["decision_bucket"]): string {
  return `strategy-decision strategy-decision-${bucket}`;
}

function credibilityClass(level: NonNullable<StrategyStock["event_credibility"]>["level"]): string {
  return `strategy-credibility strategy-credibility-${level}`;
}
