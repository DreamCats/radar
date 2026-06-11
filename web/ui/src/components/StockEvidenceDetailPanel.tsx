import {
  AlertTriangle,
  FileText,
  Gauge,
  MessageSquareText,
  Route,
  TrendingUp,
} from "lucide-react";
import type { ReactNode } from "react";

import type { StockEvidenceChainItem, StockEvidenceMarketPoint } from "../types";
import { ChatLauncher } from "./ChatLauncher";
import { StockEvidenceLifecycleDigest } from "./StockEvidenceLifecycleDigest";
import { StockEvidenceThemeEvidence } from "./StockEvidenceThemeEvidence";

type Props = {
  item: StockEvidenceChainItem | null;
  onOpenChart?: (stock: StockEvidenceChainItem) => void;
};

export function StockEvidenceDetailPanel({ item, onOpenChart }: Props) {
  if (!item) {
    return <aside className="stock-evidence-detail empty">暂无匹配阶段的股票。</aside>;
  }
  return (
    <aside className="stock-evidence-detail">
      <DetailHeader item={item} onOpenChart={onOpenChart} />
      <VerdictCard item={item} />
      <MessageEvidence item={item} />
      <StockEvidenceThemeEvidence item={item} />
      <MarketRecognition item={item} />
      <RiskEvidence item={item} />
      <StockEvidenceLifecycleDigest item={item} />
      <RawEvidenceTimeline item={item} />
    </aside>
  );
}

function DetailHeader({ item, onOpenChart }: { item: StockEvidenceChainItem; onOpenChart?: (stock: StockEvidenceChainItem) => void }) {
  return (
    <header>
      <div>
        <strong>{item.stock_name}</strong>
        <span>{item.ts_code}</span>
      </div>
      <div className="stock-evidence-detail-actions">
        <StagePill item={item} />
        {onOpenChart && (
          <button className="btn btn-sm" type="button" onClick={() => onOpenChart(item)}>
            <TrendingUp size={14} />
            看K线
          </button>
        )}
        <ChatLauncher
          title={`${item.stock_name} 证据链`}
          subtitle={`${item.ts_code} · ${item.stage_label}`}
          surface="个股证据链"
          entityId={item.ts_code}
          buttonLabel="AI"
          buttonClassName="btn btn-primary btn-sm stock-evidence-ai-btn"
          context={[
            { label: "股票", value: item.stock_name },
            { label: "代码", value: item.ts_code },
            { label: "阶段", value: item.stage_label },
            { label: "复盘标签", value: item.review.label },
            { label: "置信", value: formatConfidence(item.confidence) },
            { label: "触发", value: `${item.trigger_count}条 / 去重${item.unique_trigger_count}` },
            { label: "扩散", value: `${item.sender_count}人 / ${item.conversation_count}会话` },
            { label: "主题", value: item.primary_theme?.theme_name ?? "未确认" },
            { label: "市场认可", value: item.recognition.state_label },
            { label: "生命周期", value: item.lifecycle_digest?.one_line ?? "未生成" },
          ]}
          evidence={stockEvidenceChatLines(item)}
          suggestedQuestions={[
            "用人话解释一下这个阶段判断，哪些证据最关键？",
            "结合主题位置、市场证据和消息证据，现在主要风险是什么？",
            "如果继续跟踪，下一步应该盯哪些主题、价格和催化？",
          ]}
        />
      </div>
    </header>
  );
}

function VerdictCard({ item }: { item: StockEvidenceChainItem }) {
  return (
    <section className={`stock-evidence-verdict ${reviewToneClass(item.review.tone)}`}>
      <div className="stock-evidence-review-line">
        <span className={`stock-evidence-review-badge ${item.review.tone}`}>{item.review.label}</span>
        <p>{item.review.headline}</p>
      </div>
      <div className="stock-evidence-verdict-main">
        <span className="stock-evidence-verdict-k">当前结论</span>
        <h3>{item.summary || "暂无一句话判断"}</h3>
      </div>
      <div className="stock-evidence-verdict-pills">
        <span>
          <Route size={14} />
          {item.stage_label}
        </span>
        <span>
          <Gauge size={14} />
          {item.recognition.state_label}
        </span>
        <span>{item.review.action_label}</span>
      </div>
      <DetailList items={item.review.reasons} empty="暂无复盘提示。" compact />
    </section>
  );
}

