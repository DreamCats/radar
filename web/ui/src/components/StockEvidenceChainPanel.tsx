import { AlertTriangle, CheckCircle2, CircleAlert, Clock3, Gauge, MessageSquareText, Network, TrendingUp, Users } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { formatTime } from "../lib/datetime";
import type { StockEvidenceChainDashboard, StockEvidenceChainItem, StockEvidenceMarketPoint } from "../types";
import { ChatLauncher } from "./ChatLauncher";
import { PanelTitle } from "./PanelTitle";

const STAGE_ORDER = ["线索期", "种子期", "论证期", "扩散期", "定价期", "拥挤期"];

type Props = {
  data: StockEvidenceChainDashboard | null;
  error: string | null;
  onSelectStock?: (stock: StockEvidenceChainItem) => void;
};

export function StockEvidenceChainPanel({ data, error, onSelectStock }: Props) {
  const items = data?.items ?? [];
  const [stage, setStage] = useState("全部");
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const filteredItems = stage === "全部" ? items : items.filter((item) => item.stage_label === stage);
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

  return (
    <div className="stock-evidence-workbench">
      <div className="statbar metric-grid">
        <Metric label="候选股票" value={data?.item_count ?? 0} detail="最新证据链判断" />
        <Metric label="观察池" value={earlyCount(items)} detail="线索 / 种子 / 论证" />
        <Metric label="正在定价" value={stageCount(data, "定价期")} detail="需要结合价格风险" />
        <Metric label="拥挤风险" value={stageCount(data, "拥挤期")} detail="优先复盘不追高" />
      </div>
      {error && <p className="error-line">{error}</p>}
      {!error && !items.length && <p className="empty-line">暂无个股证据链判断。先在作业中心运行「个股证据链」。</p>}
      {!!items.length && (
        <section className="panel stock-evidence-panel">
          <PanelTitle title="个股证据链" meta={windowMeta(data)} titleExtra={<SortRuleHelp />} />
          <div className="stock-evidence-stage-tabs" role="tablist" aria-label="证据链阶段">
            {stageTabs.map((label) => (
              <button className={stage === label ? "active" : ""} type="button" key={label} onClick={() => setStage(label)}>
                {label}
                <span>{label === "全部" ? items.length : data?.stage_counts[label]}</span>
              </button>
            ))}
          </div>
          <div className="stock-evidence-layout">
            <div className="stock-evidence-list" aria-label="股票候选">
              {filteredItems.map((item) => (
                <StockEvidenceRow
                  item={item}
                  selected={item.ts_code === selected?.ts_code}
                  key={item.ts_code}
                  onClick={() => setSelectedCode(item.ts_code)}
                  onOpenChart={onSelectStock}
                />
              ))}
            </div>
            <StockEvidenceDetail item={selected} onOpenChart={onSelectStock} />
          </div>
        </section>
      )}
    </div>
  );
}

