import { useEffect, useMemo, useState } from "react";
import { RefreshCw, Search, X } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

import { fetchPremarketSignal } from "../api/radarApi";
import { PageLoadingState } from "../components/PageLoadingState";
import { PanelTitle } from "../components/PanelTitle";
import { formatTime } from "../lib/datetime";
import { panelMotionState } from "../lib/motion";
import type { PremarketConceptRank, PremarketSignalResult, PremarketStockRank } from "../types";

type WindowForm = {
  startDate: string;
  startTime: string;
  endDate: string;
  endTime: string;
};

const DEFAULT_WINDOW_PRESET = "premarket";
const QUICK_WINDOWS = [
  { key: "premarket", label: "盘前", startTime: "07:00", endTime: "09:25" },
  { key: "after_close", label: "盘后至此刻", startTime: "15:00", endTime: "now" },
] as const;
const COLLAPSED_STOCK_LIMIT = 20;

const defaultWindow = (): WindowForm => {
  const now = new Date();
  return {
    startDate: localDateString(now),
    startTime: "07:00",
    endDate: localDateString(now),
    endTime: "09:25",
  };
};

export function PremarketPage() {
  const shouldReduceMotion = useReducedMotion();
  const [windowForm, setWindowForm] = useState<WindowForm>(() => defaultWindow());
  const [windowPreset, setWindowPreset] = useState<string>(DEFAULT_WINDOW_PRESET);
  const [result, setResult] = useState<PremarketSignalResult | null>(null);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const motionState = panelMotionState(shouldReduceMotion);

  const selectedConcept = useMemo(() => {
    return findPremarketConcept(result, selectedCode);
  }, [result, selectedCode]);

  useEffect(() => {
    void loadSignals(windowForm);
  }, []);

  async function loadSignals(nextWindow: WindowForm) {
    setLoading(true);
    setError(null);
    setResult(null);
    setSelectedCode(null);
    setDetailOpen(false);
    try {
      const data = await fetchPremarketSignal({
        start_time: `${nextWindow.startDate}T${nextWindow.startTime}:00`,
        end_time: `${nextWindow.endDate}T${nextWindow.endTime}:00`,
        limit: 30,
      });
      const normalizedData = normalizePremarketResult(data);
      setResult(normalizedData);
      if (!findPremarketConcept(normalizedData, selectedCode)) {
        setSelectedCode(null);
        setDetailOpen(false);
      }
    } catch (err) {
      setResult(null);
      setSelectedCode(null);
      setDetailOpen(false);
      setError(err instanceof Error ? err.message : "查询失败");
    } finally {
      setLoading(false);
    }
  }

  function submitWindow() {
    void loadSignals(windowForm);
  }

  function applyQuickWindow(preset: (typeof QUICK_WINDOWS)[number]) {
    const now = new Date();
    setWindowPreset(preset.key);
    setWindowForm(buildQuickWindow(preset, now));
  }

  function updateWindow(value: Partial<WindowForm>) {
    setWindowPreset("custom");
    setWindowForm((current) => ({ ...current, ...value }));
  }

  return (
    <section className="premarket-page">
      <div className="premarket-control-bar filter-panel">
        <div className="premarket-window-presets" aria-label="快捷消息窗口">
          {QUICK_WINDOWS.map((preset) => (
            <button
              className={windowPreset === preset.key ? "active" : ""}
              key={preset.key}
              type="button"
              onClick={() => applyQuickWindow(preset)}
            >
              {preset.label}
            </button>
          ))}
        </div>
        <label className="field">
          <span>开始日期</span>
          <input
            type="date"
            value={windowForm.startDate}
            onChange={(event) => updateWindow({ startDate: event.target.value })}
          />
        </label>
        <label className="field">
          <span>开始</span>
          <input
            type="time"
            value={windowForm.startTime}
            onChange={(event) => updateWindow({ startTime: event.target.value })}
          />
        </label>
        <label className="field">
          <span>结束日期</span>
          <input
            type="date"
            value={windowForm.endDate}
            onChange={(event) => updateWindow({ endDate: event.target.value })}
          />
        </label>
        <label className="field">
          <span>结束</span>
          <input
            type="time"
            value={windowForm.endTime}
            onChange={(event) => updateWindow({ endTime: event.target.value })}
          />
        </label>
        <button className="btn btn-sm premarket-query-button" type="button" onClick={submitWindow} disabled={loading}>
          <Search size={14} />
          <span>查询</span>
        </button>
        <button
          className={loading ? "btn btn-sm premarket-icon-button is-spinning" : "btn btn-sm premarket-icon-button"}
          type="button"
          aria-label="刷新盘前预测"
          onClick={submitWindow}
          disabled={loading}
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {error && <p className="premarket-error">{error}</p>}

      {loading && !result ? (
        <PageLoadingState label="盘前预测计算中" variant="strategy" />
      ) : (
        <motion.div className="premarket-workspace" {...motionState}>
          <ConceptRankPanel
            loading={loading}
            result={result}
            selectedCode={detailOpen ? selectedCode : null}
            onSelect={(concept) => {
              setSelectedCode(concept.concept_code);
              setDetailOpen(true);
            }}
          />
        </motion.div>
      )}
      {detailOpen && selectedConcept && (
        <ConceptDetailDrawer concept={selectedConcept} onClose={() => setDetailOpen(false)} />
      )}
    </section>
  );
}

