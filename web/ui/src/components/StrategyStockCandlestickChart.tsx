import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";

import type { StockEvidenceStockCandle } from "../types";

type ChartStock = {
  stock_name: string;
  first_seen_time?: string | null;
  latest_message_time?: string | null;
};

type HoverState = {
  candle: StockEvidenceStockCandle;
  x: number;
  y: number;
};

type ChartTime = string;

const chartColors = {
  background: "#0b0c0e",
  grid: "rgba(47, 52, 61, 0.52)",
  text: "#858b98",
  up: "#e85f5c",
  upSoft: "rgba(232, 95, 92, 0.34)",
  down: "#26a69a",
  downSoft: "rgba(38, 166, 154, 0.34)",
  ma5: "#f0b84f",
  ma10: "#a578ff",
  ma20: "#4e8bff",
  marker: "#f0b84f",
};

export function StrategyStockCandlestickChart({
  candles,
  stock,
  latestIsRealtime = false,
}: {
  candles: StockEvidenceStockCandle[];
  stock: ChartStock;
  latestIsRealtime?: boolean;
}) {
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const [hover, setHover] = useState<HoverState | null>(null);
  const chartData = useMemo(() => buildLightweightChartData(candles, stock), [candles, stock]);
  const activeCandle = hover?.candle ?? candles[candles.length - 1];
  const quote = useMemo(() => quoteSummary(activeCandle), [activeCandle]);
  const latestQuote = useMemo(() => quoteSummary(candles[candles.length - 1]), [candles]);

  useEffect(() => {
    setHover(null);
  }, [candles]);

  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container || chartData.candles.length === 0) {
      return;
    }

    const chart = createChart(container, {
      autoSize: true,
      height: 420,
      layout: {
        background: { type: ColorType.Solid, color: chartColors.background },
        attributionLogo: false,
        fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
        textColor: chartColors.text,
      },
      grid: {
        horzLines: { color: chartColors.grid },
        vertLines: { color: "rgba(47, 52, 61, 0.28)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "rgba(240, 184, 79, 0.32)",
          labelBackgroundColor: chartColors.marker,
          style: LineStyle.Solid,
          width: 1,
        },
        horzLine: {
          color: "rgba(240, 184, 79, 0.45)",
          labelBackgroundColor: chartColors.marker,
        },
      },
      localization: {
        priceFormatter: (price: number) => price.toFixed(2),
      },
      rightPriceScale: {
        borderColor: "rgba(68, 74, 84, 0.54)",
        scaleMargins: { top: 0.08, bottom: 0.32 },
      },
      timeScale: {
        borderColor: "rgba(68, 74, 84, 0.54)",
        rightOffset: 4,
        barSpacing: 8,
        fixLeftEdge: true,
        timeVisible: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
      handleScroll: {
        horzTouchDrag: true,
        mouseWheel: true,
        pressedMouseMove: true,
        vertTouchDrag: false,
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: chartColors.up,
      downColor: chartColors.down,
      wickUpColor: chartColors.up,
      wickDownColor: chartColors.down,
      borderVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });
    candleSeries.setData(chartData.candles);
    candleSeries.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: 0.32 } });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: "rgba(133, 139, 152, 0.26)",
      lastValueVisible: false,
      priceFormat: { type: "volume" },
      priceLineVisible: false,
      priceScaleId: "",
    });
    volumeSeries.setData(chartData.volume);
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.76, bottom: 0 } });

    chartData.maLines.forEach((line) => {
      const series = chart.addSeries(LineSeries, {
        color: line.color,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        lineWidth: 1,
        priceLineVisible: false,
      });
      series.setData(line.data);
    });

    createSeriesMarkers(candleSeries, chartData.markers, { autoScale: true });
    chart.timeScale().fitContent();

    const handleCrosshairMove = (param: MouseEventParams<Time>) => {
      if (!param.time || !param.point || param.point.x < 0 || param.point.y < 0) {
        setHover(null);
        return;
      }
      const key = String(param.time);
      const candle = chartData.candleByTime.get(key);
      if (!candle) {
        setHover(null);
        return;
      }
      const rect = container.getBoundingClientRect();
      setHover({
        candle,
        x: Math.min(param.point.x + 16, Math.max(rect.width - 190, 0)),
        y: Math.min(param.point.y + 14, Math.max(rect.height - 122, 0)),
      });
    };

    chart.subscribeCrosshairMove(handleCrosshairMove);
    return () => {
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      chart.remove();
    };
  }, [chartData]);

  return (
    <section className="strategy-stock-chart-panel">
      <div className="strategy-stock-quote-strip">
        <div className="strategy-stock-last-price">
          <span className="strategy-stock-last-price-label">{hover ? "指向交易日" : "最新收盘"}</span>
          <strong className={quote.toneClass}>{quote.close}</strong>
          <span className="strategy-stock-change-row">
            <em>较昨收</em>
            <b className={quote.toneClass}>
              {quote.change} {quote.pct}
            </b>
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
        <strong>
          证据K线 · {candles.length}交易日{latestIsRealtime ? " · 盘中快照" : ""}
        </strong>
        <span className="strategy-ma-legend">
          <em className="ma5">MA5:{formatPrice(chartData.maLatest[5])}</em>
          <em className="ma10">MA10:{formatPrice(chartData.maLatest[10])}</em>
          <em className="ma20">MA20:{formatPrice(chartData.maLatest[20])}</em>
          <em>拖动缩放看位置</em>
        </span>
      </div>

      <div className="strategy-stock-chart-shell">
        <div ref={chartContainerRef} className="strategy-stock-chart" aria-label={`${stock.stock_name} 证据K线`} />
        {hover ? <ChartHoverCard hover={hover} /> : null}
      </div>

      <div className="strategy-stock-chart-foot">
        <span>首现/最近消息已标在图上</span>
        <span>
          最新 {latestQuote.date} {latestQuote.close} · {latestQuote.change} {latestQuote.pct}
        </span>
      </div>
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

function ChartHoverCard({ hover }: { hover: HoverState }) {
  const quote = quoteSummary(hover.candle);
  return (
    <div className="strategy-chart-hover-card" style={{ left: hover.x, top: hover.y }}>
      <strong>{quote.date}</strong>
      <span>
        开 {quote.open} · 收 <b className={quote.toneClass}>{quote.close}</b>
      </span>
      <span>
        高 {quote.high} · 低 {quote.low}
      </span>
      <span>
        量 {quote.volume} · 额 {quote.amount}
      </span>
    </div>
  );
}

function buildLightweightChartData(candles: StockEvidenceStockCandle[], stock: ChartStock) {
  const candleByTime = new Map<ChartTime, StockEvidenceStockCandle>();
  const candleData: CandlestickData<ChartTime>[] = candles.map((candle) => {
    const time = chartTime(candle.trade_date);
    candleByTime.set(time, candle);
    return {
      close: candle.close,
      high: candle.high,
      low: candle.low,
      open: candle.open,
      time,
    };
  });
  const volume: HistogramData<ChartTime>[] = candles.map((candle) => ({
    color: candle.close >= candle.open ? chartColors.upSoft : chartColors.downSoft,
    time: chartTime(candle.trade_date),
    value: candle.vol ?? 0,
  }));
  const maLines = [
    { color: chartColors.ma5, data: maData(candles, 5), period: 5 },
    { color: chartColors.ma10, data: maData(candles, 10), period: 10 },
    { color: chartColors.ma20, data: maData(candles, 20), period: 20 },
  ];
  return {
    candleByTime,
    candles: candleData,
    maLatest: {
      5: maLatest(candles, 5),
      10: maLatest(candles, 10),
      20: maLatest(candles, 20),
    },
    maLines,
    markers: signalMarkers(candles, stock),
    volume,
  };
}

function maData(candles: StockEvidenceStockCandle[], period: number): LineData<ChartTime>[] {
  const points: LineData<ChartTime>[] = [];
  candles.forEach((candle, index) => {
    const average = maAt(candles, period, index);
    if (average === null) {
      return;
    }
    points.push({ time: chartTime(candle.trade_date), value: average });
  });
  return points;
}

function maLatest(candles: StockEvidenceStockCandle[], period: number): number | null {
  return maAt(candles, period, candles.length - 1);
}

function maAt(candles: StockEvidenceStockCandle[], period: number, index: number): number | null {
  if (index + 1 < period) {
    return null;
  }
  const slice = candles.slice(index + 1 - period, index + 1);
  return slice.reduce((sum, item) => sum + item.close, 0) / period;
}

function signalMarkers(candles: StockEvidenceStockCandle[], stock: ChartStock): SeriesMarker<ChartTime>[] {
  const markers: SeriesMarker<ChartTime>[] = [];
  const firstSeen = dateKey(stock.first_seen_time);
  const latest = dateKey(stock.latest_message_time);
  if (firstSeen) {
    const candle = nearestCandle(candles, firstSeen);
    markers.push({
      color: chartColors.marker,
      position: "belowBar",
      shape: "arrowUp",
      text: markerLabel("首现", stock.first_seen_time),
      time: chartTime(candle.trade_date),
    });
  }
  if (latest && latest !== firstSeen) {
    const candle = nearestCandle(candles, latest);
    markers.push({
      color: "#7aa2ff",
      position: "aboveBar",
      shape: "circle",
      text: markerLabel("最近", stock.latest_message_time),
      time: chartTime(candle.trade_date),
    });
  }
  return markers;
}

function nearestCandle(candles: StockEvidenceStockCandle[], key: string): StockEvidenceStockCandle {
  return candles.find((item) => item.trade_date >= key) ?? candles[candles.length - 1];
}

function quoteSummary(candle: StockEvidenceStockCandle) {
  const change = candle.change ?? (candle.pre_close ? candle.close - candle.pre_close : candle.close - candle.open);
  const pct = candle.pct_chg ?? (candle.pre_close ? (change / candle.pre_close) * 100 : null);
  const intradayChange = candle.close - candle.open;
  const intradayPct = candle.open ? (intradayChange / candle.open) * 100 : null;
  const toneClass = priceToneClass(change);
  return {
    amount: formatAmount(candle.amount),
    change: formatSignedPrice(change),
    close: candle.close.toFixed(2),
    date: formatTradeDate(candle.trade_date),
    high: candle.high.toFixed(2),
    highTone: priceToneClass(candle.high - (candle.pre_close ?? candle.open)),
    low: candle.low.toFixed(2),
    lowTone: priceToneClass(candle.low - (candle.pre_close ?? candle.open)),
    open: candle.open.toFixed(2),
    openTone: priceToneClass(candle.open - (candle.pre_close ?? candle.open)),
    intraday: `${formatSignedPrice(intradayChange)} ${formatPercentPoint(intradayPct)}`,
    intradayTone: priceToneClass(intradayChange),
    preClose: formatPrice(candle.pre_close ?? null),
    pct: formatPercentPoint(pct),
    toneClass,
    volume: formatVolume(candle.vol),
  };
}

function chartTime(value: string): ChartTime {
  if (value.length !== 8) {
    return value;
  }
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
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
  if (value.length === 10) {
    return `${value.slice(5, 7)}/${value.slice(8, 10)}`;
  }
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
