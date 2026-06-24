import type { Dispatch, SetStateAction } from "react";

import type { ChatMessageItem, ChatStreamEvent } from "../types";
import {
  MODEL_THINKING_STATUS,
  appendAssistantTrace,
  appendErrorTrace,
  appendStatusTrace,
  appendSummaryTrace,
  completedStatus,
  durationMsValue,
  ensureAssistantTrace,
  mergeAssistantMetadata,
  removeTraceItem,
  statusForAgentEvent,
  updateToolActivities,
  updateToolTrace,
  upsertAssistantTrace,
  upsertStatusTrace,
} from "./chatHelpers";

type ChatStreamHandlerOptions = {
  assistantDraftId: string;
  userDraftId?: string;
  setMessages: Dispatch<SetStateAction<ChatMessageItem[]>>;
  clearIdleTimer: () => void;
  scheduleIdleStatus: (status?: string) => void;
  onSession: (sessionId: string) => void;
  onFollowUpSuggestion?: (suggestion: string | null) => void;
};

const PENDING_ASSISTANT_STATUS_KEY = "assistant-progress-pending";
const ASSISTANT_CANDIDATE_KEY = "assistant-candidate";

export function createChatStreamHandler({
  assistantDraftId,
  userDraftId,
  setMessages,
  clearIdleTimer,
  scheduleIdleStatus,
  onSession,
  onFollowUpSuggestion,
}: ChatStreamHandlerOptions): (event: ChatStreamEvent) => void {
  let pendingProgressContent = "";
  let pendingCandidateContent = "";
  let toolResultSummaryAdded = false;
  let turnStartedAtMs: number | null = null;

  return (event) => {
    if (event.type === "ping") {
      return;
    }
    if (event.type === "session") {
      onSession(event.session_id);
      return;
    }
    if (event.type === "user_message") {
      const message = event.message;
      setMessages((current) => {
        if (current.some((item) => item.message_id === message.message_id || item.metadata.server_message_id === message.message_id)) {
          return current;
        }
        if (userDraftId) {
          let replaced = false;
          const next = current.map((item) => {
            if (item.message_id !== userDraftId) {
              return item;
            }
            replaced = true;
            return { ...message, metadata: { ...message.metadata, server_message_id: message.message_id } };
          });
          return replaced ? next : [...current, message];
        }
        return [...current, message];
      });
      return;
    }
    if (event.type === "error") {
      clearIdleTimer();
      setMessages((current) =>
        current.map((message) =>
          message.message_id === assistantDraftId
            ? {
                ...message,
                metadata: {
                  ...message.metadata,
                  status: "处理失败",
                  streaming: false,
                  trace_items: appendErrorTrace(message.metadata.trace_items, event.message),
                },
              }
            : message,
        ),
      );
      return;
    }
    if (event.type === "assistant_delta") {
      if (!event.content) return;
      pendingCandidateContent = "";
      clearIdleTimer();
      setMessages((current) =>
        current.map((message) =>
          message.message_id === assistantDraftId ? appendFinalAssistantDelta(message, event.content) : message,
        ),
      );
      scheduleIdleStatus("仍在处理");
      return;
    }
    if (event.type === "assistant_candidate_delta") {
      if (!event.content) return;
      pendingCandidateContent = `${pendingCandidateContent}${event.content}`;
      clearIdleTimer();
      setMessages((current) =>
        current.map((message) =>
          message.message_id === assistantDraftId ? upsertCandidateAssistant(message, pendingCandidateContent) : message,
        ),
      );
      scheduleIdleStatus("正在生成回答");
      return;
    }
    if (event.type === "assistant_candidate_commit") {
      const content = event.content || pendingCandidateContent;
      if (!content) return;
      pendingCandidateContent = "";
      clearIdleTimer();
      setMessages((current) =>
        current.map((message) => (message.message_id === assistantDraftId ? commitCandidateAssistant(message, content) : message)),
      );
      scheduleIdleStatus("仍在处理");
      return;
    }
    if (event.type === "assistant_candidate_discard") {
      const content = event.content || pendingCandidateContent;
      pendingCandidateContent = "";
      pendingProgressContent = content;
      clearIdleTimer();
      setMessages((current) =>
        current.map((message) => (message.message_id === assistantDraftId ? discardCandidateAssistant(message, content) : message)),
      );
      scheduleIdleStatus("正在查询本地数据");
      return;
    }
    if (event.type === "assistant_progress_delta") {
      if (!event.content) return;
      pendingProgressContent = `${pendingProgressContent}${event.content}`;
      clearIdleTimer();
      setMessages((current) =>
        current.map((message) =>
          message.message_id === assistantDraftId ? appendProgressDelta(message, pendingProgressContent) : message,
        ),
      );
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
                  status: MODEL_THINKING_STATUS,
                  streaming: true,
                },
              }
            : message,
        ),
      );
      scheduleIdleStatus(MODEL_THINKING_STATUS);
      return;
    }
    if (event.type === "assistant_message") {
      const message = event.message;
      const messageHasToolCalls = hasToolCalls(message);
      clearIdleTimer();
      if (messageHasToolCalls) {
        setMessages((current) =>
          current.map((item) =>
            item.message_id === assistantDraftId
              ? mergeToolRoundAssistantMessage(item, message, pendingProgressContent)
              : item,
          ),
        );
        pendingProgressContent = "";
        scheduleIdleStatus("正在查询本地数据");
        return;
      }
      const finalContent = message.content.trim();
      if (!finalContent.trim()) {
        pendingProgressContent = "";
        scheduleIdleStatus("正在处理");
        return;
      }
      setMessages((current) =>
        current.map((item) =>
          item.message_id === assistantDraftId ? mergeFinalAssistantMessage(item, message) : item,
        ),
      );
      const suggestion = readFollowUpSuggestion(message.metadata.follow_up_suggestion);
      if (suggestion) {
        onFollowUpSuggestion?.(suggestion);
      }
      pendingProgressContent = "";
      scheduleIdleStatus("正在继续处理");
      return;
    }
    if (event.type === "tool_message") {
      clearIdleTimer();
      setMessages((current) =>
        current.map((message) =>
          message.message_id === assistantDraftId
            ? {
                ...message,
                metadata: {
                  ...message.metadata,
                  streaming: true,
                  status: "正在整理结果",
                  trace_items: toolResultSummaryAdded
                    ? message.metadata.trace_items
                    : appendSummaryTrace(message.metadata.trace_items, "工具结果开始返回，我会把新增数据并入判断。"),
                },
              }
            : message,
        ),
      );
      toolResultSummaryAdded = true;
      scheduleIdleStatus(MODEL_THINKING_STATUS);
      return;
    }
    if (event.type !== "agent_event") {
      return;
    }

    const eventType = typeof event.event.type === "string" ? event.event.type : "";
    const payload = typeof event.event.payload === "object" && event.event.payload ? (event.event.payload as Record<string, unknown>) : {};
    const eventCreatedAtMs = timestampMs(event.event.created_at);
    if (eventType === "turn_started") {
      turnStartedAtMs = eventCreatedAtMs ?? Date.now();
    }
    const toolName = "tool_name" in payload && typeof payload.tool_name === "string" ? payload.tool_name : "";
    const toolCallId = "tool_call_id" in payload && typeof payload.tool_call_id === "string" ? payload.tool_call_id : toolName;
    const toolMessageId = "tool_message_id" in payload && typeof payload.tool_message_id === "string" ? payload.tool_message_id : "";
    if (eventType === "turn_completed") {
      const durationMs = durationMsValue(payload.duration_ms) ?? elapsedDurationMs(turnStartedAtMs, eventCreatedAtMs ?? Date.now());
      clearIdleTimer();
      setMessages((current) =>
        current.map((message) =>
          message.message_id === assistantDraftId
            ? {
                ...message,
                metadata: {
                  ...message.metadata,
                  ...(durationMs === null ? {} : { duration_ms: durationMs }),
                  status: completedStatus(durationMs),
                  streaming: false,
                },
              }
            : message,
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
                tool_activities: updateToolActivities(message.metadata.tool_activities, eventType, toolCallId, toolName, toolMessageId),
                trace_items: traceForAgentEvent(message.metadata.trace_items, eventType, toolCallId, toolName, toolMessageId, status),
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

function appendFinalAssistantDelta(message: ChatMessageItem, content: string): ChatMessageItem {
  return {
    ...message,
    content: `${message.content}${content}`,
    metadata: {
      ...message.metadata,
      status: "正在生成回答",
      streaming: true,
      trace_items: appendAssistantTrace(
        removeTraceItem(removeTraceItem(message.metadata.trace_items, PENDING_ASSISTANT_STATUS_KEY), ASSISTANT_CANDIDATE_KEY),
        content,
      ),
    },
  };
}

function upsertCandidateAssistant(message: ChatMessageItem, content: string): ChatMessageItem {
  return {
    ...message,
    metadata: {
      ...message.metadata,
      status: "正在生成回答",
      streaming: true,
      trace_items: upsertAssistantTrace(message.metadata.trace_items, ASSISTANT_CANDIDATE_KEY, content),
    },
  };
}

function commitCandidateAssistant(message: ChatMessageItem, content: string): ChatMessageItem {
  const baseTrace = removeTraceItem(removeTraceItem(message.metadata.trace_items, ASSISTANT_CANDIDATE_KEY), PENDING_ASSISTANT_STATUS_KEY);
  return {
    ...message,
    content,
    metadata: {
      ...message.metadata,
      status: "正在生成回答",
      streaming: true,
      trace_items: appendAssistantTrace(baseTrace, content),
    },
  };
}

function discardCandidateAssistant(message: ChatMessageItem, content: string): ChatMessageItem {
  const baseTrace = removeTraceItem(removeTraceItem(message.metadata.trace_items, ASSISTANT_CANDIDATE_KEY), PENDING_ASSISTANT_STATUS_KEY);
  return {
    ...message,
    metadata: {
      ...message.metadata,
      status: "正在查询本地数据",
      streaming: true,
      trace_items: content.trim() ? appendStatusTrace(baseTrace, content) : baseTrace,
    },
  };
}

function appendProgressDelta(message: ChatMessageItem, content: string): ChatMessageItem {
  return {
    ...message,
    metadata: {
      ...message.metadata,
      status: "正在生成回答",
      streaming: true,
      trace_items: upsertStatusTrace(message.metadata.trace_items, PENDING_ASSISTANT_STATUS_KEY, content),
    },
  };
}

function mergeToolRoundAssistantMessage(draft: ChatMessageItem, message: ChatMessageItem, pendingContent: string): ChatMessageItem {
  const processContent = (pendingContent || message.content).trim();
  const baseTrace = removeTraceItem(removeTraceItem(draft.metadata.trace_items, PENDING_ASSISTANT_STATUS_KEY), ASSISTANT_CANDIDATE_KEY);
  const traceItems = processContent
    ? appendStatusTrace(baseTrace, processContent)
    : appendSummaryTrace(baseTrace, "我会先准备要查的数据，再按证据强度比较。");
  return {
    ...draft,
    metadata: {
      ...draft.metadata,
      ...message.metadata,
      server_message_id: message.message_id,
      tool_activities: draft.metadata.tool_activities,
      trace_items: traceItems,
      streaming: true,
      status: "正在查询本地数据",
    },
  };
}

function mergeFinalAssistantMessage(draft: ChatMessageItem, message: ChatMessageItem): ChatMessageItem {
  const normalizedDraft = {
    ...draft,
    metadata: {
      ...draft.metadata,
      trace_items: removeTraceItem(removeTraceItem(draft.metadata.trace_items, PENDING_ASSISTANT_STATUS_KEY), ASSISTANT_CANDIDATE_KEY),
    },
  };
  return ensureMergedAssistantTrace(mergeAssistantMetadata(normalizedDraft, message));
}

function hasToolCalls(message: ChatMessageItem): boolean {
  const toolCalls = message.metadata.tool_calls;
  return Array.isArray(toolCalls) && toolCalls.length > 0;
}

function traceForAgentEvent(
  raw: unknown,
  eventType: string,
  toolCallId: string,
  toolName: string,
  toolMessageId: string,
  status: string,
) {
  if (eventType === "turn_started") {
    return appendSummaryTrace(appendStatusTrace(raw, status), "我会先拆解你的问题，确定需要查哪些证据。");
  }
  if (eventType === "tool_execution_started") {
    const phaseSummary = summaryForToolPhase(toolName);
    return updateToolTrace(
      phaseSummary ? appendSummaryTrace(raw, phaseSummary) : raw,
      eventType,
      toolCallId,
      toolName,
      toolMessageId,
    );
  }
  return updateToolTrace(raw, eventType, toolCallId, toolName, toolMessageId);
}

function summaryForToolPhase(toolName: string): string {
  const normalizedName = toolName.toLowerCase();
  if (containsAny(normalizedName, ["strategy", "candidate", "theme", "dashboard", "策略", "候选", "主题"])) {
    return "我会先从策略候选里拿到可比较的标的池。";
  }
  if (containsAny(normalizedName, ["evidence", "证据"])) {
    return "我会补证据链详情，检查触发、验证点和暂缓条件。";
  }
  if (containsAny(normalizedName, ["message", "conversation", "context", "overview", "消息", "会话", "上下文"])) {
    return "我会回到本地消息里补原文证据、来源密度和反证。";
  }
  if (
    containsAny(normalizedName, [
      "stock",
      "price",
      "market",
      "sector",
      "moneyflow",
      "limit",
      "backtest",
      "行情",
      "资金",
      "板块",
      "涨停",
      "回测",
    ])
  ) {
    return "我会补行情和资金流，确认市场是否已经定价。";
  }
  if (containsAny(normalizedName, ["skill", "load", "模板", "技能"])) {
    return "我会补必要的分析模板，再把结果整理成结论。";
  }
  return "我会补齐下一步判断需要的数据。";
}

function containsAny(value: string, patterns: string[]): boolean {
  return patterns.some((pattern) => value.includes(pattern));
}

function ensureMergedAssistantTrace(message: ChatMessageItem): ChatMessageItem {
  return {
    ...message,
    metadata: {
      ...message.metadata,
      trace_items: ensureAssistantTrace(message.metadata.trace_items, message.content),
    },
  };
}

function timestampMs(value: unknown): number | null {
  if (typeof value !== "string") {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function elapsedDurationMs(startedAtMs: number | null, completedAtMs: number): number | null {
  if (startedAtMs === null || !Number.isFinite(completedAtMs) || completedAtMs < startedAtMs) {
    return null;
  }
  return Math.round(completedAtMs - startedAtMs);
}

function readFollowUpSuggestion(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const suggestion = value.trim();
  return suggestion ? suggestion : null;
}
