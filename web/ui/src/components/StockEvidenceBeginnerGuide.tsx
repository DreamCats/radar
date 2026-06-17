import { AlertTriangle, Building2, Gauge, MessageSquareText, Route, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";

import type { StockEvidenceChainItem, StockEvidenceMarketPoint, StockEvidenceThemeContext } from "../types";
import { StockEvidenceAlignedTimeline } from "./StockEvidenceAlignedTimeline";
import { StockEvidenceCurrentTrigger } from "./StockEvidenceCurrentTrigger";
import { StockEvidenceSafetyBrief } from "./StockEvidenceSafetyBrief";

export function StockEvidenceBeginnerGuide({ item }: { item: StockEvidenceChainItem }) {
  const theme = item.primary_theme ?? item.themes[0] ?? null;
  const latestPoint = item.market_points[item.market_points.length - 1];
  return (
    <div className="stock-evidence-beginner">
      <section className={`stock-evidence-beginner-verdict ${reviewToneClass(item.review.tone)}`}>
        <div>
          <span className={`stock-evidence-review-badge ${item.review.tone}`}>{item.review.label}</span>
          <span className={`stock-evidence-recognition-state ${recognitionToneClass(item.recognition.state)}`}>
            <Gauge size={14} />
            {item.recognition.state_label}
          </span>
        </div>
        <h3>{beginnerHeadline(item)}</h3>
        <p>{beginnerExplanation(item)}</p>
        <div className="stock-evidence-beginner-pills">
          <span>{item.stage_label}</span>
          <span>{theme?.theme_name ?? "主线未确认"}</span>
          <span>{item.unique_trigger_count} 条去重消息</span>
        </div>
      </section>
      <StockEvidenceCurrentTrigger item={item} />
      <StockEvidenceSafetyBrief item={item} theme={theme} />

      <BeginnerStepCard
        index="01"
        icon={<Building2 size={15} />}
        title="先搞懂它是谁"
        question="别先看推荐词，先看它到底挂在哪条主线。"
      >
        <p className="stock-evidence-plain-line">{companyLine(theme)}</p>
        <MiniFacts
          items={[
            { label: "主线", value: theme?.theme_name ?? "未确认" },
            { label: "质量", value: theme?.quality_label ?? "待补" },
            { label: "来源", value: theme ? `${theme.source_count} 源` : "-" },
            { label: "角色", value: roleLabel(theme?.role) },
          ]}
        />
        <PlainList items={themeReasons(theme)} empty="暂无稳定主题依据，先按个股线索观察。" />
      </BeginnerStepCard>

      <BeginnerStepCard
        index="02"
        icon={<MessageSquareText size={15} />}
        title="历史证据在说什么"
        question="这里看的是过去一段时间的逻辑，不等于本次新增已经被验证。"
      >
        <p className="stock-evidence-plain-line">{messageLine(item)}</p>
        <EvidenceTypeStrip item={item} />
        <PlainList items={item.why.slice(0, 3)} empty="暂未形成清晰消息逻辑。" />
      </BeginnerStepCard>

      <BeginnerStepCard
        index="03"
        icon={<TrendingUp size={15} />}
        title="市场有没有认"
        question="先确认行情验证的是历史证据，还是这次新增触发。"
      >
        <p className="stock-evidence-plain-line">{marketLine(item, latestPoint)}</p>
        <MiniFacts
          items={[
            { label: marketReturnLabel(item), value: formatPercent(numberValue(item.market_summary.return_since_first_point), true), tone: toneClass(numberValue(item.market_summary.return_since_first_point)) },
            { label: "高点回撤", value: formatPercent(numberValue(item.market_summary.drawdown_from_selected_high), true), tone: toneClass(numberValue(item.market_summary.drawdown_from_selected_high)) },
            { label: "最新量能", value: latestPoint?.amount_ratio_5d ? `${latestPoint.amount_ratio_5d.toFixed(1)}x` : "-" },
            { label: "主题5日", value: formatPercent(theme?.stock_return_5d, true), tone: toneClass(theme?.stock_return_5d) },
          ]}
        />
        <PlainList items={item.recognition.reasons.slice(0, 3)} empty="还没有足够市场认可依据。" />
      </BeginnerStepCard>

      <BeginnerStepCard
        index="04"
        icon={<Route size={15} />}
        title="消息和市场对得上吗"
        question="按日期对照：本次触发、历史证据和市场点分开看。"
      >
        <StockEvidenceAlignedTimeline item={item} />
      </BeginnerStepCard>

      <BeginnerStepCard
        index="05"
        icon={<AlertTriangle size={15} />}
        title="下一步只看什么"
        question="不继续堆消息，只盯会改变判断的证据。"
      >
        <PlainList items={nextWatchItems(item)} empty="暂无明确观察点，先补主题、行情和反证。" />
        <div className="stock-evidence-fail-box">
          <strong>什么情况说明要降温？</strong>
          <PlainList items={failureItems(item)} empty="暂未识别出明确反证。" compact />
        </div>
      </BeginnerStepCard>
    </div>
  );
}

function BeginnerStepCard({
  index,
  icon,
  title,
  question,
  children,
}: {
  index: string;
  icon: ReactNode;
  title: string;
  question: string;
  children: ReactNode;
}) {
  return (
    <section className="stock-evidence-card stock-evidence-beginner-card">
      <div className="stock-evidence-beginner-head">
        <span>{icon}</span>
        <div>
          <small>{index}</small>
          <strong>{title}</strong>
          <em>{question}</em>
        </div>
      </div>
      {children}
    </section>
  );
}

function EvidenceTypeStrip({ item }: { item: StockEvidenceChainItem }) {
  const catalyst = item.family_counts.catalyst ?? 0;
  const diffusion = (item.family_counts.research ?? 0) + (item.family_counts.roadshow ?? 0) + (item.family_counts.push ?? 0);
  const price = item.family_counts.price ?? 0;
  return (
    <div className="stock-evidence-type-strip">
      <span className={catalyst > 0 ? "strong" : ""}>硬催化 {catalyst}</span>
      <span className={diffusion > 0 ? "medium" : ""}>扩散证据 {diffusion}</span>
      <span className={price > 0 ? "price" : ""}>价格异动 {price}</span>
    </div>
  );
}

function MiniFacts({ items }: { items: { label: string; value: string; tone?: string }[] }) {
  return (
    <div className="stock-evidence-mini-facts">
      {items.map((item) => (
        <article key={item.label}>
          <span>{item.label}</span>
          <strong className={item.tone}>{item.value}</strong>
        </article>
      ))}
    </div>
  );
}

function PlainList({ items, empty, compact = false }: { items: string[]; empty: string; compact?: boolean }) {
  return items.length ? (
    <ul className={compact ? "stock-evidence-detail-list compact" : "stock-evidence-detail-list"}>
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  ) : (
    <p className="stock-evidence-empty">{empty}</p>
  );
}

function beginnerHeadline(item: StockEvidenceChainItem): string {
  if (item.recognition.state === "confirmed" || item.recognition.state === "just_confirmed") {
    return "消息、主线和市场反馈基本对上，适合继续研究验证。";
  }
  if (item.recognition.state === "just_started") {
    return "价格和量能刚开始动，还不能直接当成趋势。";
  }
  if (item.recognition.state === "overheated") {
    return "市场已经明显反映，先判断是强趋势还是高位分歧。";
  }
  if (item.recognition.state === "pullback_after_pricing") {
    return "曾经被市场定价过，现在重点看回撤有没有破坏逻辑。";
  }
  if (item.recognition.state === "rejected") {
    return "消息有热度，但价格或主线没有配合。";
  }
  return "证据还不完整，先补主线和市场验证。";
}

function beginnerExplanation(item: StockEvidenceChainItem): string {
  if (item.summary) {
    return item.summary;
  }
  return item.review.headline || "先按证据链核查，暂不输出买卖结论。";
}

function companyLine(theme: StockEvidenceThemeContext | null): string {
  if (!theme) {
    return "系统还没有找到稳定主线。小白先不要把它当作板块核心，要先补公司主营、客户和产业链位置。";
  }
  if (theme.quality_score >= 0.72) {
    return `先按「${theme.theme_name}」主线理解，系统认为它是${theme.quality_label}。下一步仍要确认主营业务和催化是否真的传到业绩。`;
  }
  return `它最接近「${theme.theme_name}」，但主题质量是${theme.quality_label}。先当候选线索看，不要直接当主线核心。`;
}

function themeReasons(theme: StockEvidenceThemeContext | null): string[] {
  if (!theme) {
    return [];
  }
  return [...theme.quality_reasons, ...theme.quality_warnings, ...theme.missing_evidence].slice(0, 4);
}

function messageLine(item: StockEvidenceChainItem): string {
  const catalyst = item.family_counts.catalyst ?? 0;
  const roadshow = item.family_counts.roadshow ?? 0;
  const push = item.family_counts.push ?? 0;
  if (catalyst > 0) {
    return `历史证据里有 ${catalyst} 条催化证据，不只是泛泛推荐；但还要单独看本次触发有没有新增信息。`;
  }
  if (roadshow + push > 0) {
    return "历史消息主要来自路演或强推，说明关注度在扩散，但还需要硬催化和市场承接。";
  }
  return "目前更像普通关注线索，需要继续补订单、涨价、业绩、政策或产业反馈。";
}

function marketLine(item: StockEvidenceChainItem, latestPoint: StockEvidenceMarketPoint | undefined): string {
  const validation = item.market_validation;
  if (validation?.status === "pending_current_trigger") {
    return validation.note;
  }
  if (validation?.status === "same_day_current_trigger") {
    return validation.note;
  }
  const returnSince = numberValue(item.market_summary.return_since_first_point);
  const drawdown = numberValue(item.market_summary.drawdown_from_selected_high);
  const amount = latestPoint?.amount_ratio_5d;
  if (item.recognition.state === "rejected") {
    return `市场暂时不认：${marketReturnLabel(item)}收益 ${formatPercent(returnSince, true)}，高点回撤 ${formatPercent(drawdown, true)}。放量也要先判断是确认还是分歧。`;
  }
  if (item.recognition.state === "overheated") {
    return `市场已经充分反映：${marketReturnLabel(item)}收益 ${formatPercent(returnSince, true)}。现在要看承接和高位分歧，不是继续堆消息。`;
  }
  if (item.recognition.state === "just_started" || item.recognition.state === "just_confirmed") {
    return `市场开始给反馈：最新量能 ${amount ? `${amount.toFixed(1)}x` : "-"}，但还要看后面 2-3 个交易日是否承接。`;
  }
  if (item.recognition.state === "confirmed") {
    return `市场已经比较配合：涨幅、回撤和量能能互相支持。下一步看逻辑是否继续增强。`;
  }
  return "市场证据还不够完整，先不要只凭消息热度下判断。";
}

function marketReturnLabel(item: StockEvidenceChainItem): string {
  const date = tradeDateLabel(item.market_summary.first_trade_date);
  return date ? `${date}后` : "首点后";
}

function tradeDateLabel(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const compact = value.match(/^(\d{4})(\d{2})(\d{2})$/);
  if (compact) {
    return `${Number(compact[2])}/${Number(compact[3])}`;
  }
  const dashed = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (dashed) {
    return `${Number(dashed[2])}/${Number(dashed[3])}`;
  }
  return null;
}

function nextWatchItems(item: StockEvidenceChainItem): string[] {
  if (item.watch_next.length) {
    return item.watch_next.slice(0, 4);
  }
  return [
    "看后续 2-3 个交易日是否继续放量承接。",
    "看有没有新的硬催化，而不是重复同一类推荐。",
    "看主题内是否继续领先，还是开始掉队。",
  ];
}

function failureItems(item: StockEvidenceChainItem): string[] {
  return [
    item.pricing_risk ? `定价风险：${item.pricing_risk}` : "",
    item.crowding_risk ? `拥挤风险：${item.crowding_risk}` : "",
    ...item.recognition.missing_evidence,
    ...(item.lifecycle_digest?.missing_evidence ?? []),
  ]
    .filter(Boolean)
    .slice(0, 5);
}

function roleLabel(role?: string | null): string {
  if (role === "core") {
    return "核心";
  }
  if (role === "elastic") {
    return "弹性";
  }
  return "待确认";
}

function formatPercent(value?: number | null, signed = false): string {
  if (value === undefined || value === null) {
    return "-";
  }
  const normalized = Math.abs(value) > 1 ? value : value * 100;
  const text = `${normalized.toFixed(1)}%`;
  return signed && normalized > 0 ? `+${text}` : text;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function toneClass(value?: number | null): string {
  if (value === undefined || value === null || value === 0) {
    return "return-flat";
  }
  return value > 0 ? "return-up" : "return-down";
}

function recognitionToneClass(state: string): string {
  if (state === "confirmed" || state === "just_confirmed") {
    return "confirmed";
  }
  if (state === "rejected") {
    return "rejected";
  }
  if (state === "just_started" || state === "overheated" || state === "pullback_after_pricing") {
    return "risk";
  }
  return "unknown";
}

function reviewToneClass(tone: StockEvidenceChainItem["review"]["tone"]): string {
  if (tone === "success") {
    return "confirmed";
  }
  if (tone === "danger") {
    return "rejected";
  }
  if (tone === "warning") {
    return "risk";
  }
  return "unknown";
}
