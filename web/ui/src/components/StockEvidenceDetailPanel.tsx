import { ChevronLeft, FileText, ListChecks, TrendingUp } from "lucide-react";

import type { StockEvidenceChainItem } from "../types";
import { ChatLauncher } from "./ChatLauncher";
import { StockEvidenceBeginnerGuide } from "./StockEvidenceBeginnerGuide";

type Props = {
  item: StockEvidenceChainItem | null;
  onOpenChart?: (stock: StockEvidenceChainItem) => void;
  onOpenChecklist?: (stock: StockEvidenceChainItem) => void;
  onBackToList?: () => void;
};

export function StockEvidenceDetailPanel({ item, onOpenChart, onOpenChecklist, onBackToList }: Props) {
  if (!item) {
    return <aside className="stock-evidence-detail empty">暂无匹配阶段的股票。</aside>;
  }
  return (
    <aside className="stock-evidence-detail">
      <DetailHeader item={item} onOpenChart={onOpenChart} onOpenChecklist={onOpenChecklist} onBackToList={onBackToList} />
      <StockEvidenceBeginnerGuide item={item} />
      <RawEvidenceTimeline item={item} />
    </aside>
  );
}

function DetailHeader({
  item,
  onOpenChart,
  onOpenChecklist,
  onBackToList,
}: {
  item: StockEvidenceChainItem;
  onOpenChart?: (stock: StockEvidenceChainItem) => void;
  onOpenChecklist?: (stock: StockEvidenceChainItem) => void;
  onBackToList?: () => void;
}) {
  return (
    <header>
      <div>
        {onBackToList && (
          <button className="mini-button stock-evidence-detail-back" type="button" onClick={onBackToList} aria-label="返回股票候选">
            <ChevronLeft size={15} />
          </button>
        )}
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
        {onOpenChecklist && (
          <button
            className="stock-evidence-checklist-btn"
            type="button"
            title="打开个股核查卡"
            aria-label={`打开${item.stock_name}个股核查卡`}
            onClick={() => onOpenChecklist(item)}
          >
            <ListChecks size={14} />
            <span>核查卡</span>
          </button>
        )}
        <ChatLauncher
          title={`${item.stock_name} 证据链`}
          subtitle={`${item.ts_code} · ${item.stage_label}`}
          surface="个股证据链"
          entityId={item.ts_code}
          buttonLabel="AI"
          buttonClassName="btn btn-sm stock-evidence-ai-btn"
          context={[
            { label: "股票", value: item.stock_name },
            { label: "代码", value: item.ts_code },
            { label: "阶段", value: item.stage_label },
            { label: "当前状态", value: item.review.label },
            { label: "置信", value: formatConfidence(item.confidence) },
            { label: "触发", value: `${item.trigger_count}条 / 去重${item.unique_trigger_count}` },
            { label: "扩散", value: `${item.sender_count}人 / ${item.conversation_count}会话` },
            { label: "主题", value: item.primary_theme?.theme_name ?? "未确认" },
            { label: "市场认可", value: item.recognition.state_label },
            { label: "生命周期", value: item.lifecycle_digest?.one_line ?? "未生成" },
          ]}
          evidence={stockEvidenceChatLines(item)}
          quickPrompts={[
            { label: "证据核验", prompt: "把这只股票的原文证据、催化、市场确认和反证串成一条证据链；区分事实、推断和缺口。" },
            { label: "主线判断", prompt: "判断它是不是当前主线的真实受益者：说明业务关联强弱、市场认可度、证据缺口和可能误归类的风险。" },
            { label: "跟踪计划", prompt: "给我一份后续跟踪清单：接下来 3 个最该验证的问题、对应要看的数据或消息、什么情况下降低优先级。" },
          ]}
          suggestedQuestions={[
            "用小白能听懂的话解释：消息证据和市场证据怎么对上？",
            "这只股票现在是刚确认、强趋势、充分定价，还是市场不认？",
            "如果继续跟踪，接下来最该盯哪三个验证点？",
          ]}
        />
      </div>
    </header>
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

function stockEvidenceChatLines(item: StockEvidenceChainItem): string[] {
  return [
    `一句话判断：${item.summary || "暂无"}`,
    `阶段：${item.stage_label}；当前状态：${item.review.label}`,
    `主题：${item.primary_theme?.theme_name ?? "未确认"}；市场认可：${item.recognition.state_label}`,
    item.lifecycle_digest ? `生命周期摘要：${item.lifecycle_digest.one_line}` : "",
    ...item.why.slice(0, 4).map((line) => `消息依据：${line}`),
    ...item.recognition.reasons.slice(0, 4).map((line) => `市场依据：${line}`),
    ...item.recognition.missing_evidence.slice(0, 4).map((line) => `证据缺口：${line}`),
    ...item.evidence_chain.slice(0, 6).map((evidence) => {
      const source = [evidence.sender, evidence.group_name].filter(Boolean).join(" · ");
      return `证据：${evidence.time ?? "-"} ${evidence.type ?? "证据"} ${evidence.evidence ?? evidence.raw_content ?? "无摘要"}${source ? `（${source}）` : ""}`;
    }),
    ...item.market_points
      .slice(-4)
      .map(
        (point) =>
          `市场：${point.trade_date} 收盘 ${point.close ?? "-"} 涨跌 ${formatPercentPoint(point.pct_chg, true)} 量能 ${
            point.amount_ratio_5d ? `${point.amount_ratio_5d.toFixed(1)}x` : "-"
          }`,
      ),
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

function formatPercentPoint(value?: number | null, signed = false): string {
  if (value === undefined || value === null) {
    return "-";
  }
  const text = `${value.toFixed(1)}%`;
  return signed && value > 0 ? `+${text}` : text;
}
