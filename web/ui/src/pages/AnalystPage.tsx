import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Clock3, Database, Info, RefreshCw, UserRoundCheck, X } from "lucide-react";

import { fetchAnalystBacktestMessageEvidence, fetchAnalystBacktestSummary, fetchRuns } from "../api/radarApi";
import { PageLoadingState, PageRefreshProgress } from "../components/PageLoadingState";
import { formatTime } from "../lib/datetime";
import { useEscapeToClose } from "../lib/useEscapeToClose";
import { useSwipeToCloseSheet } from "../lib/useSwipeToCloseSheet";
import type {
  AnalystBacktestEvidenceItem,
  AnalystBacktestMessageEvidence,
  AnalystBacktestMessageEvidenceItem,
  AnalystBacktestSummary,
  AnalystBacktestSummaryRow,
  IngestSource,
  RunItem,
} from "../types";

const WINDOW_OPTIONS = [1, 3, 5] as const;
const SOURCE_OPTIONS: Array<[IngestSource, string]> = [
  ["all", "全部"],
  ["group_message", "个人群"],
  ["personal_message", "个人消息"],
];
const ANALYST_SUMMARY_LIMIT = 100;

export function AnalystPage() {
  const [lookbackDays, setLookbackDays] = useState(40);
  const [window, setWindow] = useState(5);
  const [source, setSource] = useState<IngestSource>("all");
  const [includeBroadList, setIncludeBroadList] = useState(false);
  const [summary, setSummary] = useState<AnalystBacktestSummary | null>(null);
  const [evidence, setEvidence] = useState<AnalystBacktestMessageEvidence | null>(null);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [selectedAnalystId, setSelectedAnalystId] = useState<string>("");
  const [selectedEvidence, setSelectedEvidence] = useState<AnalystBacktestMessageEvidenceItem | null>(null);
  const [detailSheetOpen, setDetailSheetOpen] = useState(false);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [loadingEvidence, setLoadingEvidence] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const range = useMemo(() => buildLookbackRange(lookbackDays), [lookbackDays]);

  async function refresh() {
    setLoadingSummary(true);
    setError(null);
    try {
      const [nextSummary, nextRuns] = await Promise.all([
        fetchAnalystBacktestSummary({
          start_time: range.startTime,
          end_time: range.endTime,
          source,
          window: [window],
          limit: ANALYST_SUMMARY_LIMIT,
          include_broad_list: includeBroadList,
        }),
        fetchRuns({ kinds: ["analyst_stock_mention_backtest_refresh"], limit: 5 }),
      ]);
      setSummary(nextSummary);
      setRuns(nextRuns);
      setDetailSheetOpen(false);
      setSelectedEvidence(null);
      setSelectedAnalystId((current) => {
        if (current && nextSummary.rows.some((row) => row.analyst_id === current)) {
          return current;
        }
        return nextSummary.rows[0]?.analyst_id ?? "";
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载分析师回测失败");
    } finally {
      setLoadingSummary(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, [range.startTime, range.endTime, source, window, includeBroadList]);

  const selectedRow = summary?.rows.find((row) => row.analyst_id === selectedAnalystId) ?? summary?.rows[0] ?? null;

  useEffect(() => {
    if (!selectedRow) {
      setEvidence(null);
      setSelectedEvidence(null);
      return;
    }
    let cancelled = false;
    setLoadingEvidence(true);
    setSelectedEvidence(null);
    fetchAnalystBacktestMessageEvidence({
      start_time: range.startTime,
      end_time: range.endTime,
      window,
      analyst: selectedRow.analyst_id,
      source,
      limit: 50,
      include_broad_list: includeBroadList,
    })
      .then((nextEvidence) => {
        if (!cancelled) {
          setEvidence(nextEvidence);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "加载原文证据失败");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingEvidence(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRow?.analyst_id, range.startTime, range.endTime, source, window, includeBroadList]);

  const latestRun = runs[0];
  const running = runs.some((run) => run.status === "running");
  const initialLoading = loadingSummary && !summary;

  function selectAnalyst(row: AnalystBacktestSummaryRow) {
    setSelectedAnalystId(row.analyst_id);
    setDetailSheetOpen(true);
  }

  function closeDetailSheet() {
    setDetailSheetOpen(false);
    setSelectedEvidence(null);
  }

  const detailSheetSwipe = useSwipeToCloseSheet(closeDetailSheet);
  useEscapeToClose(closeDetailSheet, { enabled: detailSheetOpen && !selectedEvidence });

  return (
    <section className="analyst-page">
      <div className="analyst-header">
        <div>
          <span className="analyst-kicker">
            <UserRoundCheck size={15} />
            分析师
          </span>
          <h1>近期分析师回测</h1>
        </div>
        <div className="analyst-toolbar">
          {loadingSummary && !initialLoading ? <PageRefreshProgress label="正在刷新分析师" /> : null}
          <button className="btn btn-sm" type="button" onClick={() => void refresh()} disabled={loadingSummary}>
            <RefreshCw size={15} />
            刷新
          </button>
        </div>
      </div>

      <div className="analyst-filter-row">
        <label className="field analyst-field">
          <span>窗口</span>
          <select value={lookbackDays} onChange={(event) => setLookbackDays(Number(event.target.value))}>
            <option value={30}>近 30 天</option>
            <option value={40}>近 40 天</option>
            <option value={60}>近 60 天</option>
          </select>
        </label>
        <label className="field analyst-field">
          <span>来源</span>
          <select value={source} onChange={(event) => setSource(event.target.value as IngestSource)}>
            {SOURCE_OPTIONS.map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <div className="analyst-window-field">
          <span>回测</span>
          <div className="analyst-window-tabs" role="tablist" aria-label="回测窗口">
            {WINDOW_OPTIONS.map((item) => (
              <button
                className={window === item ? "active" : ""}
                type="button"
                role="tab"
                aria-selected={window === item}
                key={item}
                onClick={() => setWindow(item)}
              >
                T+{item}
              </button>
            ))}
          </div>
        </div>
        <label className="analyst-check">
          <input
            type="checkbox"
            checked={includeBroadList}
            onChange={(event) => setIncludeBroadList(event.target.checked)}
          />
          包含 broad_list
        </label>
      </div>

      <div className="analyst-status-line">
        <span>
          <Database size={14} />
          {summary ? `${summary.row_count} 位分析师 · 展示 Top ${summary.rows.length}` : "等待数据"}
        </span>
        <span>
          <Clock3 size={14} />
          {range.label}
        </span>
        {running ? <span className="status running">回测运行中</span> : null}
        {!running && latestRun ? <span className={`status ${latestRun.status}`}>最近作业 {latestRun.status}</span> : null}
        <RankingHelp />
      </div>

      {error ? <p className="analyst-error">{error}</p> : null}

      {initialLoading ? (
        <PageLoadingState label="正在加载分析师回测" variant="strategy" />
      ) : (
        <div className="analyst-layout">
          <section className="analyst-list-panel">
            {summary?.rows.length ? (
              <div className="analyst-list">
                {summary.rows.map((row, index) => (
                  <button
                    className={row.analyst_id === selectedRow?.analyst_id ? "analyst-row active" : "analyst-row"}
                    type="button"
                    key={row.analyst_id}
                    onClick={() => selectAnalyst(row)}
                  >
                    <span className="analyst-rank">{index + 1}</span>
                    <span className="analyst-row-main">
                      <strong>{row.analyst_display_name}</strong>
                      <em>{row.latest_event_time ? `最近证据 ${formatTime(row.latest_event_time)}` : "暂无时间"}</em>
                    </span>
                    <span className="analyst-row-side">
                      <strong className={toneClass(metric(row, "avg_excess", window))}>
                        {pct(metric(row, "avg_excess", window))}
                      </strong>
                      <em>综合 {scoreText(row, window)} · n={intMetric(row, "sample_count", window)}</em>
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="analyst-empty">
                <strong>暂无分析师回测结果</strong>
                <span>先在作业页执行“分析师回测”，或检查消息、股票映射和行情覆盖水位。</span>
              </div>
            )}
          </section>

          {selectedRow && detailSheetOpen ? (
            <button
              className="analyst-detail-scrim"
              type="button"
              aria-label="关闭分析师详情"
              onClick={closeDetailSheet}
            />
          ) : null}

          <section className={detailSheetOpen ? "analyst-detail-panel sheet-open" : "analyst-detail-panel"}>
            {selectedRow ? (
              <>
                <div className="analyst-detail-head" {...detailSheetSwipe}>
                  <div>
                    <span className="analyst-kicker">当前分析师</span>
                    <h2>{selectedRow.analyst_display_name}</h2>
                  </div>
                  <div className="analyst-detail-head-actions">
                    <div className="analyst-detail-score">
                      <strong className={toneClass(metric(selectedRow, "avg_return", window))}>
                        {pct(metric(selectedRow, "avg_return", window))}
                      </strong>
                      <span>T+{window} 平均收益</span>
                    </div>
                    <button className="analyst-icon-button analyst-detail-close" type="button" onClick={closeDetailSheet} aria-label="关闭分析师详情">
                      <X size={16} />
                    </button>
                  </div>
                </div>
                <div className="analyst-metrics">
                  <Metric label="成熟样本" value={`${intMetric(selectedRow, "sample_count", window)}`} />
                  <Metric label="正收益率" value={pct(metric(selectedRow, "positive_rate", window), 1)} />
                  <Metric label="平均超额" value={pct(metric(selectedRow, "avg_excess", window))} tone={toneClass(metric(selectedRow, "avg_excess", window))} />
                  <Metric label="提及数" value={`${selectedRow.event_count}`} />
                </div>
                <div className="analyst-evidence-head">
                  <strong>原文证据</strong>
                  {loadingEvidence ? <PageRefreshProgress label="正在加载原文" /> : null}
                </div>
                <EvidenceList
                  rows={evidence?.rows ?? []}
                  loading={loadingEvidence}
                  onOpen={setSelectedEvidence}
                />
                {selectedEvidence ? (
                  <EvidenceDrawer
                    evidence={selectedEvidence}
                    window={window}
                    onClose={() => setSelectedEvidence(null)}
                  />
                ) : null}
              </>
            ) : (
              <div className="analyst-empty detail">
                <strong>选择一位分析师</strong>
                <span>左侧列表按最近未成熟日期排序，同日期再看平均超额。</span>
              </div>
            )}
          </section>
        </div>
      )}
    </section>
  );
}

function RankingHelp() {
  return (
    <button className="analyst-ranking-help" type="button" aria-label="查看排序口径">
      <Info size={13} />
      <span className="analyst-ranking-tooltip" role="tooltip">
        <strong>排序口径</strong>
        <span>默认展示 Top 100，先按当前 T+窗口的最近未成熟证据日期倒序。</span>
        <span>同一日期下，按已成熟样本的平均超额收益降序。</span>
        <span>没有未成熟证据的分析师排在有未成熟证据的人后面。</span>
        <span>不再用最小样本数过滤；n 和综合分只作为参考与极端同分兜底。</span>
      </span>
    </button>
  );
}

function EvidenceList(props: {
  rows: AnalystBacktestMessageEvidenceItem[];
  loading: boolean;
  onOpen: (row: AnalystBacktestMessageEvidenceItem) => void;
}) {
  if (!props.loading && props.rows.length === 0) {
    return (
      <div className="analyst-empty evidence">
        <strong>暂无原文证据</strong>
        <span>当前筛选下没有可展示的提及样本。</span>
      </div>
    );
  }
  return (
    <div className="analyst-evidence-list">
      {props.rows.map((row) => (
        <button className="analyst-evidence-item" type="button" key={row.message_id} onClick={() => props.onOpen(row)}>
          <div className="analyst-evidence-title">
            <div>
              <strong>{formatTime(row.message_time)}</strong>
            </div>
            <strong className={toneClass(messageMetric(row, "avg_return"))}>{pct(messageMetric(row, "avg_return"))}</strong>
          </div>
          <p>{previewText(row.raw_content)}</p>
          <div className="analyst-stock-chip-row">
            {row.items.slice(0, 7).map((item) => (
              <span className="analyst-stock-chip" key={item.mention_id}>
                {item.stock_name}
                <em className={toneClass(item.return_rate)}>{pct(item.return_rate)}</em>
              </span>
            ))}
            {row.items.length > 7 ? <span className="analyst-stock-chip muted">+{row.items.length - 7}</span> : null}
          </div>
          <div className="analyst-evidence-meta">
            <span>{formatTime(row.message_time)}</span>
            <span>命中 {row.stock_count} 只</span>
            <span>已成熟 {intMessageMetric(row, "succeeded_count")} 只</span>
            <span>平均超额 {pct(messageMetric(row, "avg_excess"))}</span>
            {row.quality_flags.map((flag) => (
              <span key={flag}>{flag}</span>
            ))}
          </div>
        </button>
      ))}
    </div>
  );
}

function EvidenceDrawer(props: { evidence: AnalystBacktestMessageEvidenceItem; window: number; onClose: () => void }) {
  const swipeClose = useSwipeToCloseSheet(props.onClose);
  useEscapeToClose(props.onClose);
  return createPortal(
    <div className="analyst-drawer-backdrop" role="presentation" onClick={props.onClose}>
      <aside className="analyst-drawer" role="dialog" aria-modal="true" aria-label="原文证据详情" onClick={(event) => event.stopPropagation()}>
        <div className="analyst-drawer-head" {...swipeClose}>
          <div>
            <span className="analyst-kicker">原文证据</span>
            <h3>{formatTime(props.evidence.message_time)}</h3>
          </div>
          <button className="analyst-icon-button" type="button" onClick={props.onClose} aria-label="关闭">
            <X size={16} />
          </button>
        </div>
        <div className="analyst-drawer-summary">
          <Metric label="命中标的" value={`${props.evidence.stock_count}`} />
          <Metric label="平均收益" value={pct(messageMetric(props.evidence, "avg_return"))} tone={toneClass(messageMetric(props.evidence, "avg_return"))} />
          <Metric label="平均超额" value={pct(messageMetric(props.evidence, "avg_excess"))} tone={toneClass(messageMetric(props.evidence, "avg_excess"))} />
          <Metric label="正收益率" value={pct(messageMetric(props.evidence, "positive_rate"), 1)} />
        </div>
        <div className="analyst-drawer-body">
          <section className="analyst-drawer-section">
            <strong>完整原文</strong>
            <pre>{props.evidence.raw_content}</pre>
          </section>
          <section className="analyst-drawer-section">
            <strong>T+{props.window} 标的表现</strong>
            <div className="analyst-stock-table">
              {props.evidence.items.map((item) => (
                <div className="analyst-stock-row" key={item.mention_id}>
                  <span>
                    <strong>{item.stock_name}</strong>
                    <em>{item.ts_code}</em>
                  </span>
                  <span>{statusLabel(item.status)}</span>
                  <strong className={toneClass(item.return_rate)}>{pct(item.return_rate)}</strong>
                  <em>超额 {pct(item.excess_return_rate)}</em>
                </div>
              ))}
            </div>
          </section>
        </div>
      </aside>
    </div>,
    document.body,
  );
}

function Metric(props: { label: string; value: string; tone?: string }) {
  return (
    <div className="analyst-metric">
      <span>{props.label}</span>
      <strong className={props.tone}>{props.value}</strong>
    </div>
  );
}

function buildLookbackRange(days: number): { startTime: string; endTime: string; label: string } {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - days);
  start.setHours(0, 0, 0, 0);
  return {
    startTime: localIso(start),
    endTime: localIso(end),
    label: `${dateLabel(start)} - ${dateLabel(end)}`,
  };
}

function localIso(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  const hour = `${date.getHours()}`.padStart(2, "0");
  const minute = `${date.getMinutes()}`.padStart(2, "0");
  const second = `${date.getSeconds()}`.padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}:${second}`;
}

function dateLabel(date: Date): string {
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${month}-${day}`;
}

function metric(row: AnalystBacktestSummaryRow, key: string, window: number): number | null {
  const value = row.metrics[`${key}_t${window}`];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function intMetric(row: AnalystBacktestSummaryRow, key: string, window: number): number {
  return Math.round(metric(row, key, window) ?? 0);
}

function scoreText(row: AnalystBacktestSummaryRow, window: number): string {
  const value = metric(row, "ranking_score", window);
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(1) : "--";
}

function messageMetric(row: AnalystBacktestMessageEvidenceItem, key: string): number | null {
  const value = row.metrics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function intMessageMetric(row: AnalystBacktestMessageEvidenceItem, key: string): number {
  return Math.round(messageMetric(row, key) ?? 0);
}

function previewText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function pct(value: number | null | undefined, digits = 2): string {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : "--";
}

function toneClass(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value === 0) {
    return "";
  }
  return value > 0 ? "up" : "down";
}

function statusLabel(status: AnalystBacktestEvidenceItem["status"]): string {
  if (status === "succeeded") {
    return "已成熟";
  }
  if (status === "pending") {
    return "待成熟";
  }
  if (status === "missing_price") {
    return "缺行情";
  }
  if (status === "failed") {
    return "失败";
  }
  return "未补齐";
}