function MessageEvidence({ item }: { item: StockEvidenceChainItem }) {
  return (
    <EvidenceCard
      icon={<MessageSquareText size={15} />}
      title="为什么值得看"
      question="大家在讲什么，是否有扩散和催化。"
      tone="message"
    >
      <div className="stock-evidence-metric-strip">
        <MetricLite label="去重触发" value={`${item.unique_trigger_count}`} />
        <MetricLite label="发送人" value={`${item.sender_count}`} />
        <MetricLite label="会话" value={`${item.conversation_count}`} />
        <MetricLite label="置信" value={formatConfidence(item.confidence)} />
      </div>
      <FamilyChips counts={item.family_counts} />
      <DetailList items={item.why} empty="暂未形成清晰阶段依据。" />
    </EvidenceCard>
  );
}

function MarketRecognition({ item }: { item: StockEvidenceChainItem }) {
  const theme = item.primary_theme ?? item.themes[0] ?? null;
  const latest = item.market_summary.latest_close;
  const returnSince = numberValue(item.market_summary.return_since_first_point);
  const drawdown = numberValue(item.market_summary.drawdown_from_selected_high);
  return (
    <EvidenceCard
      icon={<TrendingUp size={15} />}
      title="市场认不认"
      question="价格、成交和主题内强弱有没有确认。"
      tone={recognitionToneClass(item.recognition.state)}
    >
      <div className="stock-evidence-market-status">
        <span className={`stock-evidence-recognition-state ${recognitionToneClass(item.recognition.state)}`}>
          <Gauge size={14} />
          {item.recognition.state_label}
        </span>
        {latest !== undefined && <span>最新收盘 {String(latest)}</span>}
      </div>
      <div className="stock-evidence-metric-strip">
        <MetricLite label="区间" value={formatPercent(returnSince, true)} tone={toneClass(returnSince)} />
        <MetricLite label="高点回撤" value={formatPercent(drawdown, true)} tone={toneClass(drawdown)} />
        <MetricLite label="5日" value={formatPercent(theme?.stock_return_5d, true)} tone={toneClass(theme?.stock_return_5d)} />
        <MetricLite label="量能" value={theme?.amount_ratio_5d ? `${theme.amount_ratio_5d.toFixed(1)}x` : "-"} />
      </div>
      <DetailList items={item.recognition.reasons} empty="还没有足够市场认可依据。" />
      <MarketPointStrip points={item.market_points} />
    </EvidenceCard>
  );
}

function RiskEvidence({ item }: { item: StockEvidenceChainItem }) {
  const missing = [...item.recognition.missing_evidence, ...(item.lifecycle_digest?.missing_evidence ?? [])];
  return (
    <EvidenceCard
      icon={<AlertTriangle size={15} />}
      title="风险和缺口"
      question="哪些证据还不够，哪里可能让判断失效。"
      tone="risk"
    >
      <div className="stock-evidence-risk-grid">
        <RiskMini title="定价风险" value={item.pricing_risk} />
        <RiskMini title="拥挤风险" value={item.crowding_risk} />
      </div>
      <DetailList items={dedupe(missing)} empty="暂未识别出明确缺口。" />
    </EvidenceCard>
  );
}

function RawEvidenceTimeline({ item }: { item: StockEvidenceChainItem }) {
  const rows = item.evidence_chain.slice(0, 8);
  return (
    <section className="stock-evidence-card stock-evidence-card-raw">
      <details>
        <summary>
          <span>
            <FileText size={15} />
            原始证据底稿
          </span>
          <small>{rows.length ? `${rows.length} 条关键消息` : "暂无时间线"}</small>
        </summary>
        {rows.length ? (
          <div className="stock-evidence-timeline">
            {rows.map((evidence, index) => (
              <article key={`${evidence.message_id ?? index}-${index}`}>
                <time>{evidence.time ?? "-"}</time>
                <strong>{evidence.type ?? "证据"}</strong>
                <p>{evidence.evidence ?? evidence.raw_content ?? "无摘要"}</p>
                <span>
                  {evidence.sender ?? "-"}
                  {evidence.group_name ? ` · ${evidence.group_name}` : ""}
                </span>
              </article>
            ))}
          </div>
        ) : (
          <p className="stock-evidence-empty">LLM 未返回关键证据时间线。</p>
        )}
      </details>
    </section>
  );
}

function EvidenceCard(props: { icon: ReactNode; title: string; question: string; tone: string; children: ReactNode }) {
  return (
    <section className={`stock-evidence-card stock-evidence-card-${props.tone}`}>
      <div className="stock-evidence-card-head">
        <span>{props.icon}</span>
        <div>
          <strong>{props.title}</strong>
          <small>{props.question}</small>
        </div>
      </div>
      {props.children}
    </section>
  );
}

function MetricLite(props: { label: string; value: string; tone?: string }) {
  return (
    <article>
      <span>{props.label}</span>
      <strong className={props.tone}>{props.value}</strong>
    </article>
  );
}

