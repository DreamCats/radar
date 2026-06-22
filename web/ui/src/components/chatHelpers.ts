import type { ChatMessageItem } from "../types";

const ACTIVE_SESSION_KEY = "radar.chat.activeSessionId";
const SELECTED_PROVIDER_KEY = "radar.chat.selectedProviderName";

export type ToolActivityItem = {
  key: string;
  label: string;
  status: "running" | "completed";
};

export type ChatTraceItem =
  | {
      key: string;
      type: "reasoning";
      content: string;
    }
  | {
      key: string;
      type: "tool";
      toolCallId: string;
      label: string;
      status: "running" | "completed";
    }
  | {
      key: string;
      type: "status";
      label: string;
    }
  | {
      key: string;
      type: "summary";
      content: string;
    }
  | {
      key: string;
      type: "error";
      message: string;
    }
  | {
      key: string;
      type: "assistant";
      content: string;
    };

export function statusForChatMessage(metadata: Record<string, unknown>): string {
  const status = typeof metadata.status === "string" ? metadata.status : "";
  if (status === "已处理") {
    return completedStatus(metadata.duration_ms);
  }
  if (status) {
    return status;
  }
  return durationMsValue(metadata.duration_ms) === null ? "" : completedStatus(metadata.duration_ms);
}

export function completedStatus(durationMs: unknown): string {
  const elapsed = formatElapsedTime(durationMs);
  return elapsed ? `已处理 ${elapsed}` : "已处理";
}

