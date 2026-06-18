import { FileText, Gauge, MessageSquareText, TrendingUp } from "lucide-react";
import { useState } from "react";

import type { StockEvidenceChainItem, StockEvidenceMarketPoint, StockEvidenceMessage } from "../types";
import { OriginalMessageDrawer, originalContent } from "./StockEvidenceCurrentTrigger";

type TimelineRow = {
  date: string;
  messages: StockEvidenceMessage[];
  marketPoints: StockEvidenceMarketPoint[];
};

export function StockEvidenceAlignedTimeline({ item }: { item: StockEvidenceChainItem }) {
  const rows = alignedTimelineRows(item);
  const [originalMessage, setOriginalMessage] = useState<StockEvidenceMessage | null>(null);
  const validation = item.market_validation ?? { status: "unknown", note: "" };
  return (
    <div className="stock-evidence-aligned-block">
      {validation.note && (
        <p className={`stock-evidence-aligned-note ${validationTone(validation.status)}`}>
          {validation.note}
        </p>
      )}
      <div className="stock-evidence-aligned-legend">
        <span>
          <MessageSquareText size={13} />
          消息证据
        </span>
        <span>
          <TrendingUp size={13} />
          市场反馈
        </span>
      </div>
      <div className="stock-evidence-aligned-timeline">
        {rows.map((row) => (
          <section className="stock-evidence-aligned-row" key={row.date}>
            <time>{row.date}</time>
            <div className="stock-evidence-aligned-cell">
              {row.messages.length ? (
                row.messages.slice(0, 2).map((evidence, index) => (
                  <div className="stock-evidence-aligned-evidence" key={`${evidence.message_id ?? row.date}-${index}`}>
                    <div className="stock-evidence-aligned-evidence-head">
                      <strong>
                        {timeOnly(evidence.time)}
                        <span>{evidence.type ?? "证据"}</span>
                      </strong>
                      {originalContent(evidence) ? (
                        <button
                          className="stock-evidence-original-btn"
                          type="button"
                          aria-label="查看原文"
                          title="查看原文"
                          onClick={() => setOriginalMessage(evidence)}
                        >
                          <FileText size={13} />
                        </button>
                      ) : null}
                    </div>
                    <p>{evidence.evidence ?? evidence.raw_content ?? "无摘要"}</p>
                  </div>
                ))
              ) : (
                <p className="stock-evidence-aligned-empty">当日没有入选关键消息</p>
              )}
              {row.messages.length > 2 && <small>还有 {row.messages.length - 2} 条消息</small>}
            </div>
            <div className="stock-evidence-aligned-cell market">
              {row.marketPoints.length ? (
                row.marketPoints.map((point) => (
                  <div className="stock-evidence-aligned-market" key={`${point.trade_date}-${point.tag ?? ""}`}>
                    <strong className={toneClass(point.pct_chg)}>
                      {point.close ?? "-"} / {formatPercentPoint(point.pct_chg, true)}
                    </strong>
                    <p>
                      量能 {point.amount_ratio_5d ? `${point.amount_ratio_5d.toFixed(1)}x` : "-"}
                      {point.tag ? ` · ${marketTagLabel(point.tag)}` : ""}
                    </p>
                  </div>
                ))
              ) : (
                <p className="stock-evidence-aligned-empty">暂无市场反馈</p>
              )}
            </div>
          </section>
        ))}
        {!rows.length && <p className="stock-evidence-empty">暂无可对照的消息或市场证据。</p>}
      </div>
      {originalMessage ? <OriginalMessageDrawer trigger={originalMessage} onClose={() => setOriginalMessage(null)} /> : null}
      <section className="stock-evidence-judgement-panel">
        <h4>
          <Gauge size={14} />
          系统当前判断
        </h4>
        <div>
          <article>
            <span>阶段</span>
            <strong>{item.stage_label}</strong>
            <p>{item.summary || "暂无一句话判断"}</p>
          </article>
          <article>
            <span>市场</span>
            <strong>{item.recognition.state_label}</strong>
            <p>{item.recognition.reasons[0] ?? "还缺市场确认依据"}</p>
          </article>
          <article>
            <span>动作</span>
            <strong>{item.review.action_label}</strong>
            <p>{item.review.headline}</p>
          </article>
        </div>
      </section>
    </div>
  );
}

function alignedTimelineRows(item: StockEvidenceChainItem): TimelineRow[] {
  const rows = new Map<string, TimelineRow>();
  const ensureRow = (date: string): TimelineRow => {
    const current = rows.get(date);
    if (current) {
      return current;
    }
    const next = { date, messages: [], marketPoints: [] };
    rows.set(date, next);
    return next;
  };

  const currentTriggers = item.current_triggers ?? [];
  const currentIds = new Set(currentTriggers.map((evidence) => evidence.message_id).filter(Boolean));
  currentTriggers.slice(0, 6).forEach((evidence) => {
    ensureRow(dateKeyFromMessage(evidence)).messages.push(evidence);
  });
  item.evidence_chain
    .filter((evidence) => !evidence.message_id || !currentIds.has(evidence.message_id))
    .slice(0, 6)
    .forEach((evidence) => {
      ensureRow(dateKeyFromMessage(evidence)).messages.push(evidence);
    });
  item.market_points.slice(-5).forEach((point) => {
    const date = formatTradeDate(point.trade_date);
    if (point.tag !== "latest" && !rows.has(date)) {
      return;
    }
    ensureRow(date).marketPoints.push(point);
  });

  return Array.from(rows.values()).sort((a, b) => dateSortValue(a.date) - dateSortValue(b.date));
}

function dateKeyFromMessage(evidence: StockEvidenceMessage): string {
  const value = evidence.time;
  if (!value) {
    return "日期待确认";
  }
  const dashedDate = value.match(/\d{4}-\d{2}-\d{2}/)?.[0];
  if (dashedDate) {
    return dashedDate;
  }
  const compactDate = value.match(/\d{8}/)?.[0];
  if (compactDate) {
    return formatTradeDate(compactDate);
  }
  return "日期待确认";
}

function formatTradeDate(value: string): string {
  if (/^\d{8}$/.test(value)) {
    return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6)}`;
  }
  return value;
}

function timeOnly(value?: string | null): string {
  if (!value) {
    return "-";
  }
  const time = value.match(/\d{2}:\d{2}/)?.[0];
  return time ?? value.slice(0, 10);
}

function dateSortValue(value: string): number {
  if (value === "日期待确认") {
    return Number.MAX_SAFE_INTEGER;
  }
  const time = Date.parse(`${value}T00:00:00`);
  return Number.isNaN(time) ? Number.MAX_SAFE_INTEGER : time;
}

function marketTagLabel(tag: string): string {
  if (tag === "latest") {
    return "最新交易日";
  }
  if (tag === "evidence_day") {
    return "历史证据日";
  }
  if (tag === "selected_high") {
    return "阶段高点";
  }
  return tag;
}

function validationTone(status: string): string {
  if (status === "has_after_trigger_market") {
    return "confirmed";
  }
  if (status === "pending_current_trigger" || status === "same_day_current_trigger") {
    return "watch";
  }
  if (status === "no_market") {
    return "risk";
  }
  return "muted";
}

function formatPercentPoint(value?: number | null, signed = false): string {
  if (value === undefined || value === null) {
    return "-";
  }
  const text = `${value.toFixed(1)}%`;
  return signed && value > 0 ? `+${text}` : text;
}

function toneClass(value?: number | null): string {
  if (value === undefined || value === null || value === 0) {
    return "return-flat";
  }
  return value > 0 ? "return-up" : "return-down";
}
