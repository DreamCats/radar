import { ArrowDown, Check, ChevronDown, CircleAlert, Copy, SquareTerminal } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState, type ComponentType, type RefObject, type UIEvent } from "react";

import type { ChatMessageItem } from "../types";
import { copyText } from "../lib/clipboard";
import { chatTraceItems, statusForChatMessage, toolActivities, type ChatTraceItem, type ToolActivityItem } from "./chatHelpers";
import { DrawerMarkdownContent } from "./DrawerMarkdownContent";
import { MarkdownContent } from "./MarkdownContent";

type ChatMessageListProps = {
  endRef: RefObject<HTMLDivElement | null>;
  listRef: RefObject<HTMLDivElement | null>;
  messages: ChatMessageItem[];
  emptyState?: "overview";
  markdownSurface?: "drawer";
  showJumpToBottom: boolean;
  onJumpToBottom: () => void;
  onScrollStateChange: (isNearBottom: boolean) => void;
};

export function ChatMessageList(props: ChatMessageListProps) {
  const Content = props.markdownSurface === "drawer" ? DrawerMarkdownContent : MarkdownContent;
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  function handleScroll(event: UIEvent<HTMLDivElement>) {
    props.onScrollStateChange(isNearBottom(event.currentTarget));
  }

  async function handleCopyMessage(message: ChatMessageItem) {
    try {
      await copyText(message.content);
      setCopiedMessageId(message.message_id);
      window.setTimeout(() => {
        setCopiedMessageId((current) => (current === message.message_id ? null : current));
      }, 1400);
    } catch {
      setCopiedMessageId(null);
    }
  }

  return (
    <div className="chat-message-list-shell">
      <div
        className={props.showJumpToBottom ? "chat-message-list with-jump-to-bottom" : "chat-message-list"}
        ref={props.listRef}
        onScroll={handleScroll}
      >
        {props.messages.length === 0 && props.emptyState === "overview" ? (
          <div className="chat-empty-state">
            <strong>本地消息已就绪</strong>
            <span>等待一个股票、产业链或消息线索。</span>
          </div>
        ) : null}
        <AnimatePresence initial={false}>
          {props.messages.map((message) => {
            const status = message.role === "assistant" ? statusForChatMessage(message.metadata) : "";
            const activities = toolActivities(message.metadata.tool_activities);
            const traceItems = normalizeTraceItems(chatTraceItems(message.metadata.trace_items));
            const hasAssistantTrace = traceItems.some((item) => item.type === "assistant");
            const canCopy = message.role === "assistant" && Boolean(message.content) && !message.metadata.streaming;
            const isCopied = copiedMessageId === message.message_id;
            return (
              <motion.article
                className={`chat-message chat-message-${message.role}`}
                key={message.message_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.16 }}
              >
                {message.role === "assistant" && (status || activities.length > 0 || traceItems.length > 0) ? (
                  <AssistantTrace
                    activities={activities}
                    Content={Content}
                    status={status || "正在处理"}
                    streaming={Boolean(message.metadata.streaming)}
                    traceItems={traceItems}
                  />
                ) : null}
                {message.content && !hasAssistantTrace ? (
                  <>
                    <Content content={message.content} />
                    {message.metadata.streaming ? <i className="chat-stream-cursor" aria-hidden="true" /> : null}
                  </>
                ) : !hasAssistantTrace ? (
                  <div className="chat-typing" aria-label="生成中">
                    <span>正在整理</span>
                    <em />
                    <em />
                    <em />
                  </div>
                ) : null}
                {canCopy ? (
                  <div className="chat-message-actions">
                    <button
                      className={isCopied ? "chat-message-copy is-copied" : "chat-message-copy"}
                      type="button"
                      aria-label={isCopied ? "已复制回复" : "复制回复"}
                      title={isCopied ? "已复制" : "复制"}
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleCopyMessage(message);
                      }}
                    >
                      {isCopied ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                  </div>
                ) : null}
              </motion.article>
            );
          })}
        </AnimatePresence>
        <div ref={props.endRef} />
      </div>
      {props.showJumpToBottom ? (
        <button className="chat-jump-to-bottom" type="button" onClick={props.onJumpToBottom}>
          <ArrowDown size={14} />
          <span>新内容</span>
        </button>
      ) : null}
    </div>
  );
}

const TOOL_ACTIVITY_COLLAPSE_LIMIT = 6;
const TRANSIENT_STATUS_LABELS = new Set(["正在推理", "正在查询本地数据", "正在整理结果", "正在生成回答"]);
const PROCESS_SUMMARIES = new Set([
  "我会先拆解你的问题，确定需要查哪些证据。",
  "我会先准备要查的数据，再按证据强度比较。",
  "我会先拉取候选、消息和行情相关数据，之后再统一比较。",
  "我会先从策略候选里拿到可比较的标的池。",
  "我会回到本地消息里补原文证据、来源密度和反证。",
  "我会补证据链详情，检查触发、验证点和暂缓条件。",
  "我会补行情和资金流，确认市场是否已经定价。",
  "我会补必要的分析模板，再把结果整理成结论。",
  "我会补齐下一步判断需要的数据。",
  "工具结果开始返回，我会把新增数据并入判断。",
  "判断已经形成，开始整理成可读回答。",
]);

