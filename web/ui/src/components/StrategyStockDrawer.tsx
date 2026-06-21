import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { BarChart3, ListChecks, RefreshCw, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { createPortal } from "react-dom";

import { fetchStockEvidenceFinancials, fetchStockEvidenceStockChart } from "../api/radarApi";
import { ChatLauncher } from "./ChatLauncher";
import { StrategyMarketChartLoading } from "./StrategyMarketChartLoading";
import { StockChecklistCard, type StockChecklistData } from "./StockChecklistCard";
import { checklistWithFinancials } from "./stockChecklistFinancials";
import type { StockEvidenceFinancials, StockEvidenceStockChart } from "../types";

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
  checklist?: StockChecklistData;
};

type StrategyStock = StrategyStockDrawerStock;
export type StrategyStockDrawerMode = "chart" | "checklist";

const StrategyStockCandlestickChart = lazy(() =>
  import("./StrategyStockCandlestickChart").then((module) => ({ default: module.StrategyStockCandlestickChart })),
);

function isMobileStockDrawerLayout() {
  return window.matchMedia("(max-width: 720px)").matches;
}

function nextDrawerHistoryState(tsCode: string) {
  const currentState = window.history.state;
  const baseState = currentState && typeof currentState === "object" ? currentState : {};
  return {
    ...baseState,
    radarStrategyStockDrawer: tsCode,
  };
}

type Props = {
  stock: StrategyStock | null;
  initialMode?: StrategyStockDrawerMode;
  onClose: () => void;
};

