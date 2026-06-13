import { CheckCircle2, CircleAlert, MessageSquareText, Network, TrendingUp, Users } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { formatTime } from "../lib/datetime";
import type { StockEvidenceChainDashboard, StockEvidenceChainItem } from "../types";
import { StockEvidenceDetailPanel } from "./StockEvidenceDetailPanel";
import { PanelTitle } from "./PanelTitle";

const STAGE_ORDER = ["线索期", "种子期", "论证期", "扩散期", "定价期", "拥挤期"];
const REVIEW_FILTERS = [
  { key: "全部", label: "全部", states: null },
  { key: "机会", label: "主线确认", states: ["mainline_confirmed", "market_first"] },
  { key: "初动", label: "初动", states: ["volume_start_validation"] },
  { key: "补主题", label: "补主题", states: ["theme_missing"] },
  { key: "补市场", label: "补市场", states: ["needs_market_validation", "one_day_pulse", "evidence_gap"] },
  { key: "市场不认", label: "市场不认", states: ["price_rejected_diffusion", "narrative_rejected"] },
  { key: "已过热", label: "已过热", states: ["overheated_review"] },
  { key: "异常", label: "异常", states: ["llm_error"] },
] as const;
const RECOGNITION_ORDER: Record<string, number> = {
  confirmed: 0,
  just_confirmed: 1,
  just_started: 2,
  unknown: 3,
  pullback_after_pricing: 4,
  rejected: 5,
  overheated: 6,
};
const FAMILY_WEIGHTS: Record<string, number> = {
  catalyst: 5,
  roadshow: 4,
  research: 3,
  push: 3,
  price: 1,
};

type ReviewFilterKey = (typeof REVIEW_FILTERS)[number]["key"];

type Props = {
  data: StockEvidenceChainDashboard | null;
  error: string | null;
  onSelectStock?: (stock: StockEvidenceChainItem) => void;
  onOpenChecklist?: (stock: StockEvidenceChainItem) => void;
};