type ToolActivityDisplayItem = ToolActivityItem & {
  count: number;
};

type TraceDisplayItem =
  | Exclude<ChatTraceItem, { type: "tool" }>
  | {
      key: string;
      type: "tool_group";
      label: string;
      status: ToolActivityItem["status"];
      count: number;
    };

function normalizeTraceItems(items: ChatTraceItem[]): ChatTraceItem[] {
  return items.filter((item) => {
    if (item.type === "reasoning") {
      return false;
    }
    if (item.type === "status") {
      return !TRANSIENT_STATUS_LABELS.has(item.label);
    }
    if (item.type === "summary") {
      return PROCESS_SUMMARIES.has(item.content);
    }
    return true;
  });
}

function AssistantTrace({
  activities,
  Content,
  status,
  streaming,
  traceItems,
}: {
  activities: ToolActivityItem[];
  Content: ComponentType<{ content: string }>;
  status: string;
  streaming: boolean;
  traceItems: ChatTraceItem[];
}) {
  const hasProcess = traceItems.length > 0 || activities.length > 0;
  const hasAssistantTrace = traceItems.some((item) => item.type === "assistant");
  const [expanded, setExpanded] = useState(streaming);

  useEffect(() => {
    if (streaming) {
      setExpanded(true);
    }
  }, [streaming]);

  if (!hasProcess) {
    return <div className="chat-agent-status">{status}</div>;
  }

  if (hasAssistantTrace) {
    return (
      <div className={expanded ? "chat-agent-trace is-open" : "chat-agent-trace"}>
        <button
          className="chat-agent-summary"
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          <span>{status}</span>
          <ChevronDown size={14} aria-hidden="true" />
        </button>
        <div className="chat-agent-process">
          <ChatTraceTimeline Content={Content} items={traceItems} showProcess={expanded} streaming={streaming} />
        </div>
      </div>
    );
  }

  return (
    <details className="chat-agent-trace" open={streaming}>
      <summary className="chat-agent-summary">
        <span>{status}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </summary>
      <div className="chat-agent-process">
        {traceItems.length > 0 ? (
          <ChatProcessTimeline items={traceItems} streaming={streaming} />
        ) : (
          <ChatToolActivityList activities={activities} />
        )}
      </div>
    </details>
  );
}

function ChatProcessTimeline({ items, streaming }: { items: ChatTraceItem[]; streaming: boolean }) {
  const visibleItems = groupTraceItems(items.filter((item) => item.type !== "assistant"));
  const activeStatusKey = streaming ? latestItemKey(visibleItems, "status") : undefined;
  const activeSummaryKey = streaming && !activeStatusKey ? visibleItems[visibleItems.length - 1]?.key : undefined;
  return (
    <div className="chat-trace-timeline">
      {visibleItems.map((item) =>
        item.type === "tool_group" ? (
          <ChatTraceToolRow count={item.count} key={item.key} label={item.label} status={item.status} />
        ) : item.type === "status" ? (
          <ChatTraceStatusRow key={item.key} active={item.key === activeStatusKey} label={item.label} />
        ) : item.type === "summary" ? (
          <ChatTraceSummaryRow key={item.key} active={item.key === activeSummaryKey} content={item.content} />
        ) : item.type === "error" ? (
          <ChatTraceErrorRow key={item.key} message={item.message} />
        ) : null,
      )}
    </div>
  );
}

function ChatTraceTimeline({
  Content,
  items,
  showProcess,
  streaming,
}: {
  Content: ComponentType<{ content: string }>;
  items: ChatTraceItem[];
  showProcess: boolean;
  streaming: boolean;
}) {
  const displayItems = groupTraceItems(items);
  const lastAssistantKey = [...displayItems].reverse().find((item) => item.type === "assistant")?.key;
  const activeStatusKey = streaming ? latestItemKey(displayItems, "status") : undefined;
  const activeSummaryKey = streaming && !activeStatusKey ? displayItems[displayItems.length - 1]?.key : undefined;
  return (
    <div className="chat-trace-timeline">
      {displayItems.map((item) => {
        if (item.type === "assistant") {
          return (
            <div className="chat-trace-entry chat-trace-entry-assistant" key={item.key}>
              <span className="chat-trace-node" aria-hidden="true" />
              <div className="chat-trace-body chat-trace-assistant">
                <Content content={item.content} />
                {streaming && item.key === lastAssistantKey ? <i className="chat-stream-cursor" aria-hidden="true" /> : null}
              </div>
            </div>
          );
        }
        if (!showProcess) {
          return null;
        }
        if (item.type === "tool_group") {
          return <ChatTraceToolRow count={item.count} key={item.key} label={item.label} status={item.status} />;
        }
        if (item.type === "status") {
          return <ChatTraceStatusRow key={item.key} active={item.key === activeStatusKey} label={item.label} />;
        }
        if (item.type === "summary") {
          return <ChatTraceSummaryRow key={item.key} active={item.key === activeSummaryKey} content={item.content} />;
        }
        if (item.type === "error") {
          return <ChatTraceErrorRow key={item.key} message={item.message} />;
        }
        return null;
      })}
    </div>
  );
}

