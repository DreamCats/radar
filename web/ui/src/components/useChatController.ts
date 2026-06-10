import { useEffect, useRef, useState } from "react";

import { deleteChatSession, fetchChatModelOptions, fetchChatSession, fetchChatSessions, streamChatTurn } from "../api/radarApi";
import { formatChatTranscript } from "../lib/chatTranscript";
import { copyText } from "../lib/clipboard";
import type { ChatMessageItem, ChatModelOption, ChatSessionItem } from "../types";
import {
  clearActiveSessionId,
  clearSelectedProviderName,
  formatToolName,
  mergeAssistantMetadata,
  readActiveSessionId,
  readSelectedProviderName,
  statusForAgentEvent,
  updateToolActivities,
  writeActiveSessionId,
  writeSelectedProviderName,
} from "./chatHelpers";
import type { ChatController, ChatSurfaceProps } from "./chatTypes";

export function useChatController(props: ChatSurfaceProps, active: boolean): ChatController {
  const [draft, setDraft] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [sessions, setSessions] = useState<ChatSessionItem[]>([]);
  const [modelOptions, setModelOptions] = useState<ChatModelOption[]>([]);
  const [selectedProviderName, setSelectedProviderName] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const idleTimerRef = useRef<number | null>(null);
  const autoFollowBottomRef = useRef(true);
  const messageListRef = useRef<HTMLDivElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const [autoFollowBottom, setAutoFollowBottom] = useState(true);
  const [hasNewMessagesBelow, setHasNewMessagesBelow] = useState(false);
  const visibleContext = props.context.filter((item) => item.value !== undefined && item.value !== null && `${item.value}`.trim() !== "");

  useEffect(() => {
    if (!active) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      if (autoFollowBottomRef.current) {
        scrollMessageListToBottom(false);
        setHasNewMessagesBelow(false);
        return;
      }
      if (messages.length > 0) {
        setHasNewMessagesBelow(true);
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [messages, active, sending]);

  useEffect(() => {
    if (!active) {
      return;
    }
    setBottomFollowMode(true);
    setHasNewMessagesBelow(false);
    void refreshSessions();
    void refreshModelOptions();
    if (!sessionId && messages.length === 0) {
      const activeSessionId = readActiveSessionId();
      if (activeSessionId) {
        void restoreSession(activeSessionId);
      }
    }
  }, [active]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      clearIdleTimer();
    };
  }, []);

  function clearIdleTimer() {
    if (idleTimerRef.current === null) {
      return;
    }
    window.clearTimeout(idleTimerRef.current);
    idleTimerRef.current = null;
  }

  function setBottomFollowMode(nextValue: boolean) {
    autoFollowBottomRef.current = nextValue;
    setAutoFollowBottom((current) => (current === nextValue ? current : nextValue));
  }

  function scrollMessageListToBottom(smooth: boolean) {
    const list = messageListRef.current;
    if (!list) {
      return;
    }
    if (smooth) {
      list.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
      return;
    }
    list.scrollTop = list.scrollHeight;
  }

  function updateMessageScrollState(isNearBottom: boolean) {
    setBottomFollowMode(isNearBottom);
    if (isNearBottom) {
      setHasNewMessagesBelow(false);
    }
  }

  function jumpToLatestMessage() {
    setBottomFollowMode(true);
    setHasNewMessagesBelow(false);
    scrollMessageListToBottom(true);
  }

  async function submitTurn() {
    const content = draft.trim();
    if (!content || sending) {
      return;
    }
    setBottomFollowMode(true);
    setHasNewMessagesBelow(false);
    setSending(true);
    setError(null);
    setDraft("");
    const userDraftId = `user-local-${Date.now()}`;
    const assistantDraftId = `assistant-stream-${Date.now()}`;
    const selectedModelOption = modelOptions.find((item) => item.provider_name === selectedProviderName) ?? null;
    let assistantRoundClosed = false;
    const controller = new AbortController();
    abortControllerRef.current = controller;
    const scheduleIdleStatus = (status = "仍在处理") => {
      clearIdleTimer();
      idleTimerRef.current = window.setTimeout(() => {
        setMessages((current) =>
          current.map((message) =>
            message.message_id === assistantDraftId && message.metadata.streaming
              ? { ...message, metadata: { ...message.metadata, status } }
              : message,
          ),
        );
        idleTimerRef.current = null;
      }, 1000);
    };
    setMessages((current) => [
      ...current,
      {
        message_id: userDraftId,
        role: "user",
        content,
        created_at: new Date().toISOString(),
        metadata: {
          local: true,
          llm: selectedModelOption
            ? { provider_name: selectedModelOption.provider_name, model: selectedModelOption.model, protocol: selectedModelOption.protocol }
            : {},
        },
      },
      {
        message_id: assistantDraftId,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
        metadata: { streaming: true },
      },
    ]);
    scheduleIdleStatus("正在准备");
    try {
      await streamChatTurn(
        {
          session_id: sessionId,
          title: props.title,
          content,
          provider_name: selectedProviderName,
          context: {
            surface: props.surface,
            entity_id: props.entityId,
            title: props.title,
            subtitle: props.subtitle,
            fields: visibleContext,
            evidence: props.evidence ?? [],
          },
          metadata: {
            surface: props.surface,
            entity_id: props.entityId,
            title: props.title,
            chat_provider_name: selectedProviderName,
            chat_model: selectedModelOption?.model,
          },
        },
        (event) => {
          if (event.type === "session") {
            setSessionId(event.session_id);
            writeActiveSessionId(event.session_id);
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
          if (event.type === "agent_event") {
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
          }
        },
        { signal: controller.signal },
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setError(null);
      } else {
        setError(err instanceof Error ? err.message : "发送失败");
      }
      setMessages((current) =>
        current
          .filter((message) => message.message_id !== assistantDraftId || message.content.trim())
          .map((message) =>
            message.message_id === assistantDraftId ? { ...message, metadata: { ...message.metadata, streaming: false, stopped: true } } : message,
          ),
      );
    } finally {
      clearIdleTimer();
      abortControllerRef.current = null;
      setSending(false);
      void refreshSessions();
    }
  }

  function stopStreaming() {
    abortControllerRef.current?.abort();
  }

  function changeProvider(providerName: string | null) {
    setSelectedProviderName(providerName);
    if (!providerName) {
      clearSelectedProviderName();
      return;
    }
    writeSelectedProviderName(providerName);
  }

  async function refreshSessions() {
    setLoadingSessions(true);
    try {
      const data = await fetchChatSessions();
      setSessions(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取历史失败");
    } finally {
      setLoadingSessions(false);
    }
  }

  async function refreshModelOptions() {
    try {
      const data = await fetchChatModelOptions();
      setModelOptions(data.items);
      setSelectedProviderName((current) => {
        if (current && data.items.some((item) => item.provider_name === current)) return current;
        const saved = readSelectedProviderName();
        if (saved && data.items.some((item) => item.provider_name === saved)) return saved;
        if (saved) clearSelectedProviderName();
        return data.default_provider_name ?? data.items[0]?.provider_name ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取模型配置失败");
    }
  }

  async function restoreSession(nextSessionId: string) {
    try {
      const data = await fetchChatSession(nextSessionId);
      setBottomFollowMode(true);
      setHasNewMessagesBelow(false);
      setSessionId(data.session.session_id);
      setMessages(data.messages);
      writeActiveSessionId(data.session.session_id);
      setHistoryOpen(false);
      setError(null);
    } catch (err) {
      clearActiveSessionId();
      setError(err instanceof Error ? err.message : "恢复对话失败");
    }
  }

  function startNewSession() {
    abortControllerRef.current?.abort();
    clearActiveSessionId();
    setBottomFollowMode(true);
    setHasNewMessagesBelow(false);
    setSessionId(null);
    setMessages([]);
    setDraft("");
    setError(null);
    setHistoryOpen(false);
  }

  async function copySessionId(nextSessionId: string) {
    try {
      await copyText(nextSessionId);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "复制失败");
    }
  }

  async function copySessionTitle(session: ChatSessionItem) {
    try {
      await copyText(session.title?.trim() || "未命名对话");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "复制失败");
    }
  }

  async function copySessionContent(nextSessionId: string) {
    try {
      const data = await fetchChatSession(nextSessionId);
      await copyText(formatChatTranscript(data));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "复制内容失败");
    }
  }

  async function removeSession(nextSessionId: string) {
    try {
      if (nextSessionId === sessionId) abortControllerRef.current?.abort();
      await deleteChatSession(nextSessionId);
      if (nextSessionId === sessionId) {
        clearActiveSessionId();
        setBottomFollowMode(true);
        setHasNewMessagesBelow(false);
        setSessionId(null);
        setMessages([]);
      }
      await refreshSessions();
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除对话失败");
    }
  }

  return {
    activeSessionId: sessionId,
    autoFollowBottom,
    draft,
    error,
    hasNewMessagesBelow,
    historyOpen,
    loadingSessions,
    messageListRef,
    messages,
    messagesEndRef,
    modelOptions,
    selectedProviderName,
    sending,
    sessions,
    visibleContext,
    changeProvider,
    copySessionContent,
    copySessionId,
    copySessionTitle,
    jumpToLatestMessage,
    refreshSessions,
    removeSession,
    restoreSession,
    setDraft,
    setHistoryOpen,
    startNewSession,
    stopStreaming,
    submitTurn,
    updateMessageScrollState,
  };
}
