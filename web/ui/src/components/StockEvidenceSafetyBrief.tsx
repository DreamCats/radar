import { AlertCircle, CheckCircle2, HelpCircle, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

import type { StockEvidenceChainItem, StockEvidenceMarketPoint, StockEvidenceThemeContext } from "../types";

type BriefLine = {
  label: string;
  value: string;
  tone?: "good" | "watch" | "risk" | "muted";
};

export function StockEvidenceSafetyBrief({ item, theme }: { item: StockEvidenceChainItem; theme: StockEvidenceThemeContext | null }) {
  const latestPoint = item.market_points[item.market_points.length - 1];
  const alignment = alignmentBrief(item);
  return (
    <section className="stock-evidence-safety-brief">
      <div className="stock-evidence-safety-head">
        <span>
          <ShieldCheck size={15} />
        </span>
        <div>
          <strong>系统只敢这么说</strong>
          <p>把事实、推断和不确定分开看，避免把系统判断当成事实。</p>
        </div>
      </div>
      <div className="stock-evidence-safety-grid">
        <SafetyCard
          icon={<CheckCircle2 size={14} />}
          title="事实"
          tone="good"
          lines={factLines(item, theme, latestPoint)}
        />
        <SafetyCard icon={<HelpCircle size={14} />} title="保守推断" tone={alignment.tone} lines={[alignment, inferenceLine(item)]} />
        <SafetyCard icon={<AlertCircle size={14} />} title="不确定" tone="risk" lines={uncertaintyLines(item, theme)} />
      </div>
      <div className="stock-evidence-change-rules">
        <strong>后面什么会改变判断？</strong>
        <ul>
          {changeRuleLines(item).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function SafetyCard({ icon, title, tone, lines }: { icon: ReactNode; title: string; tone: BriefLine["tone"]; lines: BriefLine[] }) {
  return (
    <article className={`stock-evidence-safety-card ${tone ?? "muted"}`}>
      <h4>
        {icon}
        {title}
      </h4>
      <div>
        {lines.map((line) => (
          <p key={`${line.label}-${line.value}`}>
            <span>{line.label}</span>
            <strong className={line.tone}>{line.value}</strong>
          </p>
        ))}
      </div>
    </article>
  );
}

function factLines(item: StockEvidenceChainItem, theme: StockEvidenceThemeContext | null, latestPoint: StockEvidenceMarketPoint | undefined): BriefLine[] {
  return [
    {
      label: "消息",
      value: `${item.unique_trigger_count} 条去重，${item.sender_count} 人 / ${item.conversation_count} 会话`,
      tone: item.unique_trigger_count >= 3 ? "good" : "watch",
    },
    {
      label: "主线",
      value: theme ? `${theme.theme_name} · ${theme.quality_label}` : "未确认",
      tone: theme && theme.quality_score >= 0.72 ? "good" : "watch",
    },
    {
      label: "市场",
      value: latestPoint ? `最新 ${formatPercentPoint(latestPoint.pct_chg, true)}，量能 ${formatAmountRatio(latestPoint.amount_ratio_5d)}` : "暂无市场点",
      tone: latestPoint?.pct_chg && latestPoint.pct_chg > 0 ? "good" : "watch",
    },
  ];
}

function alignmentBrief(item: StockEvidenceChainItem): BriefLine {
  const firstMessage = firstMessageDate(item);
  const firstMarket = firstMarketDate(item);
  const returnSince = numberValue(item.market_summary.return_since_first_point);
  if (!firstMessage || !firstMarket) {
    return { label: "对齐", value: "消息或市场时间点不足，先不判断领先关系", tone: "muted" };
  }
  const gap = daysBetween(firstMessage, firstMarket);
  if (gap > 0 && positiveReturn(returnSince)) {
    return { label: "对齐", value: "消息先出现，后续市场有反馈，但仍需看承接", tone: "good" };
  }
  if (gap < 0) {
    return { label: "对齐", value: "价格证据早于入选消息，不能把消息当成首因", tone: "watch" };
  }
  if (Math.abs(gap) === 0) {
    return { label: "对齐", value: "消息和价格同日出现，无法证明谁领先", tone: "watch" };
  }
  if (!positiveReturn(returnSince)) {
    return { label: "对齐", value: "消息出现后市场反馈偏弱，先按待验证处理", tone: "risk" };
  }
  return { label: "对齐", value: "时间关系可参考，但证据还不够稳定", tone: "watch" };
}

function inferenceLine(item: StockEvidenceChainItem): BriefLine {
  if (item.recognition.state === "confirmed" || item.recognition.state === "just_confirmed") {
    return { label: "判断", value: "可以继续研究验证，不等于已经安全", tone: "good" };
  }
  if (item.recognition.state === "just_started") {
    return { label: "判断", value: "刚有异动，还不能证明趋势成立", tone: "watch" };
  }
  if (item.recognition.state === "overheated") {
    return { label: "判断", value: "市场反映已经明显，后面重点看分歧和承接", tone: "risk" };
  }
  if (item.recognition.state === "rejected") {
    return { label: "判断", value: "消息热度暂时没有被市场确认", tone: "risk" };
  }
  return { label: "判断", value: "证据还不完整，系统不应该强判", tone: "muted" };
}

function uncertaintyLines(item: StockEvidenceChainItem, theme: StockEvidenceThemeContext | null): BriefLine[] {
  const missing = [
    ...(theme?.missing_evidence ?? []),
    ...item.recognition.missing_evidence,
    ...(item.lifecycle_digest?.missing_evidence ?? []),
  ].filter(Boolean);
  const lines = missing.slice(0, 2).map((value, index) => ({
    label: index === 0 ? "缺口" : "还缺",
    value,
    tone: "risk" as const,
  }));
  if (lines.length) {
    return lines;
  }
  return [
    { label: "缺口", value: "没有明显缺口，但仍要看后续 2-3 个交易日是否承接", tone: "watch" },
    { label: "反证", value: "如果只剩重复消息、价格不跟，就要降级", tone: "watch" },
  ];
}

function changeRuleLines(item: StockEvidenceChainItem): string[] {
  const watch = item.watch_next.slice(0, 2);
  return [
    watch[0] ? `增强：${watch[0]}` : "增强：后续 2-3 个交易日继续放量承接，并出现新的硬催化。",
    watch[1] ? `继续看：${watch[1]}` : "继续看：个股是否仍然跑赢主题，而不是只靠群内重复扩散。",
    "降级：消息继续扩散但价格缩量回落、放量滞涨，或主题/公司证据补不上。",
  ];
}

function firstMessageDate(item: StockEvidenceChainItem): Date | null {
  const dates = item.evidence_chain.map((evidence) => parseMessageDate(evidence.time)).filter((date): date is Date => Boolean(date));
  return dates.sort((a, b) => a.getTime() - b.getTime())[0] ?? null;
}

function firstMarketDate(item: StockEvidenceChainItem): Date | null {
  const dates = item.market_points.map((point) => parseTradeDate(point.trade_date)).filter((date): date is Date => Boolean(date));
  return dates.sort((a, b) => a.getTime() - b.getTime())[0] ?? null;
}

function parseMessageDate(value?: string | null): Date | null {
  if (!value) {
    return null;
  }
  const dateText = value.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? value.match(/\d{8}/)?.[0];
  return dateText ? parseTradeDate(dateText) : null;
}

function parseTradeDate(value: string): Date | null {
  const normalized = /^\d{8}$/.test(value) ? `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6)}` : value.slice(0, 10);
  const time = Date.parse(`${normalized}T00:00:00`);
  return Number.isNaN(time) ? null : new Date(time);
}

function daysBetween(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

function positiveReturn(value: number | null): boolean {
  if (value === null) {
    return false;
  }
  return Math.abs(value) > 1 ? value > 0 : value > 0.02;
}

function formatAmountRatio(value?: number | null): string {
  return value ? `${value.toFixed(1)}x` : "-";
}

function formatPercentPoint(value?: number | null, signed = false): string {
  if (value === undefined || value === null) {
    return "-";
  }
  const text = `${value.toFixed(1)}%`;
  return signed && value > 0 ? `+${text}` : text;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
