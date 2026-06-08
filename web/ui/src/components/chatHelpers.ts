import type { ChatMessageItem } from "../types";

const ACTIVE_SESSION_KEY = "radar.chat.activeSessionId";

export type ToolActivityItem = {
  key: string;
  label: string;
  status: "running" | "completed";
};

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
    radar_source_signals: "源头信号",
    radar_strategy_dashboard: "策略看板",
  };
  return labels[toolName] ?? (toolName || "工具");
}

export function mergeAssistantMetadata(draft: ChatMessageItem, message: ChatMessageItem): ChatMessageItem {
  return {
    ...message,
    metadata: {
      ...message.metadata,
      reasoning: draft.metadata.reasoning,
      tool_activities: draft.metadata.tool_activities,
      status: "已处理",
      streaming: false,
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
