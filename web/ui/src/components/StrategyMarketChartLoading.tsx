export function StrategyMarketChartLoading({ stockName }: { stockName: string }) {
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
    <section className="strategy-market-loading" role="status" aria-live="polite" aria-label={`正在读取${stockName}本地行情`}>
      <div className="strategy-market-loading-head">
        <span className="strategy-market-loading-dot" />
        <div>
          <strong>正在读取本地行情</strong>
          <span>读取日线缓存</span>
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