function SortRuleHelp() {
  return (
    <span className="stock-evidence-sort-help">
      <button type="button" aria-label="查看排序规则">
        <CircleAlert size={14} />
      </button>
      <span className="stock-evidence-sort-tooltip" role="tooltip">
        <strong>默认按可行动优先级排序</strong>
        <span>先看阶段：种子 / 论证 / 线索 / 早扩散优先。</span>
        <span>再看证据：催化、调研、研报、推票、市场验证。</span>
        <span>然后看新增变化、多人多群扩散、置信度。</span>
        <span>涨幅过大或拥挤期会后置，主要用于复盘避坑。</span>
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
          <StagePill item={item} />
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

function StockEvidenceDetail({
  item,
  onOpenChart,
}: {
  item: StockEvidenceChainItem | null;
  onOpenChart?: (stock: StockEvidenceChainItem) => void;
}) {
  if (!item) {
    return <aside className="stock-evidence-detail empty">暂无匹配阶段的股票。</aside>;
  }
  return (
    <aside className="stock-evidence-detail">
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
              { label: "置信", value: formatConfidence(item.confidence) },
              { label: "触发", value: `${item.trigger_count}条 / 去重${item.unique_trigger_count}` },
              { label: "扩散", value: `${item.sender_count}人 / ${item.conversation_count}会话` },
              { label: "主题", value: item.primary_theme?.theme_name ?? "未确认" },
              { label: "市场认可", value: item.recognition.state_label },
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
      <p className="stock-evidence-summary">{item.summary || "暂无一句话判断"}</p>
      <div className="stock-evidence-facts">
        <Fact icon={<MessageSquareText size={14} />} label="触发" value={`${item.trigger_count}条 / 去重${item.unique_trigger_count}`} />
        <Fact icon={<Users size={14} />} label="扩散" value={`${item.sender_count}人 / ${item.conversation_count}会话`} />
        <Fact icon={<CheckCircle2 size={14} />} label="置信" value={formatConfidence(item.confidence)} />
        <Fact icon={<Clock3 size={14} />} label="证据" value={`${item.evidence_count}条`} />
      </div>
      <ThemeRecognition item={item} />
      <DetailSection title="为什么是这个阶段" items={item.why} />
      <EvidenceTimeline item={item} />
      <MarketEvidence item={item} />
      <RiskBlock title="定价风险" value={item.pricing_risk} />
      <RiskBlock title="拥挤风险" value={item.crowding_risk} />
      <DetailSection title="下一步盯什么" items={item.watch_next} />
    </aside>
  );
}

function stockEvidenceChatLines(item: StockEvidenceChainItem): string[] {
  return [
    `一句话判断：${item.summary || "暂无"}`,
    `阶段：${item.stage_label}；置信度：${formatConfidence(item.confidence)}`,
    `主题：${item.primary_theme?.theme_name ?? "未确认"}；市场认可：${item.recognition.state_label}`,
    ...item.recognition.reasons.slice(0, 4).map((line) => `认可依据：${line}`),
    ...item.recognition.missing_evidence.slice(0, 4).map((line) => `证据缺口：${line}`),
    ...item.why.slice(0, 4).map((line) => `阶段依据：${line}`),
    ...item.evidence_chain.slice(0, 6).map((evidence) => {
      const source = [evidence.sender, evidence.group_name].filter(Boolean).join(" · ");
      return `证据：${evidence.time ?? "-"} ${evidence.type ?? "证据"} ${evidence.evidence ?? evidence.raw_content ?? "无摘要"}${source ? `（${source}）` : ""}`;
    }),
    ...item.market_points.slice(-4).map((point) => `市场：${point.trade_date} 收盘 ${point.close ?? "-"} 涨跌 ${formatPercent(point.pct_chg, true)} 量能 ${point.amount_ratio_5d ? `${point.amount_ratio_5d.toFixed(1)}x` : "-"}`),
    item.pricing_risk ? `定价风险：${item.pricing_risk}` : "",
    item.crowding_risk ? `拥挤风险：${item.crowding_risk}` : "",
    ...item.watch_next.slice(0, 4).map((line) => `下一步：${line}`),
  ].filter((line): line is string => Boolean(line));
}

function ThemeRecognition({ item }: { item: StockEvidenceChainItem }) {
  const theme = item.primary_theme ?? item.themes[0] ?? null;
  return (
    <section className="stock-evidence-recognition">
      <div className="stock-evidence-recognition-head">
        <span>
          <Network size={14} />
          主题位置
        </span>
        <span className={`stock-evidence-recognition-state ${recognitionToneClass(item.recognition.state)}`}>
          <Gauge size={14} />
          {item.recognition.state_label}
        </span>
      </div>
      {theme ? (
        <div className="stock-evidence-theme-primary">
          <strong>{theme.theme_name}</strong>
          <span>{typeLabel(theme.theme_type)}</span>
          <span>{roleLabel(theme.role)}</span>
          <span>{theme.source_count} 源</span>
          {theme.return_rank_5d && theme.member_count && <span>5日强弱 {theme.return_rank_5d}/{theme.member_count}</span>}
        </div>
      ) : (
        <p className="stock-evidence-empty">暂无自动主题归属。</p>
      )}
      {!!item.themes.length && (
        <div className="stock-evidence-theme-list">
          {item.themes.slice(0, 5).map((candidate) => (
            <span key={candidate.theme_id}>
              {candidate.theme_name}
              <small>{roleLabel(candidate.role)}</small>
            </span>
          ))}
        </div>
      )}
      <div className="stock-evidence-recognition-grid">
        <MetricLite label="5日涨幅" value={formatPercent(theme?.stock_return_5d, true)} />
        <MetricLite label="20日涨幅" value={formatPercent(theme?.stock_return_20d, true)} />
        <MetricLite label="量能" value={theme?.amount_ratio_5d ? `${theme.amount_ratio_5d.toFixed(1)}x` : "-"} />
        <MetricLite label="覆盖" value={coverageText(theme)} />
      </div>
      <DetailSection title="认可依据" items={item.recognition.reasons} />
      <DetailSection title="证据缺口" items={item.recognition.missing_evidence} />
    </section>
  );
}

function EvidenceTimeline({ item }: { item: StockEvidenceChainItem }) {
  const rows = item.evidence_chain.slice(0, 8);
  return (
    <section className="stock-evidence-section">
      <div className="stock-evidence-section-title">证据时间线</div>
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
    </section>
  );
}

function MarketEvidence({ item }: { item: StockEvidenceChainItem }) {
  const points = item.market_points.slice(-4);
  const latest = item.market_summary.latest_close;
  const returnSince = numberValue(item.market_summary.return_since_first_point);
  return (
    <section className="stock-evidence-section">
      <div className="stock-evidence-section-title">市场证据</div>
      {latest !== undefined && (
        <div className="stock-evidence-market-summary">
          <span>最新收盘 {String(latest)}</span>
          <span className={toneClass(returnSince)}>区间 {formatPercent(returnSince, true)}</span>
        </div>
      )}
      {points.length ? (
        <div className="stock-evidence-market-points">
          {points.map((point) => (
            <MarketPoint point={point} key={`${point.trade_date}-${point.tag ?? ""}`} />
          ))}
        </div>
      ) : (
        <p className="stock-evidence-empty">暂无市场证据。</p>
      )}
    </section>
  );
}

function MarketPoint({ point }: { point: StockEvidenceMarketPoint }) {
  return (
    <article>
      <time>{point.trade_date}</time>
      <strong>{point.close ?? "-"}</strong>
      <span className={toneClass(point.pct_chg)}>{formatPercent(point.pct_chg, true)}</span>
      <small>量能 {point.amount_ratio_5d ? `${point.amount_ratio_5d.toFixed(1)}x` : "-"}</small>
    </article>
  );
}

function DetailSection({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="stock-evidence-section">
      <div className="stock-evidence-section-title">{title}</div>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="stock-evidence-empty">暂无。</p>
      )}
    </section>
  );
}

