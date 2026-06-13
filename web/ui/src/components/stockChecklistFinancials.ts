import type { StockEvidenceFinancials } from "../types";
import type { StockChecklistData, StockChecklistSection } from "./StockChecklistCard";

export function checklistWithFinancials(
  checklist: StockChecklistData,
  financials: StockEvidenceFinancials | null,
  loading: boolean,
  error: string | null,
): StockChecklistData {
  return {
    ...checklist,
    sections: checklist.sections.map((section) =>
      section.key === "finance" ? financialSectionWithTushare(section, financials, loading, error) : section,
    ),
  };
}

function financialSectionWithTushare(
  base: StockChecklistSection,
  financials: StockEvidenceFinancials | null,
  loading: boolean,
  error: string | null,
): StockChecklistSection {
  if (loading && !financials) {
    return {
      ...base,
      status: "读取 Tushare",
      tone: "watch",
      lines: ["正在读取 Tushare 财报缓存和最近报告期。"],
      empty: "正在读取财务数据。",
    };
  }
  if (error) {
    return {
      ...base,
      status: "读取失败",
      tone: "missing",
      lines: [`Tushare 财务数据读取失败：${error}`, "财务核查暂不输出完整结论。"],
      empty: "财务数据读取失败。",
    };
  }
  if (!financials) {
    return base;
  }
  const metricLine = financials.metrics.map((metric) => `${metric.label} ${metric.value}`).join("；");
  return {
    ...base,
    status: financials.status,
    tone: financials.tone,
    lines: dedupe([metricLine, ...financials.lines, financials.missing_reason ?? ""]),
    empty: financials.missing_reason ?? "Tushare 暂无可展示财务数据。",
  };
}

function dedupe(items: string[]): string[] {
  return Array.from(new Set(items.filter(Boolean)));
}
