import type { Dispatch, SetStateAction } from "react";

import type { ChatMessageItem, ChatStreamEvent } from "../types";
import { formatToolName, mergeAssistantMetadata, statusForAgentEvent, updateToolActivities } from "./chatHelpers";

type ChatStreamHandlerOptions = {
  assistantDraftId: string;
  setMessages: Dispatch<SetStateAction<ChatMessageItem[]>>;
  clearIdleTimer: () => void;
  scheduleIdleStatus: (status?: string) => void;
  onSession: (sessionId: string) => void;
};

export function createChatStreamHandler({
  assistantDraftId,
  setMessages,
  clearIdleTimer,
  scheduleIdleStatus,
  onSession,
}: ChatStreamHandlerOptions): (event: ChatStreamEvent) => void {
  let assistantRoundClosed = false;

  return (event) => {
    if (event.type === "session") {
      onSession(event.session_id);
      return;
    }
    if (event.type === "assistant_delta") {
      if (!event.content) return;
      clearIdleTimer();
      setMessages((current) =>
        current.map((message) =>
          message.message_id === assistantDraftId
            ? {
                ...message,
                content: `${message.content}${assistantRoundClosed && message.content.trim() ? "\n\n" : ""}${event.content}`,
                metadata: { ...message.metadata, status: "正在生成回答", streaming: true },
              }
            : message,
        ),
      );
      assistantRoundClosed = false;
      scheduleIdleStatus("仍在处理");
      return;
    }
    if (event.type === "assistant_reasoning_delta") {
      if (!event.content) return;
      clearIdleTimer();
      setMessages((current) =>
        current.map((message) =>
          message.message_id === assistantDraftId
            ? {
                ...message,
                metadata: {
                  ...message.metadata,
                  reasoning: `${typeof message.metadata.reasoning === "string" ? message.metadata.reasoning : ""}${event.content}`,
                  status: "正在推理",
                  streaming: true,
                },
              }
            : message,
        ),
      );
      scheduleIdleStatus("正在推理");
      return;
    }
    if (event.type === "assistant_message") {
      const message = event.message;
      clearIdleTimer();
      if (!message.content.trim()) {
        setMessages((current) =>
          current.map((item) =>
            item.message_id === assistantDraftId
              ? { ...item, metadata: { ...item.metadata, streaming: true, status: "正在查询本地数据" } }
              : item,
          ),
        );
        scheduleIdleStatus("正在查询本地数据");
        return;
      }
      setMessages((current) => current.map((item) => (item.message_id === assistantDraftId ? mergeAssistantMetadata(item, message) : item)));
      assistantRoundClosed = true;
      scheduleIdleStatus("正在继续处理");
      return;
    }
    if (event.type === "tool_message") {
      const toolName = typeof event.message.metadata.tool_name === "string" ? event.message.metadata.tool_name : "工具";
      clearIdleTimer();
      setMessages((current) =>
        current.map((message) =>
          message.message_id === assistantDraftId
            ? { ...message, metadata: { ...message.metadata, streaming: true, status: `已读取 ${formatToolName(toolName)}` } }
            : message,
        ),
      );
      scheduleIdleStatus("正在整理结果");
      return;
    }
    if (event.type !== "agent_event") {
      return;
    }

    const eventType = typeof event.event.type === "string" ? event.event.type : "";
    const payload = typeof event.event.payload === "object" && event.event.payload ? event.event.payload : {};
    const toolName = "tool_name" in payload && typeof payload.tool_name === "string" ? payload.tool_name : "";
    const toolCallId = "tool_call_id" in payload && typeof payload.tool_call_id === "string" ? payload.tool_call_id : toolName;
    if (eventType === "turn_completed") {
      clearIdleTimer();
      setMessages((current) =>
        current.map((message) =>
          message.message_id === assistantDraftId ? { ...message, metadata: { ...message.metadata, status: "已处理", streaming: false } } : message,
        ),
      );
      return;
    }
    const status = statusForAgentEvent(eventType, toolName);
    if (!status) {
      return;
    }
    clearIdleTimer();
    setMessages((current) =>
      current.map((message) =>
        message.message_id === assistantDraftId
          ? {
              ...message,
              metadata: {
                ...message.metadata,
                streaming: true,
                status,
                tool_activities: updateToolActivities(message.metadata.tool_activities, eventType, toolCallId, toolName),
              },
            }
          : message,
      ),
    );
    if (eventType === "turn_started") {
      scheduleIdleStatus("正在准备查询");
    }
  };
}
