import { Check, Clock3, Copy, FileText, MessageSquareText, ShieldAlert, Users, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { copyText } from "../lib/clipboard";
import type { StockEvidenceChainItem, StockEvidenceMarketValidation, StockEvidenceMessage } from "../types";

export function StockEvidenceCurrentTrigger({ item }: { item: StockEvidenceChainItem }) {
  const triggers = item.current_triggers ?? [];
  const [originalMessage, setOriginalMessage] = useState<StockEvidenceMessage | null>(null);
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
            <TriggerRow
              key={`${trigger.message_id ?? trigger.time ?? "trigger"}-${index}`}
              trigger={trigger}
              onOpenOriginal={() => setOriginalMessage(trigger)}
            />
          ))}
          {triggers.length > 4 && <small>还有 {triggers.length - 4} 条本次窗口触发</small>}
        </div>
      ) : (
        <p className="stock-evidence-empty">这版没有恢复到窗口内触发消息，先只按历史证据链观察。</p>
      )}
      <OriginalMessageDrawer trigger={originalMessage} onClose={() => setOriginalMessage(null)} />
    </section>
  );
}

function TriggerRow({ trigger, onOpenOriginal }: { trigger: StockEvidenceMessage; onOpenOriginal: () => void }) {
  const hasOriginal = Boolean(originalContent(trigger));
  return (
    <article className="stock-evidence-current-row">
      <div className="stock-evidence-current-row-head">
        <div>
          <time>{trigger.time ?? "时间待确认"}</time>
          <span>{trigger.type ?? "本次触发"}</span>
        </div>
        {hasOriginal ? (
          <button
            className="stock-evidence-original-btn"
            type="button"
            aria-label="查看原文"
            title="查看原文"
            onClick={onOpenOriginal}
          >
            <FileText size={13} />
          </button>
        ) : null}
      </div>
      <p>{trigger.evidence ?? trigger.raw_content ?? "暂无摘要"}</p>
      <small>
        {[trigger.sender, trigger.group_name].filter(Boolean).join(" · ") || "来源待确认"}
      </small>
    </article>
  );
}

export function OriginalMessageDrawer({ trigger, onClose }: { trigger: StockEvidenceMessage | null; onClose: () => void }) {
  const shouldReduceMotion = useReducedMotion();
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!trigger) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, trigger]);

  if (!trigger) {
    return createPortal(<AnimatePresence>{null}</AnimatePresence>, document.body);
  }

  const content = originalContent(trigger) ?? "暂无原文";
  const shellMotion = originalShellMotion(shouldReduceMotion);
  const drawerMotion = originalDrawerMotion(shouldReduceMotion);

  async function copyOriginal() {
    try {
      await copyText(content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }

  return createPortal(
    <AnimatePresence>
      <motion.div
        className="stock-evidence-original-shell"
        role="dialog"
        aria-modal="true"
        aria-label="查看原文"
        key="stock-evidence-original"
        {...shellMotion}
      >
        <motion.button
          className="stock-evidence-original-scrim"
          type="button"
          aria-label="关闭原文"
          onClick={onClose}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={shouldReduceMotion ? { duration: 0.08 } : { duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
        />
        <motion.aside className="stock-evidence-original-drawer" {...drawerMotion}>
          <header>
            <div>
              <span>{trigger.type ?? "原始消息"}</span>
              <strong>查看原文</strong>
            </div>
            <div>
              <button
                className={copied ? "icon-btn is-copied" : "icon-btn"}
                type="button"
                aria-label={copied ? "已复制原文" : "复制原文"}
                title={copied ? "已复制" : "复制原文"}
                onClick={() => void copyOriginal()}
              >
                {copied ? <Check size={15} /> : <Copy size={15} />}
              </button>
              <button className="icon-btn" type="button" aria-label="关闭原文" onClick={onClose}>
                <X size={16} />
              </button>
            </div>
          </header>
          <div className="stock-evidence-original-meta">
            <article>
              <span>时间</span>
              <strong>{trigger.time ?? "-"}</strong>
            </article>
            <article>
              <span>发送人</span>
              <strong>{trigger.sender ?? "-"}</strong>
            </article>
            <article>
              <span>来源</span>
              <strong>{trigger.group_name ?? "个人消息"}</strong>
            </article>
          </div>
          <pre>{content}</pre>
        </motion.aside>
      </motion.div>
    </AnimatePresence>,
    document.body,
  );
}

function originalShellMotion(shouldReduceMotion: boolean | null) {
  if (shouldReduceMotion) {
    return {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: { duration: 0.12 },
    };
  }
  return {
    initial: { opacity: 1 },
    animate: { opacity: 1 },
    exit: { opacity: 1 },
    transition: { duration: 0.16 },
  };
}

function originalDrawerMotion(shouldReduceMotion: boolean | null) {
  if (shouldReduceMotion) {
    return {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: { duration: 0.12 },
    };
  }
  return {
    initial: { opacity: 0.92, x: 28 },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0, x: 24 },
    transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] as const },
  };
}

export function originalContent(trigger: StockEvidenceMessage): string | null {
  const content = trigger.raw_content?.trim();
  return content || null;
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
