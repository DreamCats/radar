import { CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";

import { PanelTitle } from "./PanelTitle";
import type { BacktestGroupBy, RecommendationBacktestSummaryRow } from "../types";

type LeaderboardChartPoint = {
  key: string;
  label: string;
  subtitle: string;
  stableWinRate: number;
  winRateT5: number;
  avgExcess: number;
  avgReturn: number | null;
  sampleCount: number;
  eventCount: number;
  windowWinRates: Array<{ label: string; value: number }>;
};

const COLORS = {
  grid: "var(--color-hairline)",
  text: "var(--color-ink-subtle)",
  up: "var(--color-price-up)",
  mixed: "var(--color-primary-hover)",
  down: "var(--color-price-down)",
};

export function LeaderboardAlphaChart(props: { rows: RecommendationBacktestSummaryRow[]; dimension: BacktestGroupBy }) {
  const points = props.rows
    .map((row) => buildPoint(row, props.dimension))
    .filter((point): point is LeaderboardChartPoint => point !== null)
    .sort((a, b) => pointScore(b) - pointScore(a))
    .slice(0, 50);
  const sampleCounts = points.map((point) => point.sampleCount);
  const maxSampleCount = Math.max(...sampleCounts, 1);
  const watchlist = points.slice(0, 3);

  return (
    <section className="content-panel leaderboard-alpha-panel">
      <PanelTitle title="胜率收益象限" meta="横轴 T+5 超额 · 纵轴 稳定胜率 · 气泡 样本" />
      <div className="leaderboard-alpha-body">
        {points.length === 0 ? (
          <p className="empty-line chart-empty">暂无成熟 T+5 回测结果。</p>
        ) : (
          <>
            <div className="leaderboard-alpha-chart">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 14, right: 22, bottom: 10, left: -8 }}>
                  <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
                  <ReferenceLine x={0} stroke={COLORS.grid} strokeDasharray="4 4" />
                  <ReferenceLine y={0.6} stroke={COLORS.grid} strokeDasharray="4 4" />
                  <XAxis
                    type="number"
                    dataKey="avgExcess"
                    name="平均超额"
                    tickFormatter={formatAxisPercent}
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: COLORS.text, fontSize: 12 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="stableWinRate"
                    name="稳定胜率"
                    domain={[0, 1]}
                    tickFormatter={formatAxisPercent}
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: COLORS.text, fontSize: 12 }}
                  />
                  <ZAxis type="number" dataKey="sampleCount" range={[72, Math.min(620, 180 + maxSampleCount * 36)]} />
                  <Tooltip content={<AlphaTooltip />} cursor={{ stroke: COLORS.grid, strokeDasharray: "3 3" }} />
                  <Scatter data={points} name="榜单项">
                    {points.map((point) => (
                      <Cell key={point.key} fill={pointColor(point)} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </div>
            <ol className="observation-watchlist" aria-label="优先观察榜单">
              {watchlist.map((point, index) => (
                <li key={point.key}>
                  <span>{index + 1}</span>
                  <strong title={point.label}>{point.label}</strong>
                  <em>
                    {formatSignedPercent(point.avgExcess)} · {point.sampleCount}样本
                  </em>
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </section>
  );
}

function buildPoint(row: RecommendationBacktestSummaryRow, dimension: BacktestGroupBy): LeaderboardChartPoint | null {
  const winRateT5 = metric(row, "win_rate_t5");
  const avgExcess = metric(row, "avg_excess_t5");
  const sampleCount = metric(row, "sample_count_t5");
  if (winRateT5 === null || avgExcess === null || sampleCount === null || sampleCount <= 0) {
    return null;
  }
  const windowWinRates = [
    ["T+1", metric(row, "win_rate_t1")],
    ["T+2", metric(row, "win_rate_t2")],
    ["T+3", metric(row, "win_rate_t3")],
    ["T+5", winRateT5],
  ]
    .filter((item): item is [string, number] => typeof item[1] === "number")
    .map(([label, value]) => ({ label, value }));
  const stableWinRate = average(windowWinRates.map((item) => item.value));
  return {
    key: row.key,
    label: rowTitle(row, dimension),
    subtitle: rowSubtitle(row, dimension),
    stableWinRate,
    winRateT5,
    avgExcess,
    avgReturn: metric(row, "avg_return_t5"),
    sampleCount,
    eventCount: row.event_count,
    windowWinRates,
  };
}

function AlphaTooltip(props: { active?: boolean; payload?: Array<{ payload?: LeaderboardChartPoint }> }) {
  if (!props.active || !props.payload?.length) {
    return null;
  }
  const point = props.payload[0]?.payload;
  if (!point) {
    return null;
  }
  return (
    <div className="chart-tooltip leaderboard-alpha-tooltip">
      <p>{point.label}</p>
      <span>{point.subtitle}</span>
      <span>稳定胜率: {formatPercent(point.stableWinRate)}</span>
      <span>T+5 胜率: {formatPercent(point.winRateT5)}</span>
      <span>T+5 平均超额: {formatSignedPercent(point.avgExcess)}</span>
      <span>T+5 平均收益: {formatSignedPercent(point.avgReturn)}</span>
      <span>{point.windowWinRates.map((item) => `${item.label} ${formatPercent(item.value)}`).join(" / ")}</span>
      <span>
        样本: {point.sampleCount} / 推荐事件: {point.eventCount}
      </span>
    </div>
  );
}

function metric(row: RecommendationBacktestSummaryRow, key: string): number | null {
  const value = row.metrics[key];
  return typeof value === "number" ? value : null;
}

function rowTitle(row: RecommendationBacktestSummaryRow, dimension: BacktestGroupBy): string {
  const analyst = row.analyst_display_name || row.source_candidate || "未识别分析师";
  const stock = row.stock_name || row.ts_code || "未识别股票";
  const sector = row.sector_name || "未归因板块";
  if (dimension === "analyst_sector") {
    return `${analyst} · ${sector}`;
  }
  if (dimension === "analyst_stock" || dimension === "source_stock") {
    return `${analyst} · ${stock}`;
  }
  if (dimension === "analyst") {
    return analyst;
  }
  if (dimension === "sector") {
    return sector;
  }
  if (dimension === "stock") {
    return stock;
  }
  return row.source_candidate || "未知来源";
}

function rowSubtitle(row: RecommendationBacktestSummaryRow, dimension: BacktestGroupBy): string {
  if (dimension === "source") {
    return `${row.event_count} 条推荐事件`;
  }
  return [
    row.stock_name || row.ts_code ? `股票 ${row.stock_name || row.ts_code}` : "",
    row.sector_name ? `板块 ${row.sector_name}` : "",
    row.source_candidate ? `来源 ${row.source_candidate}` : "",
  ]
    .filter(Boolean)
    .join(" / ");
}

function pointColor(point: LeaderboardChartPoint): string {
  if (point.stableWinRate >= 0.6 && point.avgExcess >= 0) {
    return COLORS.up;
  }
  if (point.stableWinRate < 0.5 && point.avgExcess < 0) {
    return COLORS.down;
  }
  return COLORS.mixed;
}

function pointScore(point: LeaderboardChartPoint): number {
  return point.stableWinRate * Math.max(point.avgExcess, 0) * Math.sqrt(point.sampleCount);
}

function average(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function formatAxisPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatPercent(value: number | null): string {
  return value === null ? "-" : `${Math.round(value * 1000) / 10}%`;
}

function formatSignedPercent(value: number | null): string {
  if (value === null) {
    return "-";
  }
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${Math.round(value * 10000) / 100}%`;
}