function RiskBlock({ title, value }: { title: string; value?: string | null }) {
  return (
    <section className="stock-evidence-risk">
      <AlertTriangle size={14} />
      <strong>{title}</strong>
      <p>{value || "证据不足"}</p>
    </section>
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

function MetricLite(props: { label: string; value: string }) {
  return (
    <article>
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </article>
  );
}

function Fact(props: { icon: ReactNode; label: string; value: string }) {
  return (
    <article>
      {props.icon}
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </article>
  );
}

function StagePill({ item }: { item: StockEvidenceChainItem }) {
  return <span className={`stock-evidence-stage stock-evidence-stage-${item.stage}`}>{item.stage_label}</span>;
}

function stageCount(data: StockEvidenceChainDashboard | null, label: string): number {
  return data?.stage_counts[label] ?? 0;
}

function earlyCount(items: StockEvidenceChainItem[]): number {
  return items.filter((item) => ["线索期", "种子期", "论证期"].includes(item.stage_label)).length;
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
  if (state === "overheated" || state === "pullback_after_pricing") {
    return "risk";
  }
  if (state === "rejected") {
    return "rejected";
  }
  return "unknown";
}

function roleLabel(role: string): string {
  if (role === "core") {
    return "核心";
  }
  if (role === "elastic") {
    return "弹性";
  }
  return "待确认";
}

function typeLabel(type: string): string {
  if (type === "industry") {
    return "行业";
  }
  if (type === "concept") {
    return "概念";
  }
  if (type === "theme") {
    return "题材";
  }
  return type || "主题";
}

function coverageText(theme: StockEvidenceChainItem["primary_theme"]): string {
  if (!theme?.covered_member_count || !theme.member_count) {
    return "-";
  }
  return `${theme.covered_member_count}/${theme.member_count}`;
}
