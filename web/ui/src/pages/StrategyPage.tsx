import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { fetchStockEvidenceChainLatest } from "../api/radarApi";
import { PageLoadingState, PageRefreshProgress } from "../components/PageLoadingState";
import { StockEvidenceChainPanel } from "../components/StockEvidenceChainPanel";
import { type StockChecklistData, type StockChecklistSection } from "../components/StockChecklistCard";
import { StrategyStockDrawer, type StrategyStockDrawerMode, type StrategyStockDrawerStock } from "../components/StrategyStockDrawer";
import { formatTime } from "../lib/datetime";
import type { StockEvidenceChainDashboard, StockEvidenceChainItem } from "../types";

export function StrategyPage() {
  const [data, setData] = useState<StockEvidenceChainDashboard | null>(null);
  const [selectedStock, setSelectedStock] = useState<StrategyStockDrawerStock | null>(null);
  const [drawerMode, setDrawerMode] = useState<StrategyStockDrawerMode>("chart");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchStockEvidenceChainLatest({ limit: 120 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const initialLoading = loading && !data;
  const openStockDrawer = (stock: StockEvidenceChainItem, mode: StrategyStockDrawerMode) => {
    setSelectedStock(drawerStock(stock));
    setDrawerMode(mode);
  };

  return (
    <section className="strategy-page">
      <div className="dashboard-actions">
        <p>{strategyHeaderText(initialLoading, data)}</p>
        <div>
          {loading && !initialLoading && <PageRefreshProgress label="正在刷新策略" />}
          <button className="btn btn-sm" type="button" onClick={() => void refresh()} disabled={loading}>
            <RefreshCw size={15} />
            刷新
          </button>
        </div>
      </div>
      <div className="strategy-mode-tabs" role="tablist" aria-label="策略模式">
        <button className="active" type="button" role="tab" aria-selected="true">
          个股证据链
        </button>
      </div>
      {initialLoading ? (
        <PageLoadingState label="正在加载个股证据链" variant="strategy" />
      ) : (
        <StockEvidenceChainPanel
          data={data}
          error={error}
          onSelectStock={(stock) => openStockDrawer(stock, "chart")}
          onOpenChecklist={(stock) => openStockDrawer(stock, "checklist")}
        />
      )}
      <StrategyStockDrawer
        key={selectedStock ? `${selectedStock.ts_code}-${drawerMode}` : "closed"}
        stock={selectedStock}
        initialMode={drawerMode}
        onClose={() => setSelectedStock(null)}
      />
    </section>
  );
}

function strategyHeaderText(loading: boolean, data: StockEvidenceChainDashboard | null): string {
  if (loading) {
    return "正在加载个股证据链";
  }
  if (!data?.as_of_time) {
    return "暂无个股证据链判断";
  }
  return `个股证据链 ${formatTime(data.as_of_time)} · ${data.item_count} 个候选`;
}

function drawerStock(item: StockEvidenceChainItem): StrategyStockDrawerStock {
  return {
    stock_name: item.stock_name,
    ts_code: item.ts_code,
    event_count: item.trigger_count,
    source_count: item.sender_count,
    first_seen_time: firstEvidenceTime(item),
    latest_message_time: item.updated_at,
    price_return_since_first_seen: numberValue(item.market_summary.return_since_first_point),
    drawdown_from_high_since_first_seen: numberValue(item.market_summary.drawdown_from_selected_high),
    drawer_context: [
      { label: "首现", value: firstEvidenceTime(item) },
      { label: "最近", value: item.updated_at },
      { label: "发送人", value: item.sender_count },
      { label: "会话", value: item.conversation_count },
    ],
    drawer_metrics: [
      { label: "区间收益", value: numberValue(item.market_summary.return_since_first_point) },
      { label: "高点回撤", value: numberValue(item.market_summary.drawdown_from_selected_high) },
      { label: "5日强弱", value: numberValue(item.primary_theme?.stock_return_5d) },
      { label: "量能", value: volumeRatioText(item.primary_theme?.amount_ratio_5d) },
    ],
    evidence_title: "核查依据",
    evidence_lines: stockEvidenceLines(item),
    checklist: stockChecklist(item),
  };
}

function stockChecklist(item: StockEvidenceChainItem): StockChecklistData {
  const status = checklistStatus(item);
  return {
    status: status.label,
    tone: status.tone,
    summary: item.summary || item.review.headline || "先按证据链核查，暂不输出买卖结论。",
    metrics: [
      { label: "阶段", value: item.stage_label },
      { label: "复盘", value: item.review.label },
      { label: "置信", value: formatConfidence(item.confidence) },
      { label: "区间", value: formatPercent(numberValue(item.market_summary.return_since_first_point), true), tone: metricTone(numberValue(item.market_summary.return_since_first_point)) },
    ],
    sections: [
      companySection(item),
      logicSection(item),
      catalystSection(item),
      financeSection(),
      marketSection(item),
      riskSection(item),
    ],
  };
}

function companySection(item: StockEvidenceChainItem): StockChecklistSection {
  const theme = item.primary_theme ?? item.themes[0] ?? null;
  return {
    key: "company",
    icon: "company",
    title: "公司身份",
    caption: "公司做什么，处在产业链哪段。",
    status: theme ? "先按主题核查" : "待补主营",
    tone: "missing",
    lines: [
      theme ? `当前先按「${theme.theme_name}」里的 ${theme.role || "候选"} 角色观察。` : "暂无自动主题归属，需要补主营业务和产业链位置。",
      "主营业务、客户结构、收入构成还未接入财报/公告数据，第一版不假装完整。",
    ],
    empty: "公司身份待补全。",
  };
}

function logicSection(item: StockEvidenceChainItem): StockChecklistSection {
  return {
    key: "logic",
    icon: "logic",
    title: "消息逻辑",
    caption: "消息源为什么把它推到候选池。",
    status: item.why.length ? "有证据" : "待补证据",
    tone: item.why.length ? "ready" : "missing",
    lines: dedupe([item.summary, ...item.why.slice(0, 4)]),
    empty: "暂无清晰消息逻辑。",
  };
}

function catalystSection(item: StockEvidenceChainItem): StockChecklistSection {
  const familyLines = Object.entries(item.family_counts)
    .filter(([, count]) => count > 0)
    .slice(0, 5)
    .map(([family, count]) => `${familyLabel(family)} ${count} 条`);
  const theme = item.primary_theme ?? item.themes[0] ?? null;
  return {
    key: "catalyst",
    icon: "catalyst",
    title: "催化传导",
    caption: "事件能否传到收入、利润或估值。",
    status: familyLines.length ? "有催化线索" : "待确认",
    tone: familyLines.length ? "watch" : "missing",
    lines: dedupe([...familyLines, ...(theme?.quality_reasons ?? []).slice(0, 3), ...item.watch_next.slice(0, 2)]),
    empty: "暂无明确催化，需要继续观察订单、涨价、政策、业绩或产业反馈。",
  };
}

function financeSection(): StockChecklistSection {
  return {
    key: "finance",
    icon: "finance",
    title: "财务核查",
    caption: "收入、利润、现金流和资产质量。",
    status: "接入 Tushare",
    tone: "missing",
    lines: [
      "打开核查卡时读取 Tushare income / balancesheet / cashflow / fina_indicator。",
      "第一版只展示财报事实，不接 LLM，也不自动给完整财务结论。",
    ],
    empty: "财务核查待接入。",
  };
}

function marketSection(item: StockEvidenceChainItem): StockChecklistSection {
  const theme = item.primary_theme ?? item.themes[0] ?? null;
  const returnSince = numberValue(item.market_summary.return_since_first_point);
  const drawdown = numberValue(item.market_summary.drawdown_from_selected_high);
  return {
    key: "market",
    icon: "market",
    title: "市场位置",
    caption: "价格、量能、主题强弱是否已经反映。",
    status: item.recognition.state_label,
    tone: item.recognition.state === "confirmed" || item.recognition.state === "just_confirmed" ? "ready" : "watch",
    lines: dedupe([
      `区间收益 ${formatPercent(returnSince, true)}，高点回撤 ${formatPercent(drawdown, true)}。`,
      theme ? `主题内 5 日强弱 ${formatPercent(theme.stock_return_5d, true)}，量能 ${theme.amount_ratio_5d ? `${theme.amount_ratio_5d.toFixed(1)}x` : "-"}。` : "",
      ...item.recognition.reasons.slice(0, 3),
    ]),
    empty: "暂无市场认可依据。",
  };
}

function riskSection(item: StockEvidenceChainItem): StockChecklistSection {
  const missing = [
    item.pricing_risk ? `定价风险：${item.pricing_risk}` : "",
    item.crowding_risk ? `拥挤风险：${item.crowding_risk}` : "",
    ...(item.lifecycle_digest?.risk ?? []),
    ...item.recognition.missing_evidence,
    ...(item.lifecycle_digest?.missing_evidence ?? []),
  ];
  const lines = dedupe(missing).slice(0, 6);
  return {
    key: "risk",
    icon: "risk",
    title: "反证和退出条件",
    caption: "什么情况说明这条逻辑不该继续推进。",
    status: lines.length ? "需跟踪" : "待补反证",
    tone: item.review.tone === "danger" || item.review.tone === "warning" ? "risk" : "watch",
    lines,
    empty: "暂无明确反证，仍需要补公告、财务和后续消息验证。",
  };
}

function stockEvidenceLines(item: StockEvidenceChainItem): string[] {
  return [
    `一句话判断：${item.summary || "暂无"}`,
    `阶段：${item.stage_label}；复盘标签：${item.review.label}`,
    `主题：${item.primary_theme?.theme_name ?? "未确认"}；市场认可：${item.recognition.state_label}`,
    ...item.why.slice(0, 4).map((line) => `阶段依据：${line}`),
    ...item.recognition.reasons.slice(0, 4).map((line) => `认可依据：${line}`),
    ...item.watch_next.slice(0, 3).map((line) => `下一步：${line}`),
  ].filter((line): line is string => Boolean(line));
}

function checklistStatus(item: StockEvidenceChainItem): { label: string; tone: StockChecklistData["tone"] } {
  if (item.review.state === "overheated_review" || item.recognition.state === "overheated") {
    return { label: "已过热", tone: "risk" };
  }
  if (item.review.tone === "danger") {
    return { label: "反证优先", tone: "risk" };
  }
  if (item.review.tone === "success") {
    return { label: "可继续研究", tone: "ready" };
  }
  if (item.review.tone === "warning") {
    return { label: "风险偏高", tone: "risk" };
  }
  return { label: "待补全", tone: "missing" };
}

function firstEvidenceTime(item: StockEvidenceChainItem): string | null {
  return item.evidence_chain[0]?.time ?? null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatConfidence(value?: number | null): string {
  return value === undefined || value === null ? "-" : `${(value * 100).toFixed(0)}%`;
}

function formatPercent(value?: number | null, signed = false): string {
  if (value === undefined || value === null) {
    return "-";
  }
  const text = `${(value * 100).toFixed(1)}%`;
  return signed && value > 0 ? `+${text}` : text;
}

function metricTone(value?: number | null): "up" | "down" | "flat" {
  if (value === undefined || value === null || value === 0) {
    return "flat";
  }
  return value > 0 ? "up" : "down";
}

function volumeRatioText(value: unknown): string | null {
  const ratio = numberValue(value);
  return ratio === null ? null : `${ratio.toFixed(1)}x`;
}

function familyLabel(value: string): string {
  const labels: Record<string, string> = {
    catalyst: "催化",
    research: "研报",
    roadshow: "路演/调研",
    push: "强推",
    price: "价格确认",
  };
  return labels[value] ?? value;
}

function dedupe(items: string[]): string[] {
  return Array.from(new Set(items.filter(Boolean)));
}