function latestItemKey(items: TraceDisplayItem[], type: TraceDisplayItem["type"]): string | undefined {
  return [...items].reverse().find((item) => item.type === type)?.key;
}

function groupTraceItems(items: ChatTraceItem[]): TraceDisplayItem[] {
  return items.reduce<TraceDisplayItem[]>((groups, item) => {
    if (item.type !== "tool") {
      groups.push(item);
      return groups;
    }
    const last = groups[groups.length - 1];
    if (last?.type === "tool_group" && last.label === item.label && last.status === item.status) {
      last.count += 1;
      return groups;
    }
    groups.push({
      key: `tool-group-${item.key}`,
      type: "tool_group",
      label: item.label,
      status: item.status,
      count: 1,
    });
    return groups;
  }, []);
}

function ChatTraceStatusRow({ active, label }: { active?: boolean; label: string }) {
  return (
    <div className={active ? "chat-trace-entry chat-trace-entry-status is-active" : "chat-trace-entry chat-trace-entry-status"}>
      <span className="chat-trace-node" aria-hidden="true" />
      <span className="chat-trace-body">{label}</span>
    </div>
  );
}

function ChatTraceSummaryRow({ active, content }: { active?: boolean; content: string }) {
  return (
    <div className={active ? "chat-trace-entry chat-trace-entry-summary is-active" : "chat-trace-entry chat-trace-entry-summary"}>
      <span className="chat-trace-node" aria-hidden="true" />
      <span className="chat-trace-body">{content}</span>
    </div>
  );
}

function ChatTraceErrorRow({ message }: { message: string }) {
  return (
    <div className="chat-trace-entry chat-trace-entry-error">
      <span className="chat-trace-node" aria-hidden="true">
        <CircleAlert size={14} />
      </span>
      <span className="chat-trace-body">{message}</span>
    </div>
  );
}

function ChatTraceToolRow({ count, label, status }: { count: number; label: string; status: ToolActivityItem["status"] }) {
  return (
    <div className={`chat-trace-entry chat-trace-entry-tool chat-trace-entry-tool-${status}`}>
      <span className="chat-trace-node" aria-hidden="true">
        <SquareTerminal size={14} />
      </span>
      <span className="chat-trace-body">
        <span>{toolActivitySummary(status, count)}</span>
        <em>{label}</em>
      </span>
    </div>
  );
}

function ChatToolActivityList({ activities }: { activities: ToolActivityItem[] }) {
  const [expanded, setExpanded] = useState(false);
  const groupedActivities = groupConsecutiveToolActivities(activities);
  const hasHiddenGroups = groupedActivities.length > TOOL_ACTIVITY_COLLAPSE_LIMIT;
  const hasGroupedItems = groupedActivities.some((activity) => activity.count > 1);
  const canExpand = hasHiddenGroups || hasGroupedItems;
  const displayActivities =
    expanded ? activities.map((activity) => ({ ...activity, count: 1 })) : groupedActivities.slice(0, TOOL_ACTIVITY_COLLAPSE_LIMIT);
  const hiddenCount = hasHiddenGroups
    ? groupedActivities.slice(TOOL_ACTIVITY_COLLAPSE_LIMIT).reduce((total, activity) => total + activity.count, 0)
    : 0;

  return (
    <div className="chat-tool-activity-block">
      <ul className="chat-tool-activity-list">
        {displayActivities.map((activity) => (
          <ChatToolActivityRow count={activity.count} key={activity.key} label={activity.label} status={activity.status} />
        ))}
      </ul>
      {canExpand ? (
        <button className="chat-tool-activity-toggle" type="button" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "收起工具调用" : hiddenCount > 0 ? `还有 ${hiddenCount} 个工具调用` : `展开 ${activities.length} 个工具调用`}
        </button>
      ) : null}
    </div>
  );
}

function ChatToolActivityRow({ count, label, status }: { count: number; label: string; status: ToolActivityItem["status"] }) {
  return (
    <li className={`chat-tool-activity-${status}`}>
      <SquareTerminal size={14} aria-hidden="true" />
      <span>{toolActivitySummary(status, count)}</span>
      <em>{label}</em>
    </li>
  );
}

function toolActivitySummary(status: ToolActivityItem["status"], count: number): string {
  const verb = status === "running" ? "正在运行" : "已运行";
  return `${verb} ${count} 条工具调用`;
}

function groupConsecutiveToolActivities(activities: ToolActivityItem[]): ToolActivityDisplayItem[] {
  return activities.reduce<ToolActivityDisplayItem[]>((groups, activity) => {
    const last = groups[groups.length - 1];
    if (last && last.label === activity.label && last.status === activity.status) {
      last.count += 1;
      return groups;
    }
    groups.push({ ...activity, count: 1 });
    return groups;
  }, []);
}

function isNearBottom(element: HTMLDivElement): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight < 80;
}