function FamilyChips({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts).filter(([, count]) => count > 0);
  if (!entries.length) {
    return <p className="stock-evidence-empty">暂无明确催化类型。</p>;
  }
  return (
    <div className="stock-evidence-family-chips">
      {entries.slice(0, 6).map(([family, count]) => (
        <span key={family}>
          {familyLabel(family)}
          <small>{count}</small>
        </span>
      ))}
    </div>
  );
}

function DetailList({ items, empty, compact = false }: { items: string[]; empty: string; compact?: boolean }) {
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

function MarketPointStrip({ points }: { points: StockEvidenceMarketPoint[] }) {
  const rows = points.slice(-4);
  if (!rows.length) {
    return <p className="stock-evidence-empty">暂无市场证据点。</p>;
  }
  return (
    <div className="stock-evidence-market-points">
      {rows.map((point) => (
        <article key={`${point.trade_date}-${point.tag ?? ""}`}>
          <time>{point.trade_date}</time>
          <strong>{point.close ?? "-"}</strong>
          <span className={toneClass(point.pct_chg)}>{formatPercentPoint(point.pct_chg, true)}</span>
          <small>量能 {point.amount_ratio_5d ? `${point.amount_ratio_5d.toFixed(1)}x` : "-"}</small>
        </article>
      ))}
    </div>
  );
}

function RiskMini({ title, value }: { title: string; value?: string | null }) {
  return (
    <article>
      <strong>{title}</strong>
      <p>{value || "证据不足"}</p>
    </article>
  );
}

function stockEvidenceChatLines(item: StockEvidenceChainItem): string[] {
  return [
    `一句话判断：${item.summary || "暂无"}`,
    `阶段：${item.stage_label}；置信度：${formatConfidence(item.confidence)}`,
    `复盘标签：${item.review.label}；${item.review.headline}`,
    `主题：${item.primary_theme?.theme_name ?? "未确认"}；市场认可：${item.recognition.state_label}`,
    item.lifecycle_digest ? `生命周期摘要：${item.lifecycle_digest.one_line}` : "",
    ...(item.lifecycle_digest?.stage_reason ?? []).slice(0, 4).map((line) => `生命周期依据：${line}`),
    ...(item.lifecycle_digest?.missing_evidence ?? []).slice(0, 4).map((line) => `生命周期缺口：${line}`),
    ...item.recognition.reasons.slice(0, 4).map((line) => `认可依据：${line}`),
    ...item.recognition.missing_evidence.slice(0, 4).map((line) => `证据缺口：${line}`),
    ...item.why.slice(0, 4).map((line) => `阶段依据：${line}`),
    ...item.evidence_chain.slice(0, 6).map((evidence) => {
      const source = [evidence.sender, evidence.group_name].filter(Boolean).join(" · ");
      return `证据：${evidence.time ?? "-"} ${evidence.type ?? "证据"} ${evidence.evidence ?? evidence.raw_content ?? "无摘要"}${source ? `（${source}）` : ""}`;
    }),
    ...item.market_points.slice(-4).map((point) => `市场：${point.trade_date} 收盘 ${point.close ?? "-"} 涨跌 ${formatPercentPoint(point.pct_chg, true)} 量能 ${point.amount_ratio_5d ? `${point.amount_ratio_5d.toFixed(1)}x` : "-"}`),
    item.pricing_risk ? `定价风险：${item.pricing_risk}` : "",
    item.crowding_risk ? `拥挤风险：${item.crowding_risk}` : "",
    ...item.watch_next.slice(0, 4).map((line) => `下一步：${line}`),
  ].filter((line): line is string => Boolean(line));
}

function StagePill({ item }: { item: StockEvidenceChainItem }) {
  return <span className={`stock-evidence-stage stock-evidence-stage-${item.stage}`}>{item.stage_label}</span>;
}

function formatConfidence(value?: number | null): string {
  return value === undefined || value === null ? "-" : `${(value * 100).toFixed(0)}%`;
}

function formatPercent(value?: number | null, signed = false): string {
  if (value === undefined || value === null) {
    return "-";
  }
  const normalized = Math.abs(value) > 1 ? value : value * 100;
  const text = `${normalized.toFixed(1)}%`;
  return signed && normalized > 0 ? `+${text}` : text;
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
  if (state === "overheated" || state === "pullback_after_pricing") {
    return "risk";
  }
  if (state === "rejected") {
    return "rejected";
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

function familyLabel(value: string): string {
  const labels: Record<string, string> = {
    catalyst: "催化",
    research: "研报",
    roadshow: "路演",
    push: "强推",
    price: "价格",
  };
  return labels[value] ?? value;
}

function dedupe(items: string[]): string[] {
  return Array.from(new Set(items.filter(Boolean)));
}