export function StockEvidenceChainPanel({ data, error, onSelectStock, onOpenChecklist }: Props) {
  const items = data?.items ?? [];
  const [stage, setStage] = useState("全部");
  const [reviewFilter, setReviewFilter] = useState<ReviewFilterKey>("全部");
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const mobileDetailOpenRef = useRef(false);
  const mobileDetailHistoryRef = useRef(false);
  const baseOrder = useMemo(() => new Map(items.map((item, index) => [item.ts_code, index])), [items]);
  const poolCounts = useMemo(() => stockPoolCounts(items), [items]);
  const stageFilteredItems = useMemo(
    () => (stage === "全部" ? items : items.filter((item) => item.stage_label === stage)),
    [items, stage],
  );
  const filteredItems = useMemo(
    () => sortByReviewFilter(filterByReview(stageFilteredItems, reviewFilter), reviewFilter, baseOrder),
    [baseOrder, reviewFilter, stageFilteredItems],
  );
  const reviewCounts = useMemo(() => reviewFilterCounts(stageFilteredItems), [stageFilteredItems]);
  const selected = filteredItems.find((item) => item.ts_code === selectedCode) ?? filteredItems[0] ?? null;
  const stageTabs = useMemo(() => ["全部", ...STAGE_ORDER.filter((label) => data?.stage_counts[label])], [data?.stage_counts]);

  useEffect(() => {
    if (!selectedCode && items[0]) {
      setSelectedCode(items[0].ts_code);
    }
  }, [items, selectedCode]);

  useEffect(() => {
    if (stage !== "全部" && !data?.stage_counts[stage]) {
      setStage("全部");
    }
  }, [data?.stage_counts, stage]);

  useEffect(() => {
    if (reviewFilter !== "全部" && !reviewCounts[reviewFilter]) {
      setReviewFilter("全部");
    }
  }, [reviewCounts, reviewFilter]);

  useEffect(() => {
    setMobileDetailOpen(false);
  }, [reviewFilter, stage]);

  useEffect(() => {
    mobileDetailOpenRef.current = mobileDetailOpen;
  }, [mobileDetailOpen]);

  useEffect(() => {
    const onPopState = (event: PopStateEvent) => {
      if (mobileDetailOpenRef.current && !event.state?.radarStockEvidenceDetail) {
        mobileDetailHistoryRef.current = false;
        setMobileDetailOpen(false);
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  function openMobileDetail(tsCode: string) {
    setSelectedCode(tsCode);
    setMobileDetailOpen(true);
    if (isMobileStockLayout() && !mobileDetailOpenRef.current) {
      window.history.pushState({ radarStockEvidenceDetail: tsCode }, "", window.location.href);
      mobileDetailHistoryRef.current = true;
    }
  }

  function closeMobileDetail() {
    if (mobileDetailHistoryRef.current) {
      mobileDetailHistoryRef.current = false;
      window.history.back();
      return;
    }
    setMobileDetailOpen(false);
  }

  return (
    <div className="stock-evidence-workbench">
      <div className="statbar metric-grid">
        <Metric label="候选股票" value={data?.item_count ?? 0} detail={`强信号 ${poolCounts.strong} / 观察池 ${poolCounts.watch}`} />
        <Metric label="主线确认" value={reviewCount(items, "机会")} detail="主题和市场互相支撑" />
        <Metric label="补证据" value={reviewCount(items, "补主题") + reviewCount(items, "补市场")} detail="先补主题或市场验证" />
        <Metric label="风险复盘" value={reviewCount(items, "市场不认") + reviewCount(items, "已过热") + reviewCount(items, "异常")} detail="优先看反证和避坑" />
      </div>
      {error && <p className="error-line">{error}</p>}
      {!error && !items.length && <p className="empty-line">暂无个股证据链判断。先在作业中心运行「个股证据链」。</p>}
      {!!items.length && (
        <section className="panel stock-evidence-panel">
          <PanelTitle title="个股证据链" meta={windowMeta(data)} titleExtra={<SortRuleHelp />} />
          <div className="stock-evidence-filter-stack">
            <div className="stock-evidence-filter-row stock-evidence-stage-tabs" role="tablist" aria-label="证据链阶段">
              <span className="stock-evidence-filter-label">阶段</span>
              {stageTabs.map((label) => (
                <button className={stage === label ? "active" : ""} type="button" key={label} onClick={() => setStage(label)}>
                  {label}
                  <span>{label === "全部" ? items.length : data?.stage_counts[label]}</span>
                </button>
              ))}
            </div>
            <div className="stock-evidence-filter-row stock-evidence-stage-tabs stock-evidence-review-tabs" role="tablist" aria-label="证据链状态">
              <span className="stock-evidence-filter-label">状态</span>
              {REVIEW_FILTERS.map((filter) => (
                <button
                  className={reviewFilter === filter.key ? "active" : ""}
                  type="button"
                  key={filter.key}
                  onClick={() => setReviewFilter(filter.key)}
                >
                  {filter.label}
                  <span>{reviewCounts[filter.key] ?? 0}</span>
                </button>
              ))}
            </div>
          </div>
          <div className={mobileDetailOpen ? "stock-evidence-layout detail-open" : "stock-evidence-layout"}>
            <div className="stock-evidence-list" aria-label="股票候选">
              {filteredItems.map((item) => (
                <StockEvidenceRow
                  item={item}
                  selected={item.ts_code === selected?.ts_code}
                  key={item.ts_code}
                  onClick={() => openMobileDetail(item.ts_code)}
                  onOpenChart={onSelectStock}
                />
              ))}
              {!filteredItems.length && <p className="stock-evidence-empty">当前筛选暂无股票。</p>}
            </div>
            <StockEvidenceDetailPanel
              item={selected}
              onOpenChart={onSelectStock}
              onOpenChecklist={onOpenChecklist}
              onBackToList={closeMobileDetail}
            />
          </div>
        </section>
      )}
    </div>
  );
}

function isMobileStockLayout(): boolean {
  return window.matchMedia("(max-width: 720px)").matches;
}

function SortRuleHelp() {
  return (
    <span className="stock-evidence-sort-help">
      <button type="button" aria-label="查看排序规则">
        <CircleAlert size={14} />
      </button>
      <span className="stock-evidence-sort-tooltip" role="tooltip">
        <strong>默认按可行动优先级排序</strong>
        <span>先看 review：主线确认、市场先行、补市场验证。</span>
        <span>状态筛选后，会按该状态最关心的证据二次排序。</span>
        <span>再看主题质量、市场认可、阶段和证据强度。</span>
        <span>消息扩散被价格否决、过热、LLM异常会后置。</span>
      </span>
    </span>
  );
}

function StockEvidenceRow({
  item,
  selected,
  onClick,
  onOpenChart,
}: {
  item: StockEvidenceChainItem;
  selected: boolean;
  onClick: () => void;
  onOpenChart?: (stock: StockEvidenceChainItem) => void;
}) {
  return (
    <article className={selected ? "stock-evidence-row selected" : "stock-evidence-row"}>
      <button type="button" onClick={onClick}>
        <div className="stock-evidence-row-head">
          <strong>{item.stock_name}</strong>
          <span>{item.ts_code}</span>
          <CandidatePoolBadge item={item} />
          <StagePill item={item} />
          <ReviewBadge item={item} />
        </div>
        <p>{item.summary || "暂无一句话判断"}</p>
        <div className="stock-evidence-row-metrics">
          <span>
            <MessageSquareText size={13} />
            去重 {item.unique_trigger_count}
          </span>
          <span>
            <Users size={13} />
            {item.sender_count}人/{item.conversation_count}会话
          </span>
          <span>
            <CheckCircle2 size={13} />
            {formatConfidence(item.confidence)}
          </span>
          {item.primary_theme && (
            <span>
              <Network size={13} />
              {item.primary_theme.theme_name}
            </span>
          )}
        </div>
      </button>
      {onOpenChart && (
        <button className="stock-evidence-chart-btn" type="button" onClick={() => onOpenChart(item)}>
          <TrendingUp size={14} />
          K线
        </button>
      )}
    </article>
  );
}

function Metric(props: { label: string; value: number | string; detail: string }) {
  return (
    <article className="stat metric-card">
      <p className="k">{props.label}</p>
      <strong className="v">{props.value}</strong>
      <span className="sub">{props.detail}</span>
    </article>
  );
}

function StagePill({ item }: { item: StockEvidenceChainItem }) {
  return <span className={`stock-evidence-stage stock-evidence-stage-${item.stage}`}>{item.stage_label}</span>;
}

function ReviewBadge({ item }: { item: StockEvidenceChainItem }) {
  return <span className={`stock-evidence-review-badge ${item.review.tone}`}>{item.review.label}</span>;
}

function CandidatePoolBadge({ item }: { item: StockEvidenceChainItem }) {
  const pool = candidatePool(item);
  return (
    <span className={`stock-evidence-pool-badge ${pool.tone}`} title={pool.title}>
      {pool.label}
    </span>
  );
}

function filterByReview(items: StockEvidenceChainItem[], key: ReviewFilterKey): StockEvidenceChainItem[] {
  const filter = REVIEW_FILTERS.find((item) => item.key === key);
  if (!filter?.states) {
    return items;
  }
  return items.filter((item) => filter.states.some((state) => state === item.review.state));
}

function sortByReviewFilter(
  items: StockEvidenceChainItem[],
  key: ReviewFilterKey,
  baseOrder: Map<string, number>,
): StockEvidenceChainItem[] {
  if (key === "全部") {
    return items;
  }
  return [...items].sort((a, b) => compareForReview(a, b, key) || compareBaseOrder(a, b, baseOrder));
}

function compareForReview(a: StockEvidenceChainItem, b: StockEvidenceChainItem, key: ReviewFilterKey): number {
  switch (key) {
    case "机会":
      return (
        compareDesc(themeQuality(a), themeQuality(b)) ||
        compareAsc(recognitionOrder(a), recognitionOrder(b)) ||
        compareDesc(evidenceStrength(a), evidenceStrength(b)) ||
        compareDesc(diffusionScore(a), diffusionScore(b))
      );
    case "初动":
      return (
        compareDesc(freshStartScore(a), freshStartScore(b)) ||
        compareDesc(latestAmountRatio(a), latestAmountRatio(b)) ||
        compareDesc(latestPct(a), latestPct(b))
      );
    case "补主题":
      return (
        compareDesc(stagePressure(a), stagePressure(b)) ||
        compareDesc(diffusionScore(a), diffusionScore(b)) ||
        compareDesc(evidenceStrength(a), evidenceStrength(b))
      );
    case "补市场":
      return (
        compareDesc(diffusionScore(a), diffusionScore(b)) ||
        compareDesc(missingEvidenceCount(a), missingEvidenceCount(b)) ||
        compareDesc(evidenceStrength(a), evidenceStrength(b))
      );
    case "市场不认":
      return (
        compareDesc(diffusionScore(a), diffusionScore(b)) ||
        compareAsc(returnSinceFirst(a), returnSinceFirst(b)) ||
        compareAsc(drawdownFromHigh(a), drawdownFromHigh(b))
      );
    case "已过热":
      return (
        compareDesc(overheatedScore(a), overheatedScore(b)) ||
        compareDesc(returnSinceFirst(a), returnSinceFirst(b)) ||
        compareAsc(drawdownFromHigh(a), drawdownFromHigh(b))
      );
    case "异常":
      return compareDesc(updatedAtMs(a), updatedAtMs(b));
    default:
      return 0;
  }
}

function reviewFilterCounts(items: StockEvidenceChainItem[]): Record<ReviewFilterKey, number> {
  return REVIEW_FILTERS.reduce(
    (counts, filter) => ({ ...counts, [filter.key]: filterByReview(items, filter.key).length }),
    {} as Record<ReviewFilterKey, number>,
  );
}

function reviewCount(items: StockEvidenceChainItem[], key: ReviewFilterKey): number {
  return filterByReview(items, key).length;
}

function windowMeta(data: StockEvidenceChainDashboard | null): string {
  if (!data?.as_of_time) {
    return "暂无最新判断";
  }
  return `截至 ${formatTime(data.as_of_time)} · 证据回看 ${data.evidence_start_time ? formatTime(data.evidence_start_time) : "-"}`;
}

function formatConfidence(value?: number | null): string {
  return value === undefined || value === null ? "-" : `${(value * 100).toFixed(0)}%`;
}

function stockPoolCounts(items: StockEvidenceChainItem[]): { strong: number; watch: number } {
  return items.reduce(
    (counts, item) => {
      const pool = candidatePool(item);
      if (pool.tone === "strong") {
        counts.strong += 1;
      } else if (pool.tone === "watch") {
        counts.watch += 1;
      }
      return counts;
    },
    { strong: 0, watch: 0 },
  );
}

function candidatePool(item: StockEvidenceChainItem): { label: string; tone: "strong" | "watch" | "muted"; title: string } {
  const channels = new Set(item.channels);
  const reasons = item.channels.map(channelLabel).filter(Boolean);
  if (channels.has("heat") || channels.has("early_strong")) {
    return { label: "强信号", tone: "strong", title: reasons.join(" / ") || "强信号入池" };
  }
  if (channels.has("watch")) {
    return { label: "观察池", tone: "watch", title: reasons.join(" / ") || "观察池补位" };
  }
  return { label: "候选", tone: "muted", title: reasons.join(" / ") || "候选入池" };
}

function channelLabel(value: string): string {
  const labels: Record<string, string> = {
    heat: "热度入池",
    early_strong: "早强入池",
    watch: "观察池补位",
  };
  return labels[value] ?? value;
}

function evidenceStrength(item: StockEvidenceChainItem): number {
  return Object.entries(FAMILY_WEIGHTS).reduce(
    (score, [family, weight]) => score + (item.family_counts[family] ?? 0) * weight,
    item.evidence_count,
  );
}

function diffusionScore(item: StockEvidenceChainItem): number {
  return Math.min(item.unique_trigger_count, 12) + Math.min(item.sender_count, 6) * 2 + Math.min(item.conversation_count, 6) * 2;
}

function themeQuality(item: StockEvidenceChainItem): number {
  return item.primary_theme?.quality_score ?? item.themes[0]?.quality_score ?? 0;
}

function recognitionOrder(item: StockEvidenceChainItem): number {
  return RECOGNITION_ORDER[item.recognition.state] ?? 9;
}

function latestAmountRatio(item: StockEvidenceChainItem): number {
  return numberScore(latestMarketPoint(item)?.amount_ratio_5d ?? item.primary_theme?.amount_ratio_5d);
}

function latestPct(item: StockEvidenceChainItem): number {
  return numberScore(latestMarketPoint(item)?.pct_chg);
}

function returnSinceFirst(item: StockEvidenceChainItem): number {
  return numberScore(item.market_summary.return_since_first_point);
}

function drawdownFromHigh(item: StockEvidenceChainItem): number {
  return numberScore(item.market_summary.drawdown_from_selected_high);
}

function freshStartScore(item: StockEvidenceChainItem): number {
  const earlyPenalty = Math.max(returnSinceFirst(item) * 100 - 8, 0);
  return latestAmountRatio(item) * 4 + Math.max(latestPct(item), 0) - earlyPenalty;
}

function overheatedScore(item: StockEvidenceChainItem): number {
  return Math.max(
    returnSinceFirst(item) * 100,
    numberScore(item.primary_theme?.stock_return_20d) * 100,
    numberScore(item.primary_theme?.stock_return_5d) * 100,
  );
}

function stagePressure(item: StockEvidenceChainItem): number {
  const scores: Record<string, number> = {
    crowded: 6,
    pricing: 5,
    spreading: 4,
    formed: 3,
    seed: 2,
    lead: 1,
  };
  return scores[item.stage] ?? 0;
}

function missingEvidenceCount(item: StockEvidenceChainItem): number {
  return item.recognition.missing_evidence.length + (item.lifecycle_digest?.missing_evidence.length ?? 0);
}

function updatedAtMs(item: StockEvidenceChainItem): number {
  const time = Date.parse(item.updated_at);
  return Number.isFinite(time) ? time : 0;
}

function numberScore(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function latestMarketPoint(item: StockEvidenceChainItem): StockEvidenceChainItem["market_points"][number] | undefined {
  return item.market_points[item.market_points.length - 1];
}

function compareDesc(left: number, right: number): number {
  return right - left;
}

function compareAsc(left: number, right: number): number {
  return left - right;
}

function compareBaseOrder(a: StockEvidenceChainItem, b: StockEvidenceChainItem, baseOrder: Map<string, number>): number {
  return (baseOrder.get(a.ts_code) ?? 999999) - (baseOrder.get(b.ts_code) ?? 999999);
}