export function StrategyStockDrawer({ stock, initialMode = "chart", onClose }: Props) {
  const shouldReduceMotion = useReducedMotion();
  const [activeMode, setActiveMode] = useState<StrategyStockDrawerMode>(initialMode);
  const [chart, setChart] = useState<StockEvidenceStockChart | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [financials, setFinancials] = useState<StockEvidenceFinancials | null>(null);
  const [financialLoading, setFinancialLoading] = useState(false);
  const [financialError, setFinancialError] = useState<string | null>(null);
  const openRef = useRef(false);
  const drawerHistoryRef = useRef(false);

  const closeDrawer = useCallback(() => {
    if (drawerHistoryRef.current) {
      drawerHistoryRef.current = false;
      window.history.back();
      return;
    }
    onClose();
  }, [onClose]);

  useEffect(() => {
    setActiveMode(initialMode);
  }, [initialMode, stock?.ts_code]);

  useEffect(() => {
    openRef.current = stock !== null;
  }, [stock]);

  useEffect(() => {
    if (!stock || !isMobileStockDrawerLayout() || drawerHistoryRef.current) {
      return;
    }
    window.history.pushState(nextDrawerHistoryState(stock.ts_code), "", window.location.href);
    drawerHistoryRef.current = true;
  }, [stock]);

  useEffect(() => {
    const onPopState = (event: PopStateEvent) => {
      if (openRef.current && !event.state?.radarStrategyStockDrawer) {
        drawerHistoryRef.current = false;
        onClose();
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [onClose]);

  useEffect(() => {
    if (!stock) {
      setChart(null);
      setError(null);
      setRefreshing(false);
      setFinancials(null);
      setFinancialError(null);
      setFinancialLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setRefreshing(false);
    setError(null);
    setFinancials(null);
    setFinancialError(null);
    setFinancialLoading(false);
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

  async function refreshChart() {
    if (!stock || loading || refreshing) {
      return;
    }
    setRefreshing(true);
    setError(null);
    try {
      const result = await fetchStockEvidenceStockChart(stock.ts_code, { days: 120, refresh: true });
      setChart(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "行情刷新失败");
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    if (!stock?.checklist || activeMode !== "checklist") {
      return;
    }
    let cancelled = false;
    setFinancialLoading(true);
    setFinancialError(null);
    void fetchStockEvidenceFinancials(stock.ts_code, { years: 5 })
      .then((result) => {
        if (!cancelled) {
          setFinancials(result);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setFinancialError(err instanceof Error ? err.message : "财务数据加载失败");
          setFinancials(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setFinancialLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeMode, stock?.checklist, stock?.ts_code]);

  useEffect(() => {
    if (!stock) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeDrawer();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closeDrawer, stock]);

  if (!stock) {
    return createPortal(<AnimatePresence>{null}</AnimatePresence>, document.body);
  }

  const candles = chart?.candles ?? [];
  const evidenceLines = stockEvidenceLines(stock);
  const checklist = stock.checklist ? checklistWithFinancials(stock.checklist, financials, financialLoading, financialError) : null;
  const activePanel = checklist ? activeMode : "chart";
  const shellMotion = drawerShellMotion(shouldReduceMotion);
  const drawerMotion = stockDrawerMotion(shouldReduceMotion);

  const drawer = (
    <motion.div
      className="strategy-stock-drawer-shell"
      role="dialog"
      aria-modal="true"
      aria-label={`${stock.stock_name} 个股深挖`}
      key="strategy-stock-drawer"
      {...shellMotion}
    >
      <motion.button
        className="strategy-stock-drawer-scrim"
        type="button"
        aria-label="关闭K线抽屉"
        onClick={closeDrawer}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={shouldReduceMotion ? { duration: 0.08 } : { duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
      />
      <motion.aside className="strategy-stock-drawer" {...drawerMotion}>
        <header className="strategy-stock-drawer-head">
          <div className="strategy-stock-drawer-title">
            <strong>{stock.stock_name}</strong>
            <span>{stock.ts_code}</span>
          </div>
          <div className="strategy-stock-drawer-head-actions">
            <div className="strategy-stock-mode-switch" role="tablist" aria-label="个股深挖视图">
              <button
                className={activePanel === "chart" ? "active" : ""}
                type="button"
                role="tab"
                aria-selected={activePanel === "chart"}
                title="看K线"
                onClick={() => setActiveMode("chart")}
              >
                <BarChart3 size={14} />
                <span>K线</span>
              </button>
              {checklist && (
                <button
                  className={activePanel === "checklist" ? "active" : ""}
                  type="button"
                  role="tab"
                  aria-selected={activePanel === "checklist"}
                  title="打开个股核查卡"
                  onClick={() => setActiveMode("checklist")}
                >
                  <ListChecks size={14} />
                  <span>核查卡</span>
                </button>
              )}
            </div>
            {activePanel === "chart" && (
              <button
                className={`icon-btn strategy-stock-refresh${refreshing ? " is-refreshing" : ""}`}
                type="button"
                aria-label="刷新行情"
                title="刷新行情"
                onClick={() => void refreshChart()}
                disabled={loading || refreshing}
              >
                <RefreshCw size={15} />
              </button>
            )}
            <ChatLauncher
              title={stock.stock_name}
              subtitle={drawerSubtitle(stock) || stock.ts_code}
              surface="个股深挖"
              entityId={stock.ts_code}
              buttonLabel="AI"
              buttonClassName="btn btn-sm strategy-stock-ai-action"
              context={[
                { label: "代码", value: stock.ts_code },
                { label: "视图", value: stock.drawer_badge ?? "K线复盘" },
                { label: "首现", value: stock.first_seen_time },
                { label: "最近", value: stock.latest_message_time },
                { label: "样本", value: drawerSubtitle(stock) },
              ]}
              evidence={evidenceLines}
              quickPrompts={[
                { label: "分时数据", prompt: "站在投资研究视角解读当前分时或行情数据：价格位置、成交量、资金承接和回落节奏分别说明什么；判断是发酵、分歧、兑现还是过热。" },
                { label: "兑现判断", prompt: "结合首现消息和当前行情，判断股价是提前反映、刚开始发酵，还是利好兑现；列出最关键的证据和反证。" },
                { label: "观察位", prompt: "给出后续观察位：接下来要盯的 3 个价格、量能或消息条件，以及什么情况下降低跟踪优先级。" },
              ]}
              suggestedQuestions={[
                "只看这张K线，当前价格位置和量能有什么风险？",
                "从首现到最近消息，股价是提前反映、刚启动，还是已经兑现？",
                "后续应该盯哪些均线、成交量和回撤位置？",
              ]}
            />
            <button className="icon-btn" type="button" aria-label="关闭" onClick={closeDrawer}>
              <X size={16} />
            </button>
          </div>
        </header>

        <div className="strategy-stock-drawer-tags">
          {stock.drawer_badge && <span className="strategy-stock-context-tag">{stock.drawer_badge}</span>}
          <span>{activePanel === "checklist" ? "个股核查卡" : "行情面板"}</span>
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

          {activePanel === "checklist" && checklist ? (
            <StockChecklistCard stockName={stock.stock_name} tsCode={stock.ts_code} checklist={checklist} />
          ) : (
            <>
              {loading && <StrategyMarketChartLoading stockName={stock.stock_name} />}
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
            </>
          )}
        </div>
      </motion.aside>
    </motion.div>
  );

  return createPortal(<AnimatePresence>{drawer}</AnimatePresence>, document.body);
}

function drawerShellMotion(shouldReduceMotion: boolean | null) {
  if (shouldReduceMotion) {
    return {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: { duration: 0.12 },
    };
  }
  return {
    initial: { opacity: 1 },
    animate: { opacity: 1 },
    exit: { opacity: 1 },
    transition: { duration: 0.18 },
  };
}

function stockDrawerMotion(shouldReduceMotion: boolean | null) {
  if (shouldReduceMotion) {
    return {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: { duration: 0.12 },
    };
  }
  return {
    initial: { opacity: 0.94, y: 14, scale: 0.985 },
    animate: { opacity: 1, y: 0, scale: 1 },
    exit: { opacity: 0, y: 8, scale: 0.99 },
    transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] as const },
  };
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
