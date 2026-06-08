import { type CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import { Blocks, Building2, CalendarDays, ChartCandlestick, CircleUserRound, RefreshCw, Search, Trophy, UsersRound } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { fetchRecommendationBacktestSummary } from "../api/radarApi";
import { DateField, SelectField } from "../components/FormFields";
import { PanelTitle } from "../components/PanelTitle";
import { StrategyStockDrawer, type StrategyStockDrawerStock } from "../components/StrategyStockDrawer";
import { toIso } from "../lib/datetime";
import { panelMotionState } from "../lib/motion";
import { buildPresetRange, rangeLabel, RANGE_PRESETS, toLocalIso, type LocalRange, type RangePreset } from "../lib/timeRange";
import type { BacktestGroupBy, IngestSource, RecommendationBacktestSummary, RecommendationBacktestSummaryRow } from "../types";

type Dimension = Extract<BacktestGroupBy, "analyst_sector" | "analyst_stock" | "analyst" | "sector" | "stock" | "source">;

const DIMENSIONS: Array<{
  key: Dimension;
  label: string;
  meta: string;
  icon: typeof Trophy;
}> = [
  { key: "analyst_sector", label: "分析师+板块", meta: "看擅长方向", icon: Blocks },
  { key: "analyst_stock", label: "分析师+股票", meta: "看具体标的", icon: Search },
  { key: "analyst", label: "分析师", meta: "看个人稳定性", icon: CircleUserRound },
  { key: "sector", label: "板块", meta: "看方向质量", icon: Building2 },
  { key: "stock", label: "股票", meta: "看标的表现", icon: Trophy },
  { key: "source", label: "来源", meta: "看信息源质量", icon: UsersRound },
];

const emptySummary: RecommendationBacktestSummary = {
  start_time: "",
  end_time: "",
  group_by: "analyst_sector",
  windows: [1, 2, 3, 5],
  row_count: 0,
  rows: [],
};

export function LeaderboardPage() {
  const shouldReduceMotion = useReducedMotion();
  const requestIdRef = useRef(0);
  const [range, setRange] = useState<LocalRange>(() => buildPresetRange("last30d"));
  const [preset, setPreset] = useState<RangePreset>("last30d");
  const [source, setSource] = useState<IngestSource>("all");
  const [dimension, setDimension] = useState<Dimension>("analyst_sector");
  const [minCount, setMinCount] = useState("3");
  const [summary, setSummary] = useState<RecommendationBacktestSummary>(emptySummary);
  const [overview, setOverview] = useState<RecommendationBacktestSummary>(emptySummary);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [selectedStock, setSelectedStock] = useState<StrategyStockDrawerStock | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startValue = toLocalIso(range.startDate, range.startTime);
  const endValue = toLocalIso(range.endDate, range.endTime);
  const canSubmit = Boolean(startValue && endValue) && startValue <= endValue;

  async function load() {
    if (!canSubmit) {
      setError("请选择有效的开始和结束时间。");
      return;
    }
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    setError(null);
    try {
      const baseQuery = {
        start_time: startValue,
        end_time: endValue,
        source,
      };
      const [nextSummary, nextOverview] = await Promise.all([
        fetchRecommendationBacktestSummary({
          ...baseQuery,
          group_by: dimension,
          min_count: Number(minCount),
          limit: 50,
        }),
        fetchRecommendationBacktestSummary({
          ...baseQuery,
          group_by: "source",
          min_count: 1,
          limit: 200,
        }),
      ]);
      if (requestId !== requestIdRef.current) {
        return;
      }
      setSummary(nextSummary);
      setOverview(nextOverview);
      setSelectedKey((current) => {
        if (current && nextSummary.rows.some((row) => row.key === current)) {
          return current;
        }
        return nextSummary.rows[0]?.key ?? null;
      });
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : "榜单加载失败");
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void load();
  }, [dimension, source, minCount, startValue, endValue]);

  const selected = useMemo(
    () => summary.rows.find((row) => row.key === selectedKey) ?? summary.rows[0] ?? null,
    [summary.rows, selectedKey],
  );
  const metrics = useMemo(() => buildOverviewMetrics(overview), [overview]);
  const displayedDimension = isDimension(summary.group_by) ? summary.group_by : dimension;
  const selectedDrawerStock = selected ? drawerStockFromRow(selected, displayedDimension) : null;
  const activeDimension = DIMENSIONS.find((item) => item.key === displayedDimension) ?? DIMENSIONS[0];
  const requestedDimension = DIMENSIONS.find((item) => item.key === dimension) ?? DIMENSIONS[0];
  const loadingLabel = loading && dimension !== displayedDimension ? `正在切换到 ${requestedDimension.label}` : "正在刷新榜单";
  const panelMotion = panelMotionState(shouldReduceMotion);
  const listKey = `${summary.group_by}:${summary.start_time}:${summary.end_time}:${summary.row_count}`;
  const rowTransition = shouldReduceMotion ? { duration: 0.1 } : { duration: 0.2, ease: [0.16, 1, 0.3, 1] as const };

  function applyPreset(value: RangePreset) {
    setPreset(value);
    setRange(buildPresetRange(value));
  }

  function selectDimension(nextDimension: Dimension) {
    if (nextDimension !== dimension) {
      setLoading(true);
      setError(null);
    }
    setDimension(nextDimension);
  }

  function updateDateTime(target: "start" | "end", value: string) {
    const nextValue = toIso(value);
    const [date, time = ""] = nextValue.split("T");
    const dateKey = target === "start" ? "startDate" : "endDate";
    const timeKey = target === "start" ? "startTime" : "endTime";
    setPreset("custom");
    setRange((current) => ({ ...current, [dateKey]: date ?? "", [timeKey]: time.slice(0, 5) }));
  }

  return (
    <section className={loading ? "leaderboard-page loading" : "leaderboard-page"}>
      <div className="leaderboard-header">
        <PanelTitle title="推荐胜率榜" meta="已成熟 T+N 窗口">
          <button className="btn btn-sm" type="button" onClick={() => void load()} disabled={loading} title="刷新榜单">
            <RefreshCw className="leaderboard-refresh-icon" size={15} />
            刷新
          </button>
        </PanelTitle>
        <div className="leaderboard-window">
          <CalendarDays size={15} />
          {rangeLabel(range)}
        </div>
      </div>

      <div className="range-presets leaderboard-presets" aria-label="榜单时间窗口">
        {RANGE_PRESETS.filter(([value]) => value !== "today" && value !== "yesterday").map(([value, label]) => (
          <button
            className={preset === value ? "preset-button active" : "preset-button"}
            key={value}
            type="button"
            onClick={() => applyPreset(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="leaderboard-toolbar">
        <SelectField
          label="来源"
          value={source}
          options={[
            ["all", "全部"],
            ["personal_message", "个人消息"],
            ["group_message", "个人群"],
          ]}
          onChange={(value) => setSource(value as IngestSource)}
        />
        <DateField label="开始" value={startValue} onChange={(value) => updateDateTime("start", value)} />
        <DateField label="结束" value={endValue} onChange={(value) => updateDateTime("end", value)} />
        <SelectField
          label="最小样本"
          value={minCount}
          options={[
            ["1", "1 条"],
            ["3", "3 条"],
            ["5", "5 条"],
            ["10", "10 条"],
          ]}
          onChange={setMinCount}
        />
      </div>

      <div className="leaderboard-metrics">
        <Metric label="推荐事件" value={metrics.eventCount} detail="按来源去重汇总" />
        <Metric label="T+5 胜率" value={formatPercent(metrics.t5WinRate)} detail={`${metrics.t5SampleCount} 个成熟窗口`} />
        <Metric label="T+5 平均收益" value={formatSignedPercent(metrics.t5AvgReturn)} detail="个股收益" tone={metrics.t5AvgReturn} />
        <Metric label="T+5 平均超额" value={formatSignedPercent(metrics.t5AvgExcess)} detail="相对基准" tone={metrics.t5AvgExcess} />
      </div>

      <div className="leaderboard-dimensions" aria-label="榜单维度">
        {DIMENSIONS.map((item) => {
          const Icon = item.icon;
          const dimensionIndex = DIMENSIONS.findIndex((dimensionItem) => dimensionItem.key === item.key);
          return (
            <button
              className={dimension === item.key ? "leaderboard-dimension active" : "leaderboard-dimension"}
              key={item.key}
              type="button"
              onClick={() => selectDimension(item.key)}
              style={{ "--dimension-index": dimensionIndex } as CSSProperties}
            >
              <Icon size={15} />
              <span>{item.label}</span>
              <em>{item.meta}</em>
            </button>
          );
        })}
      </div>

      {error && <p className="error-line">{error}</p>}

      <motion.div className="leaderboard-workspace" layout transition={rowTransition}>
        <motion.section className="content-panel leaderboard-list-panel" layout transition={rowTransition}>
          <PanelTitle title={activeDimension.label} meta={loading ? "加载中" : `${summary.row_count} 组`} />
          <div className="leaderboard-list">
            <AnimatePresence initial={false} mode="popLayout">
              <motion.div
                animate={panelMotion.animate}
                className="leaderboard-list-motion"
                exit={panelMotion.exit}
                initial={panelMotion.initial}
                key={listKey}
                transition={panelMotion.transition}
              >
                {summary.rows.map((row, index) => (
                  <motion.button
                    animate={{ opacity: 1, x: 0 }}
                    className={selected?.key === row.key ? "leaderboard-row active" : "leaderboard-row"}
                    exit={{ opacity: 0, x: -8 }}
                    initial={{ opacity: 0, x: shouldReduceMotion ? 0 : -8 }}
                    key={row.key}
                    layout
                    transition={rowTransition}
                    type="button"
                    onClick={() => setSelectedKey(row.key)}
                    style={{ "--row-index": Math.min(index, 12) } as CSSProperties}
                  >
                    <span className="leaderboard-rank">{index + 1}</span>
                    <span className="leaderboard-row-main">
                      <strong>{rowTitle(row, displayedDimension)}</strong>
                      <em>{rowSubtitle(row, displayedDimension)}</em>
                    </span>
                    <span className="leaderboard-row-side">
                      <strong>{formatPercent(metric(row, "win_rate_t5"))}</strong>
                      <em>{sampleLabel(row, 5)}</em>
                    </span>
                  </motion.button>
                ))}
                {!loading && summary.rows.length === 0 && <p className="empty-line">暂无已成熟回测结果。先在作业页执行推荐回测补齐。</p>}
              </motion.div>
            </AnimatePresence>
          </div>
          <AnimatePresence initial={false}>{loading && <LoadingOverlay label={loadingLabel} />}</AnimatePresence>
        </motion.section>

        <motion.section className="content-panel leaderboard-detail-panel" layout transition={rowTransition}>
          <PanelTitle title={selected ? rowTitle(selected, displayedDimension) : "画像详情"} meta={selected ? confidenceLabel(selected) : "未选择"} />
          <AnimatePresence initial={false} mode="wait">
            {selected ? (
              <motion.div
                animate={panelMotion.animate}
                className="leaderboard-detail-body"
                exit={panelMotion.exit}
                initial={panelMotion.initial}
                key={`${displayedDimension}:${selected.key}`}
                layout
                transition={panelMotion.transition}
              >
                <div className="leaderboard-detail-tags">
                  {detailTags(selected).map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
                {selectedDrawerStock && (
                  <div className="leaderboard-detail-actions">
                    <button
                      className="btn btn-primary btn-sm"
                      type="button"
                      onClick={() => setSelectedStock(selectedDrawerStock)}
                      title="打开本地日 K 线"
                    >
                      <ChartCandlestick size={15} />
                      K 线
                    </button>
                  </div>
                )}
                <div className="leaderboard-window-grid">
                  {summary.windows.map((window) => (
                    <WindowCard key={window} row={selected} window={window} />
                  ))}
                </div>
              </motion.div>
            ) : (
              <motion.p
                animate={panelMotion.animate}
                className="empty-line"
                exit={panelMotion.exit}
                initial={panelMotion.initial}
                key="empty-detail"
                transition={panelMotion.transition}
              >
                选择一个榜单项查看 T+N 表现。
              </motion.p>
            )}
          </AnimatePresence>
          <AnimatePresence initial={false}>{loading && <LoadingOverlay label={loadingLabel} />}</AnimatePresence>
        </motion.section>
      </motion.div>
      <StrategyStockDrawer stock={selectedStock} onClose={() => setSelectedStock(null)} />
    </section>
  );
}

function LoadingOverlay(props: { label: string }) {
  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      className="leaderboard-loading-overlay"
      exit={{ opacity: 0, y: -4 }}
      initial={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
    >
      <span className="leaderboard-loading-pill">
        <i aria-hidden="true" />
        {props.label}
      </span>
      <span className="leaderboard-loading-bar" aria-hidden="true" />
    </motion.div>
  );
}

function isDimension(value: BacktestGroupBy): value is Dimension {
  return DIMENSIONS.some((item) => item.key === value);
}

function Metric(props: { label: string; value: number | string; detail: string; tone?: number | null }) {
  const toneClass = typeof props.tone === "number" && props.tone !== 0 ? (props.tone > 0 ? " up" : " down") : "";
  return (
    <article className={`leaderboard-metric${toneClass}`}>
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      <em>{props.detail}</em>
    </article>
  );
}

function WindowCard(props: { row: RecommendationBacktestSummaryRow; window: number }) {
  const sampleCount = metric(props.row, `sample_count_t${props.window}`);
  const winRate = metric(props.row, `win_rate_t${props.window}`);
  const avgReturn = metric(props.row, `avg_return_t${props.window}`);
  const avgExcess = metric(props.row, `avg_excess_t${props.window}`);
  return (
    <article className="leaderboard-window-card">
      <div>
        <span>T+{props.window}</span>
        <strong>{formatPercent(winRate)}</strong>
      </div>
      <p>{sampleCount} 个成熟窗口</p>
      <dl>
        <div>
          <dt>平均收益</dt>
          <dd className={toneClass(avgReturn)}>{formatSignedPercent(avgReturn)}</dd>
        </div>
        <div>
          <dt>平均超额</dt>
          <dd className={toneClass(avgExcess)}>{formatSignedPercent(avgExcess)}</dd>
        </div>
      </dl>
    </article>
  );
}

function buildOverviewMetrics(summary: RecommendationBacktestSummary) {
  return {
    eventCount: summary.rows.reduce((sum, row) => sum + row.event_count, 0),
    t5SampleCount: sumMetric(summary.rows, "sample_count_t5"),
    t5WinRate: weightedMetric(summary.rows, "win_rate_t5", "sample_count_t5"),
    t5AvgReturn: weightedMetric(summary.rows, "avg_return_t5", "sample_count_t5"),
    t5AvgExcess: weightedMetric(summary.rows, "avg_excess_t5", "sample_count_t5"),
  };
}

function weightedMetric(rows: RecommendationBacktestSummaryRow[], metricKey: string, weightKey: string): number | null {
  let total = 0;
  let weightTotal = 0;
  for (const row of rows) {
    const value = metric(row, metricKey);
    const weight = metric(row, weightKey) ?? 0;
    if (value !== null && weight > 0) {
      total += value * weight;
      weightTotal += weight;
    }
  }
  return weightTotal > 0 ? total / weightTotal : null;
}

function sumMetric(rows: RecommendationBacktestSummaryRow[], key: string): number {
  return rows.reduce((sum, row) => sum + (metric(row, key) ?? 0), 0);
}

function metric(row: RecommendationBacktestSummaryRow, key: string): number | null {
  const value = row.metrics[key];
  return typeof value === "number" ? value : null;
}

function rowTitle(row: RecommendationBacktestSummaryRow, dimension: Dimension): string {
  const analyst = row.analyst_display_name || row.source_candidate || "未识别分析师";
  const stock = row.stock_name || row.ts_code || "未识别股票";
  const sector = row.sector_name || "未归因板块";
  if (dimension === "analyst_sector") {
    return `${analyst} · ${sector}`;
  }
  if (dimension === "analyst_stock") {
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

function rowSubtitle(row: RecommendationBacktestSummaryRow, dimension: Dimension): string {
  const parts = detailTags(row);
  if (dimension === "source") {
    return `${row.event_count} 条推荐事件`;
  }
  return parts.length > 0 ? parts.join(" / ") : `${row.event_count} 条推荐事件`;
}

function detailTags(row: RecommendationBacktestSummaryRow): string[] {
  return [
    row.analyst_display_name ? `分析师 ${row.analyst_display_name}` : "",
    row.stock_name || row.ts_code ? `股票 ${row.stock_name || row.ts_code}` : "",
    row.sector_name ? `板块 ${row.sector_name}` : "",
    row.source_candidate ? `来源 ${row.source_candidate}` : "",
    `${row.event_count} 条推荐事件`,
  ].filter(Boolean);
}

function drawerStockFromRow(row: RecommendationBacktestSummaryRow, dimension: Dimension): StrategyStockDrawerStock | null {
  if (!row.ts_code || (dimension !== "stock" && dimension !== "analyst_stock")) {
    return null;
  }
  return {
    stock_name: row.stock_name || row.ts_code,
    ts_code: row.ts_code,
    event_count: row.event_count,
    average_excess_return_t5: metric(row, "avg_excess_t5"),
    drawer_badge: "推荐胜率榜",
    drawer_metrics: [
      { label: "T+1超额", value: metric(row, "avg_excess_t1") },
      { label: "T+3超额", value: metric(row, "avg_excess_t3") },
      { label: "T+5超额", value: metric(row, "avg_excess_t5") },
      { label: "T+5收益", value: metric(row, "avg_return_t5") },
    ],
    evidence_title: "榜单证据",
    evidence_lines: detailTags(row),
  };
}

function sampleLabel(row: RecommendationBacktestSummaryRow, window: number): string {
  return `${metric(row, `sample_count_t${window}`) ?? 0} 样本`;
}

function confidenceLabel(row: RecommendationBacktestSummaryRow): string {
  const sampleCount = metric(row, "sample_count_t5") ?? 0;
  if (sampleCount >= 10) {
    return "样本较稳";
  }
  if (sampleCount >= 3) {
    return "可参考";
  }
  return "样本偏少";
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

function toneClass(value: number | null): string {
  if (value === null || value === 0) {
    return "";
  }
  return value > 0 ? "up" : "down";
}
