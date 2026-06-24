import { Copy, X } from "lucide-react";
import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";

import { copyText } from "../lib/clipboard";
import { formatTime } from "../lib/datetime";
import type { CatalystEvidenceMessage, CatalystFeedItem, CatalystTermHit } from "../types";
import { ChatLauncher } from "./ChatLauncher";

const catalystEvidenceQuickPrompts = [
  {
    label: "强度评级",
    prompt:
      "基于当前原文证据，判断它属于什么催化类型，提炼一句话结论，并给出强/中/弱评级、理由和不确定点。请区分原文事实和你的推断。",
  },
  {
    label: "串联证据",
    prompt:
      "围绕当前证据，在当前时间窗及前后 48 小时内继续查找同主题、同标的、同关键词的相关消息，按时间线列出最早来源、重复来源、增强证据和削弱证据。",
  },
  {
    label: "标的映射",
    prompt:
      "从当前原文中提取公司、股票代码和产业链环节，区分直接受益、间接受益、仅提及；没有明确证据就标注待确认。",
  },
  {
    label: "反证跟踪",
    prompt:
      "列出这条线索最需要验证的 3 个问题、可能的反向风险，以及下一步应跟踪的关键词、公开证据或后续消息。",
  },
];

export function CatalystDetailDrawer({ item, onClose }: { item: CatalystFeedItem; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const chatContext = useMemo(() => buildCatalystChatContext(item), [item]);
  const chatEvidence = useMemo(() => buildCatalystChatEvidence(item), [item]);

  useEffect(() => {
    const scrollY = window.scrollY;
    const originalBodyStyle = {
      overflow: document.body.style.overflow,
      position: document.body.style.position,
      top: document.body.style.top,
      width: document.body.style.width,
    };

    document.body.style.overflow = "hidden";
    document.body.style.position = "fixed";
    document.body.style.top = `-${scrollY}px`;
    document.body.style.width = "100%";

    const handleKeyDown = (event: KeyboardEvent) => {
      if (document.querySelector(".chat-launcher-shell")) {
        return;
      }
      if (event.key === "Escape" && !event.isComposing) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = originalBodyStyle.overflow;
      document.body.style.position = originalBodyStyle.position;
      document.body.style.top = originalBodyStyle.top;
      document.body.style.width = originalBodyStyle.width;
      window.scrollTo(0, scrollY);
    };
  }, [onClose]);

  return (
    <div
      className="catalyst-detail-drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <aside className="catalyst-detail-panel catalyst-detail-drawer content-panel panel" role="dialog" aria-modal="true">
        <header className="catalyst-detail-head">
          <div>
            <h2>原文证据</h2>
            <span>最早 {formatTime(item.first_message_time)} · 最新 {formatTime(item.latest_message_time)}</span>
          </div>
          <div className="catalyst-detail-actions">
            <ChatLauncher
              title="原文证据"
              subtitle={`${conversationLabel(item)} · ${formatTime(item.first_message_time)}`}
              surface="催化词"
              entityId={item.key}
              buttonLabel="AI"
              buttonClassName="mini-button catalyst-detail-ai-action"
              context={chatContext}
              evidence={chatEvidence}
              quickPrompts={catalystEvidenceQuickPrompts}
              suggestedQuestions={[
                "判断这条催化词线索的强度，并说明还缺什么证据。",
                "找一下前后 48 小时有没有同主题或同标的的增强/削弱证据。",
                "提取这条原文涉及的标的和产业链环节，区分直接证据和推断。",
              ]}
            />
            <button
              className="mini-button"
              type="button"
              title="复制原文"
              onClick={() => {
                void copyText(item.raw_content).then(() => {
                  setCopied(true);
                  window.setTimeout(() => setCopied(false), 1200);
                });
              }}
            >
              <Copy size={14} />
            </button>
            <button className="mini-button" type="button" title="关闭详情" onClick={onClose}>
              <X size={14} />
            </button>
          </div>
        </header>
        {copied && <p className="catalyst-copy-state">已复制</p>}
        <div className="catalyst-chip-row detail">
          {item.message_count > 1 && <span className="catalyst-stock-chip">连续 {item.message_count} 条</span>}
          {item.matched_terms.map((hit) => (
            <CatalystTermChip hit={hit} key={`${hit.category_id}-${hit.term}`} />
          ))}
          {item.stock_mentions.map((stock) => (
            <span className="catalyst-stock-chip" key={`${stock.ts_code ?? ""}-${stock.stock_name}`}>
              {stock.stock_name}
            </span>
          ))}
        </div>
        <CatalystMessageList item={item} />
        <div className="catalyst-duplicates">
          <strong>重复来源</strong>
          {item.duplicate_sources.map((source) => (
            <span key={source.message_id}>
              <em>{formatTime(source.message_time)}</em>
              {source.source === "个人群" ? source.group_name : source.sender}
              <small>
                {source.sender}
                {source.message_count > 1 ? ` · ${source.message_count}条` : ""}
              </small>
            </span>
          ))}
        </div>
      </aside>
    </div>
  );
}

function CatalystMessageList({ item }: { item: CatalystFeedItem }) {
  const messages =
    item.messages.length > 0
      ? item.messages
      : [
          {
            message_id: item.message_id,
            message_time: item.first_message_time,
            raw_content: item.raw_content,
            matched_terms: item.matched_terms,
          },
        ];
  return (
    <div className="catalyst-message-list">
      {messages.map((message, index) => (
        <CatalystEvidenceMessageBlock
          key={message.message_id}
          message={message}
          index={index}
        />
      ))}
    </div>
  );
}

function CatalystEvidenceMessageBlock(props: { message: CatalystEvidenceMessage; index: number }) {
  const hits = props.message.matched_terms;
  return (
    <article className="catalyst-evidence-message">
      <header>
        <strong>第 {props.index + 1} 条</strong>
        <time>{formatTime(props.message.message_time)}</time>
        {hits.length > 0 && <span>{hits.length} 个命中词</span>}
      </header>
      <p>{highlightCatalystText(props.message.raw_content, hits)}</p>
    </article>
  );
}

export function CatalystTermChip({ hit }: { hit: CatalystTermHit }) {
  return (
    <span className="catalyst-term-chip" style={{ "--chip-color": hit.color } as CSSProperties}>
      {hit.category_name} · {hit.term}
    </span>
  );
}

export function highlightCatalystText(text: string, hits: CatalystTermHit[]) {
  const terms = Array.from(new Set(hits.map((hit) => hit.term).filter(Boolean))).sort((a, b) => b.length - a.length);
  if (terms.length === 0) {
    return text;
  }
  const pattern = new RegExp(`(${terms.map(escapeRegex).join("|")})`, "gi");
  return text.split(pattern).map((part, index) => {
    const matched = terms.some((term) => term.toLowerCase() === part.toLowerCase());
    return matched ? <mark key={`${part}-${index}`}>{part}</mark> : <span key={`${part}-${index}`}>{part}</span>;
  });
}

function buildCatalystChatContext(item: CatalystFeedItem) {
  return [
    { label: "入口", value: "催化词原文证据" },
    { label: "会话", value: conversationLabel(item) },
    { label: "发送人", value: item.sender },
    { label: "最早时间", value: formatTime(item.first_message_time) },
    { label: "最新时间", value: formatTime(item.latest_message_time) },
    { label: "命中词", value: termSummary(item) },
    { label: "标的", value: stockSummary(item) },
    { label: "重复来源", value: item.duplicate_count > 1 ? `${item.duplicate_count} 条` : "无" },
  ];
}

function buildCatalystChatEvidence(item: CatalystFeedItem) {
  const duplicates = item.duplicate_sources
    .slice(0, 6)
    .map((source) => `${formatTime(source.message_time)} ${source.source === "个人群" ? source.group_name : source.sender} ${source.sender}`)
    .join("\n");
  const messages = (item.messages.length > 0 ? item.messages : []).map(
    (message, index) => `第 ${index + 1} 条（${formatTime(message.message_time)}）：\n${message.raw_content}`,
  );
  return [
    `命中催化词：${termSummary(item)}`,
    `标的识别：${stockSummary(item)}`,
    messages.length > 0 ? `原文分段：\n${messages.join("\n\n")}` : `原文：\n${item.raw_content}`,
    duplicates ? `重复来源：\n${duplicates}` : "",
  ].filter(Boolean);
}

function conversationLabel(item: CatalystFeedItem) {
  return item.source === "个人群" ? item.group_name || "未命名群" : item.sender;
}

function termSummary(item: CatalystFeedItem) {
  const terms = item.matched_terms.map((hit) => `${hit.category_name} / ${hit.term}`);
  return Array.from(new Set(terms)).join("、") || "无";
}

function stockSummary(item: CatalystFeedItem) {
  const stocks = item.stock_mentions.map((stock) => (stock.ts_code ? `${stock.stock_name} ${stock.ts_code}` : stock.stock_name));
  return Array.from(new Set(stocks)).join("、") || "未识别";
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