export function formatElapsedTime(durationMs: unknown): string {
  const value = durationMsValue(durationMs);
  if (value === null) {
    return "";
  }
  const totalSeconds = value === 0 ? 0 : Math.max(1, Math.round(value / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m ${seconds}s`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

export function durationMsValue(value: unknown): number | null {
  const duration = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  if (!Number.isFinite(duration) || duration < 0) {
    return null;
  }
  return Math.round(duration);
}

export function statusForAgentEvent(eventType: string, toolName: string): string {
  if (eventType === "turn_started") {
    return "正在理解问题";
  }
  if (eventType === "tool_execution_started") {
    return `正在调用 ${formatToolName(toolName)}`;
  }
  if (eventType === "tool_execution_completed") {
    return `已完成 ${formatToolName(toolName)}`;
  }
  return "";
}

export function formatToolName(toolName: string): string {
  const labels: Record<string, string> = {
    radar_backtest_summary: "回测摘要",
    radar_get_message_context: "消息上下文",
    radar_get_realtime_quote: "实时行情",
    radar_get_stock_limit_context: "涨跌停数据",
    radar_get_stock_moneyflow: "资金流",
    radar_get_stock_price_history: "行情数据",
    radar_get_stock_technical_factors: "技术因子",
    radar_get_limit_pool: "涨跌停池",
    radar_get_billboard_trading: "龙虎榜",
    radar_get_sector_moneyflow: "板块资金流",
    radar_list_conversations: "会话列表",
    radar_message_overview: "消息总览",
    radar_resolve_stock: "股票代码解析",
    radar_search_messages: "消息搜索",
    radar_strategy_dashboard: "策略看板",
  };
  return labels[toolName] ?? (toolName || "工具");
}

export function mergeAssistantMetadata(draft: ChatMessageItem, message: ChatMessageItem): ChatMessageItem {
  const displayContent =
    draft.content.trim() && !message.content.startsWith(draft.content) && draft.content !== message.content
      ? draft.content
      : message.content;
  return {
    ...message,
    message_id: draft.message_id,
    content: displayContent,
    metadata: {
      ...message.metadata,
      server_message_id: message.message_id,
      tool_activities: draft.metadata.tool_activities,
      trace_items: draft.metadata.trace_items,
      status: "正在处理",
      streaming: true,
    },
  };
}

export function appendStatusTrace(raw: unknown, label: string): ChatTraceItem[] {
  const current = chatTraceItems(raw);
  const trimmedLabel = label.trim();
  if (!trimmedLabel) {
    return current;
  }
  const last = current[current.length - 1];
  if (last?.type === "status" && last.label === trimmedLabel) {
    return current;
  }
  return [...current, { key: `status-${current.length + 1}`, type: "status", label: trimmedLabel }];
}

export function appendSummaryTrace(raw: unknown, content: string): ChatTraceItem[] {
  const current = chatTraceItems(raw);
  const trimmedContent = content.trim();
  if (!trimmedContent || current.some((item) => item.type === "summary" && item.content === trimmedContent)) {
    return current;
  }
  return [...current, { key: `summary-${current.length + 1}`, type: "summary", content: trimmedContent }];
}

export function appendErrorTrace(raw: unknown, message: string): ChatTraceItem[] {
  const current = chatTraceItems(raw);
  const trimmedMessage = message.trim();
  if (!trimmedMessage) {
    return current;
  }
  const last = current[current.length - 1];
  if (last?.type === "error" && last.message === trimmedMessage) {
    return current;
  }
  return [...current, { key: `error-${current.length + 1}`, type: "error", message: trimmedMessage }];
}

export function appendAssistantTrace(raw: unknown, content: string): ChatTraceItem[] {
  const current = chatTraceItems(raw);
  if (!content) {
    return current;
  }
  const last = current[current.length - 1];
  if (last?.type === "assistant") {
    return current.map((item, index) =>
      index === current.length - 1 && item.type === "assistant" ? { ...item, content: `${item.content}${content}` } : item,
    );
  }
  return [...current, { key: `assistant-${current.length + 1}`, type: "assistant", content }];
}

export function ensureAssistantTrace(raw: unknown, content: string): ChatTraceItem[] {
  const current = chatTraceItems(raw);
  const fullContent = content.trim();
  if (!fullContent) {
    return current;
  }
  const assistantContent = current
    .map((item) => (item.type === "assistant" ? item.content : ""))
    .filter(Boolean)
    .join("\n\n");
  if (!assistantContent) {
    return appendAssistantTrace(current, content);
  }
  if (content.startsWith(assistantContent)) {
    const missingContent = content.slice(assistantContent.length);
    return missingContent.trim() ? appendAssistantTrace(current, missingContent) : current;
  }
  return current;
}

export function updateToolTrace(raw: unknown, eventType: string, toolCallId: string, toolName: string): ChatTraceItem[] {
  const current = chatTraceItems(raw);
  if (!toolCallId || !toolName) {
    return current;
  }
  if (eventType !== "tool_execution_started" && eventType !== "tool_execution_completed") {
    return current;
  }
  const status = eventType === "tool_execution_started" ? "running" : "completed";
  const index = current.findIndex((item) => item.type === "tool" && item.toolCallId === toolCallId);
  if (index < 0) {
    return [
      ...current,
      {
        key: `tool-${toolCallId}`,
        type: "tool",
        toolCallId,
        label: formatToolName(toolName),
        status,
      },
    ];
  }
  return current.map((item, itemIndex) =>
    itemIndex === index && item.type === "tool" ? { ...item, label: formatToolName(toolName), status } : item,
  );
}

export function updateToolActivities(raw: unknown, eventType: string, toolCallId: string, toolName: string): ToolActivityItem[] {
  const current = toolActivities(raw);
  if (!toolCallId || !toolName) {
    return current;
  }
  if (eventType !== "tool_execution_started" && eventType !== "tool_execution_completed") {
    return current;
  }
  const activity = {
    key: toolCallId,
    label: formatToolName(toolName),
    status: eventType === "tool_execution_started" ? "running" : "completed",
  } as ToolActivityItem;
  const index = current.findIndex((item) => item.key === toolCallId);
  if (index < 0) {
    return [...current, activity];
  }
  return current.map((item, itemIndex) => (itemIndex === index ? activity : item));
}

export function toolActivities(raw: unknown): ToolActivityItem[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter(isToolActivityItem);
}

export function chatTraceItems(raw: unknown): ChatTraceItem[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter(isChatTraceItem);
}

export function readActiveSessionId(): string | null {
  return window.localStorage.getItem(ACTIVE_SESSION_KEY);
}

export function writeActiveSessionId(sessionId: string) {
  window.localStorage.setItem(ACTIVE_SESSION_KEY, sessionId);
}

export function clearActiveSessionId() {
  window.localStorage.removeItem(ACTIVE_SESSION_KEY);
}

export function readSelectedProviderName(): string | null {
  return window.localStorage.getItem(SELECTED_PROVIDER_KEY);
}

export function writeSelectedProviderName(providerName: string) {
  window.localStorage.setItem(SELECTED_PROVIDER_KEY, providerName);
}

export function clearSelectedProviderName() {
  window.localStorage.removeItem(SELECTED_PROVIDER_KEY);
}

function isToolActivityItem(value: unknown): value is ToolActivityItem {
  if (!value || typeof value !== "object") {
    return false;
  }
  const item = value as Record<string, unknown>;
  return (
    typeof item.key === "string" &&
    typeof item.label === "string" &&
    (item.status === "running" || item.status === "completed")
  );
}

function isChatTraceItem(value: unknown): value is ChatTraceItem {
  if (!value || typeof value !== "object") {
    return false;
  }
  const item = value as Record<string, unknown>;
  if (item.type === "reasoning") {
    return typeof item.key === "string" && typeof item.content === "string";
  }
  if (item.type === "status") {
    return typeof item.key === "string" && typeof item.label === "string";
  }
  if (item.type === "summary") {
    return typeof item.key === "string" && typeof item.content === "string";
  }
  if (item.type === "error") {
    return typeof item.key === "string" && typeof item.message === "string";
  }
  if (item.type === "assistant") {
    return typeof item.key === "string" && typeof item.content === "string";
  }
  return (
    item.type === "tool" &&
    typeof item.key === "string" &&
    typeof item.toolCallId === "string" &&
    typeof item.label === "string" &&
    (item.status === "running" || item.status === "completed")
  );
}
