import { useMemo } from "react";
import type { StrategyStockCandle } from "../types";
type ChartStock = {
  stock_name: string;
  first_seen_time?: string | null;
  latest_message_time?: string | null;
};
export function StrategyStockCandlestickChart({ candles, stock }: { candles: StrategyStockCandle[]; stock: ChartStock }) {
  const chart = useMemo(() => buildChart(candles), [candles]);
  const markers = useMemo(() => signalMarkers(candles, stock), [candles, stock]);
  const quote = useMemo(() => quoteSummary(candles), [candles]);

  return (
    <section className="strategy-stock-chart-panel">
      <div className="strategy-stock-quote-strip">
        <div className="strategy-stock-last-price">
          <strong className={quote.toneClass}>{quote.close}</strong>
          <span className="strategy-stock-change-row">
            <em>较昨收</em>
            <b className={quote.toneClass}>{quote.change} {quote.pct}</b>
          </span>
        </div>
        <dl className="strategy-stock-quote-grid">
          <QuoteItem label="高" value={quote.high} toneClass={quote.highTone} />
          <QuoteItem label="低" value={quote.low} toneClass={quote.lowTone} />
          <QuoteItem label="开" value={quote.open} toneClass={quote.openTone} />
          <QuoteItem label="昨收" value={quote.preClose} />
          <QuoteItem label="成交额" value={quote.amount} />
          <QuoteItem label="成交量" value={quote.volume} />
          <QuoteItem label="日内" value={quote.intraday} toneClass={quote.intradayTone} />
          <QuoteItem label="日期" value={quote.date} />
        </dl>
      </div>

      <div className="strategy-stock-chart-title">
        <strong>日K · {candles.length}交易日</strong>
        <span className="strategy-ma-legend">
          <em className="ma5">MA5:{formatPrice(chart.maLatest[5])}</em>
          <em className="ma10">10:{formatPrice(chart.maLatest[10])}</em>
          <em className="ma20">20:{formatPrice(chart.maLatest[20])}</em>
          <em>成交量</em>
        </span>
      </div>

      <svg className="strategy-stock-chart" viewBox={`0 0 ${chart.width} ${chart.height}`} role="img" aria-label={`${stock.stock_name} 日K`}>
        {chart.grid.map((line) => (
          <g key={line.y}>
            <line className="strategy-chart-grid" x1={chart.left} x2={chart.right} y1={line.y} y2={line.y} />
            <text className="strategy-chart-axis" x={chart.left - 8} y={line.y + 4} textAnchor="end">
              {line.label}
            </text>
          </g>
        ))}

        <line className="strategy-current-price-line" x1={chart.left} x2={chart.right} y1={chart.currentPriceY} y2={chart.currentPriceY} />
        <rect className={`strategy-current-price-pill ${quote.priceClass}`} x={chart.right - 52} y={chart.currentPriceY - 10} width="50" height="18" rx="4" />
        <text className="strategy-current-price-text" x={chart.right - 27} y={chart.currentPriceY + 4} textAnchor="middle">
          {quote.close}
        </text>

        {chart.candles.map((item) => (
          <g key={item.candle.trade_date}>
            <line
              className={item.up ? "strategy-candle-wick strategy-candle-up" : "strategy-candle-wick strategy-candle-down"}
              x1={item.x}
              x2={item.x}
              y1={item.highY}
              y2={item.lowY}
            />
            <rect
              className={item.up ? "strategy-candle-body strategy-candle-up" : "strategy-candle-body strategy-candle-down"}
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
        {chart.volumeMaLines.map((line) => (
          <polyline className={`strategy-volume-ma-line strategy-volume-ma-line-${line.period}`} key={`vol-${line.period}`} points={line.points} />
        ))}

        {markers.map((marker, index) => {
          const x = chart.xForIndex(marker.index);
          const isRightEdge = x > chart.right - 118;
          const labelX = isRightEdge ? x - 6 : x + 6;
          return (
            <g key={marker.label}>
              <line className="strategy-signal-marker-line" x1={x} x2={x} y1={chart.top} y2={chart.volumeBottom} />
              <text
                className="strategy-signal-marker-label"
                x={labelX}
                y={chart.top + 14 + index * 18}
                textAnchor={isRightEdge ? "end" : "start"}
              >
                {marker.label}
              </text>
            </g>
          );
        })}

        {chart.dateTicks.map((tick) => (
          <text className="strategy-chart-axis" key={tick.label} x={tick.x} y={chart.height - 10} textAnchor={tick.anchor}>
            {tick.label}
          </text>
        ))}
      </svg>
    </section>
  );
}

function QuoteItem({ label, value, toneClass }: { label: string; value: string; toneClass?: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={toneClass}>{value}</dd>
    </div>
  );
}

function buildChart(candles: StrategyStockCandle[]) {
  const width = 860;
  const height = 438;
  const left = 58;
  const right = width - 22;
  const top = 18;
  const priceBottom = 286;
  const volumeTop = 328;
  const volumeBottom = 404;
  const high = Math.max(...candles.map((item) => item.high));
  const low = Math.min(...candles.map((item) => item.low));
  const pad = Math.max((high - low) * 0.1, high * 0.006, 0.01);
  const maxPrice = high + pad;
  const minPrice = low - pad;
  const priceSpan = Math.max(maxPrice - minPrice, 0.01);
  const maxVol = Math.max(...candles.map((item) => item.vol ?? 0), 1);
  const step = candles.length > 1 ? (right - left) / (candles.length - 1) : 0;
  const candleWidth = Math.max(3, Math.min(10, ((right - left) / Math.max(candles.length, 1)) * 0.62));
  const yForPrice = (price: number) => priceBottom - ((price - minPrice) / priceSpan) * (priceBottom - top);
  const yForVolume = (volume: number) => volumeBottom - (volume / maxVol) * (volumeBottom - volumeTop);
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
      bodyHeight: Math.max(Math.abs(closeY - openY), 1.4),
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
  const maLines = [5, 10, 20].map((period) => ({ period, points: maPoints(candles, period, xForIndex, yForPrice) }));
  const volumeMaLines = [5, 10].map((period) => ({ period, points: volumeMaPoints(candles, period, xForIndex, yForVolume) }));
  const last = candles[candles.length - 1];
  return {
    width,
    height,
    left,
    right,
    top,
    volumeBottom,
    candleWidth,
    candles: renderedCandles,
    currentPriceY: yForPrice(last.close),
    dateTicks: dateTicks(candles, xForIndex),
    grid,
    xForIndex,
    maLatest: {
      5: maLatest(candles, 5),
      10: maLatest(candles, 10),
      20: maLatest(candles, 20),
    },
    maLines,
    volumeMaLines,
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
    const average = maAt(candles, period, index);
    if (average === null) {
      return;
    }
    points.push(`${xForIndex(index).toFixed(1)},${yForPrice(average).toFixed(1)}`);
  });
  return points.join(" ");
}

function volumeMaPoints(
  candles: StrategyStockCandle[],
  period: number,
  xForIndex: (index: number) => number,
  yForVolume: (volume: number) => number,
): string {
  const points: string[] = [];
  candles.forEach((_, index) => {
    if (index + 1 < period) {
      return;
    }
    const slice = candles.slice(index + 1 - period, index + 1);
    const average = slice.reduce((sum, item) => sum + (item.vol ?? 0), 0) / period;
    points.push(`${xForIndex(index).toFixed(1)},${yForVolume(average).toFixed(1)}`);
  });
  return points.join(" ");
}

function maLatest(candles: StrategyStockCandle[], period: number): number | null {
  return maAt(candles, period, candles.length - 1);
}

function maAt(candles: StrategyStockCandle[], period: number, index: number): number | null {
  if (index + 1 < period) {
    return null;
  }
  const slice = candles.slice(index + 1 - period, index + 1);
  return slice.reduce((sum, item) => sum + item.close, 0) / period;
}

function signalMarkers(candles: StrategyStockCandle[], stock: ChartStock) {
  const markers: Array<{ label: string; index: number }> = [];
  const firstSeen = dateKey(stock.first_seen_time);
  const latest = dateKey(stock.latest_message_time);
  if (firstSeen) {
    const label = markerLabel("首现", stock.first_seen_time);
    markers.push({ label, index: nearestCandleIndex(candles, firstSeen) });
  }
  if (latest && latest !== firstSeen) {
    const label = markerLabel("最近", stock.latest_message_time);
    markers.push({ label, index: nearestCandleIndex(candles, latest) });
  }
  return markers;
}

function nearestCandleIndex(candles: StrategyStockCandle[], key: string): number {
  const index = candles.findIndex((item) => item.trade_date >= key);
  return index >= 0 ? index : candles.length - 1;
}

function quoteSummary(candles: StrategyStockCandle[]) {
  const last = candles[candles.length - 1];
  const change = last.change ?? (last.pre_close ? last.close - last.pre_close : last.close - last.open);
  const pct = last.pct_chg ?? (last.pre_close ? (change / last.pre_close) * 100 : null);
  const intradayChange = last.close - last.open;
  const intradayPct = last.open ? (intradayChange / last.open) * 100 : null;
  const toneClass = priceToneClass(change);
  return {
    amount: formatAmount(last.amount),
    change: formatSignedPrice(change),
    close: last.close.toFixed(2),
    date: formatTradeDate(last.trade_date),
    high: last.high.toFixed(2),
    highTone: priceToneClass(last.high - (last.pre_close ?? last.open)),
    low: last.low.toFixed(2),
    lowTone: priceToneClass(last.low - (last.pre_close ?? last.open)),
    open: last.open.toFixed(2),
    openTone: priceToneClass(last.open - (last.pre_close ?? last.open)),
    intraday: `${formatSignedPrice(intradayChange)} ${formatPercentPoint(intradayPct)}`,
    intradayTone: priceToneClass(intradayChange),
    preClose: formatPrice(last.pre_close ?? null),
    pct: formatPercentPoint(pct),
    priceClass: change >= 0 ? "is-up" : "is-down",
    toneClass,
    volume: formatVolume(last.vol),
  };
}

function dateTicks(candles: StrategyStockCandle[], xForIndex: (index: number) => number) {
  const indexes = Array.from(new Set([0, Math.floor((candles.length - 1) / 2), candles.length - 1]));
  return indexes.map((index, position) => ({
    anchor: tickAnchor(position, indexes.length),
    label: formatTradeDate(candles[index].trade_date),
    x: xForIndex(index),
  }));
}

function tickAnchor(position: number, total: number): "start" | "middle" | "end" {
  if (position === 0) {
    return "start";
  }
  return position === total - 1 ? "end" : "middle";
}

function dateKey(value?: string | null): string | null {
  return dateParts(value)?.key ?? null;
}
function markerLabel(prefix: string, value?: string | null): string {
  const label = dateParts(value)?.label;
  return label ? `${prefix} ${label}` : prefix;
}
function dateParts(value?: string | null): { key: string; label: string } | null {
  if (!value) {
    return null;
  }
  const directMatch = value.match(/^(\d{4})[-/](\d{2})[-/](\d{2})(?:[T\s](\d{2}):(\d{2}))?/);
  if (directMatch) {
    const [, , month, day, hour, minute] = directMatch;
    return {
      key: `${directMatch[1]}${month}${day}`,
      label: hour && minute ? `${month}/${day} ${hour}:${minute}` : `${month}/${day}`,
    };
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  const hour = `${date.getHours()}`.padStart(2, "0");
  const minute = `${date.getMinutes()}`.padStart(2, "0");
  return {
    key: `${year}${month}${day}`,
    label: `${month}/${day} ${hour}:${minute}`,
  };
}

function formatTradeDate(value: string): string {
  if (value.length !== 8) {
    return value;
  }
  return `${value.slice(4, 6)}/${value.slice(6, 8)}`;
}

function formatPrice(value: number | null): string {
  return value === null ? "-" : value.toFixed(2);
}

function formatSignedPrice(value: number | null): string {
  if (value === null) {
    return "-";
  }
  const text = Math.abs(value).toFixed(2);
  return value > 0 ? `+${text}` : value < 0 ? `-${text}` : "0.00";
}

function formatPercentPoint(value: number | null): string {
  if (value === null) {
    return "-";
  }
  const text = `${Math.abs(value).toFixed(2)}%`;
  return value > 0 ? `+${text}` : value < 0 ? `-${text}` : "0.00%";
}

function formatVolume(value?: number | null): string {
  if (value === undefined || value === null) {
    return "-";
  }
  return `${(value / 10000).toFixed(2)}万手`;
}

function formatAmount(value?: number | null): string {
  if (value === undefined || value === null) {
    return "-";
  }
  return `${(value / 100000).toFixed(2)}亿`;
}

function priceToneClass(value: number | null): string {
  if (value === null || value === 0) {
    return "return-flat";
  }
  return value > 0 ? "return-up" : "return-down";
}