function ConceptRankPanel(props: {
  loading: boolean;
  result: PremarketSignalResult | null;
  selectedCode: string | null;
  onSelect: (concept: PremarketConceptRank) => void;
}) {
  const summary = props.result?.summary;
  const topConcepts = props.result?.top_concepts ?? [];
  const bottomConcepts = props.result?.bottom_concepts ?? [];
  const velocityConcepts = props.result?.velocity_concepts ?? [];
  return (
    <section className={props.loading ? "premarket-rank-panel content-panel panel is-refreshing" : "premarket-rank-panel content-panel panel"}>
      <PanelTitle
        title="概念排名"
        meta={
          summary
            ? `${sourceName(summary.concept_source)} / ${summary.dedup_person_stock_mentions} 个去重人股 / ${summary.ranked_concept_count} 个概念`
            : "等待查询"
        }
      />
      <div className="premarket-summary-strip">
        <Metric label="消息" value={summary?.messages_scanned ?? 0} />
        <Metric label="催化" value={summary?.catalyst_items ?? 0} />
        <Metric label="个股" value={summary?.stock_mentions ?? 0} />
      </div>
      {props.result && topConcepts.length === 0 ? (
        <div className="premarket-board-region" aria-busy={props.loading}>
          <div className="premarket-empty">当前窗口没有可排名概念</div>
        </div>
      ) : (
        <div className="premarket-board-region" aria-busy={props.loading}>
          <ConceptBoard
            title="正 Top10"
            meta="强势概念"
            mode="score"
            concepts={topConcepts}
            selectedCode={props.selectedCode}
            onSelect={props.onSelect}
          />
          <ConceptBoard
            title="倒 Top10"
            meta="弱覆盖 / 长尾"
            mode="score"
            concepts={bottomConcepts}
            selectedCode={props.selectedCode}
            onSelect={props.onSelect}
          />
          <ConceptBoard
            title="变化速度 Top10"
            meta="后半 - 前半"
            mode="velocity"
            concepts={velocityConcepts}
            selectedCode={props.selectedCode}
            onSelect={props.onSelect}
          />
        </div>
      )}
    </section>
  );
}

