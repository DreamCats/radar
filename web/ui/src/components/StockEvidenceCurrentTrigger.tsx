import { Clock3, MessageSquareText, ShieldAlert, Users } from "lucide-react";

import type { StockEvidenceChainItem, StockEvidenceMarketValidation, StockEvidenceMessage } from "../types";

export function StockEvidenceCurrentTrigger({ item }: { item: StockEvidenceChainItem }) {
  const triggers = item.current_triggers ?? [];
  const validation: StockEvidenceMarketValidation = item.market_validation ?? {
    status: "unknown",
    label: "待判断",
    note: "缺少市场验证状态，先按历史证据链观察。",
  };
  return (
    <section className="stock-evidence-current">
      <div className="stock-evidence-current-head">
        <span>
          <MessageSquareText size={15} />
        </span>
        <div>
          <strong>本次为什么出现</strong>
          <p>{currentTriggerLine(item, validation)}</p>
        </div>
      </div>

      <div className="stock-evidence-current-facts">
        <article>
          <Users size={13} />
          <span>本次触发</span>
          <strong>{item.unique_trigger_count} 条去重</strong>
        </article>
        <article>
          <Clock3 size={13} />
          <span>触发时间</span>
          <strong>{triggerTimeRange(validation)}</strong>
        </article>
        <article className={validationTone(validation.status)}>
          <ShieldAlert size={13} />
          <span>市场验证</span>
          <strong>{validation.label}</strong>
        </article>
      </div>

      <p className={`stock-evidence-validation-note ${validationTone(validation.status)}`}>{validation.note}</p>

      {triggers.length ? (
        <div className="stock-evidence-current-list">
          {triggers.slice(0, 4).map((trigger, index) => (
            <TriggerRow key={`${trigger.message_id ?? trigger.time ?? "trigger"}-${index}`} trigger={trigger} />
          ))}
          {triggers.length > 4 && <small>还有 {triggers.length - 4} 条本次窗口触发</small>}
        </div>
      ) : (
        <p className="stock-evidence-empty">这版没有恢复到窗口内触发消息，先只按历史证据链观察。</p>
      )}
    </section>
  );
}

function TriggerRow({ trigger }: { trigger: StockEvidenceMessage }) {
  return (
    <article className="stock-evidence-current-row">
      <div>
        <time>{trigger.time ?? "时间待确认"}</time>
        <span>{trigger.type ?? "本次触发"}</span>
      </div>
      <p>{trigger.evidence ?? trigger.raw_content ?? "暂无摘要"}</p>
      <small>
        {[trigger.sender, trigger.group_name].filter(Boolean).join(" · ") || "来源待确认"}
      </small>
    </article>
  );
}

function currentTriggerLine(item: StockEvidenceChainItem, validation: Pick<StockEvidenceMarketValidation, "status">): string {
  if (!item.current_triggers?.length) {
    return "当前详情主要来自历史证据链，暂时没有恢复到本次窗口触发消息。";
  }
  if (validation.status === "pending_current_trigger") {
    return "这版是被新增消息重新触发，但这些消息还没等到后续交易日验证。";
  }
  if (validation.status === "has_after_trigger_market") {
    return "这版有新增消息，也已经有后续交易日可用来观察承接。";
  }
  return "先看本次新增消息，再看历史逻辑，不把老定价当成本次验证。";
}

function triggerTimeRange(validation: Pick<StockEvidenceMarketValidation, "current_first_time" | "current_last_time">): string {
  const first = validation.current_first_time;
  const last = validation.current_last_time;
  if (!first) {
    return "-";
  }
  if (!last || first === last) {
    return first;
  }
  return `${first} - ${timeOnly(last)}`;
}

function timeOnly(value: string): string {
  const match = value.match(/\d{2}:\d{2}$/);
  return match?.[0] ?? value;
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
