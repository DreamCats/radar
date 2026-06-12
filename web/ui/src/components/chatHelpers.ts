import type { ChatMessageItem } from "../types";

const ACTIVE_SESSION_KEY = "radar.chat.activeSessionId";
const SELECTED_PROVIDER_KEY = "radar.chat.selectedProviderName";

export type ToolActivityItem = {
  key: string;
  label: string;
  status: "running" | "completed";
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
    radar_get_stock_price_history: "行情数据",
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
      reasoning: draft.metadata.reasoning,
      tool_activities: draft.metadata.tool_activities,
      status: "正在处理",
      streaming: true,
    },
  };
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
    label: `${eventType === "tool_execution_started" ? "调用" : "完成"} ${formatToolName(toolName)}`,
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