function ConceptBoard(props: {
  title: string;
  meta: string;
  mode: "score" | "velocity";
  concepts: PremarketConceptRank[];
  selectedCode: string | null;
  onSelect: (concept: PremarketConceptRank) => void;
}) {
  return (
    <section className="premarket-board">
      <header>
        <div>
          <strong>{props.title}</strong>
          <span>{props.meta}</span>
        </div>
      </header>
      <div className={props.mode === "velocity" ? "premarket-board-head velocity" : "premarket-board-head"} aria-hidden="true">
        <span>#</span>
        <span>概念</span>
        <span>{props.mode === "velocity" ? "速度" : "分数"}</span>
        <span>{props.mode === "velocity" ? "前半" : "人/股"}</span>
        {props.mode === "velocity" && <span>后半</span>}
      </div>
      <div className="premarket-board-list">
        {props.concepts.map((concept, index) => (
          <button
            className={[
              "premarket-board-row",
              props.mode === "velocity" ? "velocity" : "",
              props.selectedCode === concept.concept_code ? "active" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            key={concept.concept_code}
            type="button"
            onClick={() => props.onSelect(concept)}
          >
            <span className="premarket-rank-index">{String(index + 1).padStart(2, "0")}</span>
            <strong>{concept.concept_name}</strong>
            <em>{props.mode === "velocity" ? signedNumber(concept.velocity_score) : concept.score}</em>
            <span>{props.mode === "velocity" ? concept.early_mention_count : `${concept.person_count}/${concept.stock_count}`}</span>
            {props.mode === "velocity" && <span>{concept.late_mention_count}</span>}
          </button>
        ))}
        {props.concepts.length === 0 && <div className="premarket-empty compact">暂无数据</div>}
      </div>
    </section>
  );
}

function ConceptDetailDrawer(props: { concept: PremarketConceptRank; onClose: () => void }) {
  const [showAllStocks, setShowAllStocks] = useState(false);
  const visibleStocks = props.concept.top_stocks.slice(0, showAllStocks ? undefined : COLLAPSED_STOCK_LIMIT);
  const hiddenStockCount = Math.max(0, props.concept.top_stocks.length - visibleStocks.length);

  useEffect(() => {
    setShowAllStocks(false);
  }, [props.concept.concept_code]);

  return (
    <div className="premarket-detail-backdrop" role="presentation" onMouseDown={props.onClose}>
      <section
        className="premarket-detail-drawer content-panel panel"
        role="dialog"
        aria-modal="true"
        aria-label={`${props.concept.concept_name} 详情`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <PanelTitle
          title={props.concept.concept_name}
          meta={`${sourceName(props.concept.source)} ${props.concept.concept_code}`}
          titleExtra={<span className="premarket-score-pill">score {props.concept.score}</span>}
        >
          <button className="mini-button premarket-detail-close" type="button" aria-label="关闭详情" onClick={props.onClose}>
            <X size={15} />
          </button>
        </PanelTitle>
        <div className="premarket-detail-body">
          <div className="premarket-detail-metrics">
            <Metric label="个股" value={props.concept.stock_count} />
            <Metric label="人数" value={props.concept.person_count} />
            <Metric label="次数" value={props.concept.mention_count} />
            <Metric label="消息" value={props.concept.message_count} />
          </div>
          <div className="premarket-stock-table">
            {visibleStocks.map((stock) => (
              <StockRow key={`${stock.ts_code ?? ""}-${stock.stock_name}`} stock={stock} />
            ))}
          </div>
          {props.concept.top_stocks.length > COLLAPSED_STOCK_LIMIT && (
            <button className="premarket-stock-toggle" type="button" onClick={() => setShowAllStocks((value) => !value)}>
              {showAllStocks ? "收起" : `展开全部 ${props.concept.top_stocks.length} 只`}
              {!showAllStocks && hiddenStockCount > 0 ? `，还有 ${hiddenStockCount} 只` : ""}
            </button>
          )}
          <div className="premarket-evidence-list">
            {props.concept.evidence.map((item) => (
              <article className="premarket-evidence" key={item.message_id}>
                <header>
                  <strong>{item.sender}</strong>
                  <time>{formatTime(item.message_time)}</time>
                  {item.group_name && <span>{item.group_name}</span>}
                </header>
                <p>{item.raw_content}</p>
              </article>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function Metric(props: { label: string; value: number }) {
  return (
    <span className="premarket-metric">
      <strong>{props.value}</strong>
      <em>{props.label}</em>
    </span>
  );
}

function StockRow(props: { stock: PremarketStockRank }) {
  return (
    <div className="premarket-stock-row">
      <div>
        <strong>{props.stock.stock_name}</strong>
        {props.stock.ts_code && <span>{props.stock.ts_code}</span>}
      </div>
      <em>{props.stock.person_count} 人</em>
      <em>{props.stock.mention_count} 次</em>
      <time>{formatTime(props.stock.first_time).slice(11, 16)}</time>
    </div>
  );
}

function sourceName(source: string) {
  if (source === "ths") {
    return "THS";
  }
  if (source === "dc") {
    return "DC";
  }
  return "无概念缓存";
}

function findPremarketConcept(result: PremarketSignalResult | null, code: string | null) {
  if (!result || !code) {
    return null;
  }
  return (
    [...result.top_concepts, ...result.bottom_concepts, ...result.velocity_concepts, ...result.concepts].find(
      (item) => item.concept_code === code,
    ) ?? null
  );
}

function normalizePremarketResult(data: PremarketSignalResult): PremarketSignalResult {
  const concepts = normalizeConcepts(data.concepts);
  return {
    ...data,
    concepts,
    top_concepts: normalizeConcepts(data.top_concepts, concepts.slice(0, 10)),
    bottom_concepts: normalizeConcepts(data.bottom_concepts, concepts.slice(-10).reverse()),
    velocity_concepts: normalizeConcepts(data.velocity_concepts),
    concentration: Array.isArray(data.concentration) ? data.concentration : [],
    time_buckets: Array.isArray(data.time_buckets) ? data.time_buckets : [],
  };
}

function normalizeConcepts(value: PremarketConceptRank[] | undefined, fallback: PremarketConceptRank[] = []) {
  if (!Array.isArray(value)) {
    return fallback;
  }
  return value.map((concept) => ({
    ...concept,
    top_stocks: Array.isArray(concept.top_stocks) ? concept.top_stocks : [],
    catalyst_terms: Array.isArray(concept.catalyst_terms) ? concept.catalyst_terms : [],
    evidence: Array.isArray(concept.evidence) ? concept.evidence : [],
  }));
}

function signedNumber(value: number) {
  return value > 0 ? `+${value}` : value;
}

function buildQuickWindow(preset: (typeof QUICK_WINDOWS)[number], now: Date): WindowForm {
  const start = dateWithTime(now, preset.startTime);
  const end = preset.endTime === "now" ? now : dateWithTime(now, preset.endTime);
  if (preset.key === "after_close" && end <= start) {
    moveToPreviousWeekday(start);
  }
  return {
    startDate: localDateString(start),
    startTime: preset.startTime,
    endDate: localDateString(end),
    endTime: localTimeString(end),
  };
}

function dateWithTime(base: Date, clock: string): Date {
  const [hours, minutes] = clock.split(":").map((value) => Number.parseInt(value, 10));
  return new Date(base.getFullYear(), base.getMonth(), base.getDate(), hours, minutes);
}

function moveToPreviousWeekday(date: Date) {
  do {
    date.setDate(date.getDate() - 1);
  } while (date.getDay() === 0 || date.getDay() === 6);
}

function localDateString(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function localTimeString(date: Date) {
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${hours}:${minutes}`;
}
