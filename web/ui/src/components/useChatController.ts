import { useEffect, useRef, useState } from "react";

import { continueChatTurn, deleteChatSession, fetchChatModelOptions, fetchChatSession, fetchChatSessions, streamChatTurn } from "../api/radarApi";
import { formatChatTranscript } from "../lib/chatTranscript";
import { copyText } from "../lib/clipboard";
import type { ChatMessageItem, ChatModelOption, ChatSessionItem } from "../types";
import {
  appendErrorTrace,
  chatTraceItems,
  clearActiveSessionId,
  clearSelectedProviderName,
  completedStatus,
  readActiveSessionId,
  readSelectedProviderName,
  writeActiveSessionId,
  writeSelectedProviderName,
} from "./chatHelpers";
import { createChatStreamHandler } from "./chatStreamHandler";
import type { ChatController, ChatSurfaceProps } from "./chatTypes";

export function useChatController(props: ChatSurfaceProps, active: boolean): ChatController {
  const [draft, setDraft] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [sessions, setSessions] = useState<ChatSessionItem[]>([]);
  const [modelOptions, setModelOptions] = useState<ChatModelOption[]>([]);
  const [selectedProviderName, setSelectedProviderName] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [followUpSuggestion, setFollowUpSuggestion] = useState<string | null>(null);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [sessionAction, setSessionAction] = useState<{ label: string; sessionId: string } | null>(null);
  const [canContinue, setCanContinue] = useState(false);
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
  const composerHidden = false;

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

  function stopAssistantDraft(assistantDraftId: string, errorMessage: string | null) {
    setMessages((current) =>
      current
        .map((message) => {
          if (message.message_id !== assistantDraftId) {
            return message;
          }
          const metadata = {
            ...message.metadata,
            streaming: false,
            stopped: true,
            ...(errorMessage ? { status: "处理失败", trace_items: appendErrorTrace(message.metadata.trace_items, errorMessage) } : {}),
          };
          return { ...message, metadata };
        })
        .filter(
          (message) =>
            message.message_id !== assistantDraftId ||
            message.content.trim() ||
            chatTraceItems(message.metadata.trace_items).length > 0,
        ),
    );
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
    setCanContinue(false);
    setFollowUpSuggestion(null);
    setDraft("");
    const userDraftId = `user-local-${Date.now()}`;
    const assistantDraftId = `assistant-stream-${Date.now()}`;
    const selectedModelOption = modelOptions.find((item) => item.provider_name === selectedProviderName) ?? null;
    let currentSessionId = sessionId;
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
    const handleStreamEvent = createChatStreamHandler({
      assistantDraftId,
      setMessages,
      clearIdleTimer,
      scheduleIdleStatus,
      onSession: (nextSessionId) => {
        currentSessionId = nextSessionId;
        setSessionId(nextSessionId);
        writeActiveSessionId(nextSessionId);
      },
      onFollowUpSuggestion: setFollowUpSuggestion,
    });
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
        handleStreamEvent,
        { signal: controller.signal },
      );
      setCanContinue(false);
    } catch (err) {
      const errorMessage = chatTurnErrorMessage(err, "发送失败");
      if (isChatStreamNetworkError(err) && currentSessionId && (await recoverCompletedTurn(currentSessionId, assistantDraftId))) {
        return;
      }
      setError(null);
      stopAssistantDraft(assistantDraftId, errorMessage);
      setCanContinue(Boolean(currentSessionId));
    } finally {
      clearIdleTimer();
      abortControllerRef.current = null;
      setSending(false);
      void refreshSessions();
    }
  }

  async function continueTurn() {
    if (!sessionId || sending) {
      return;
    }
    setBottomFollowMode(true);
    setHasNewMessagesBelow(false);
    setSending(true);
    setError(null);
    setCanContinue(false);
    setFollowUpSuggestion(null);
    const assistantDraftId = `assistant-stream-${Date.now()}`;
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
        message_id: assistantDraftId,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
        metadata: { streaming: true, resumed: true },
      },
    ]);
    scheduleIdleStatus("正在继续");
    const handleStreamEvent = createChatStreamHandler({
      assistantDraftId,
      setMessages,
      clearIdleTimer,
      scheduleIdleStatus,
      onSession: (nextSessionId) => {
        setSessionId(nextSessionId);
        writeActiveSessionId(nextSessionId);
      },
      onFollowUpSuggestion: setFollowUpSuggestion,
    });
    try {
      await continueChatTurn(sessionId, { provider_name: selectedProviderName }, handleStreamEvent, { signal: controller.signal });
      setCanContinue(false);
    } catch (err) {
      const errorMessage = chatTurnErrorMessage(err, "继续生成失败");
      if (isChatStreamNetworkError(err) && (await recoverCompletedTurn(sessionId, assistantDraftId))) {
        return;
      }
      setError(null);
      stopAssistantDraft(assistantDraftId, errorMessage);
      setCanContinue(true);
    } finally {
      clearIdleTimer();
      abortControllerRef.current = null;
      setSending(false);
      void refreshSessions();
    }
  }

  function stopStreaming() {
    abortControllerRef.current?.abort();
    setFollowUpSuggestion(null);
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
    setSessionAction({ sessionId: nextSessionId, label: "打开中" });
    try {
      const data = await fetchChatSession(nextSessionId);
      setBottomFollowMode(true);
      setHasNewMessagesBelow(false);
      setSessionId(data.session.session_id);
      setMessages(data.messages);
      setCanContinue(data.session.can_continue);
      setFollowUpSuggestion(data.session.can_continue ? null : followUpSuggestionFromMessages(data.messages));
      writeActiveSessionId(data.session.session_id);
      setHistoryOpen(false);
      setError(null);
    } catch (err) {
      clearActiveSessionId();
      setError(err instanceof Error ? err.message : "恢复对话失败");
    } finally {
      setSessionAction((current) => (current?.sessionId === nextSessionId ? null : current));
    }
  }

  async function recoverCompletedTurn(nextSessionId: string, assistantDraftId: string): Promise<boolean> {
    try {
      const data = await fetchChatSession(nextSessionId);
      if (data.session.can_continue) {
        return false;
      }
      setSessionId(data.session.session_id);
      writeActiveSessionId(data.session.session_id);
      setCanContinue(false);
      setFollowUpSuggestion(followUpSuggestionFromMessages(data.messages));
      setError(null);
      if (hasVisibleAssistantAnswer(data.messages)) {
        setMessages(data.messages);
        return true;
      }
      setMessages((current) =>
        current.map((message) =>
          message.message_id === assistantDraftId
            ? {
                ...message,
                metadata: {
                  ...message.metadata,
                  status: completedStatus(message.metadata.duration_ms),
                  streaming: false,
                },
              }
            : message,
        ),
      );
      return true;
    } catch {
      return false;
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
    setCanContinue(false);
    setFollowUpSuggestion(null);
    setError(null);
    setHistoryOpen(false);
  }

  async function copySessionId(nextSessionId: string) {
    setSessionAction({ sessionId: nextSessionId, label: "复制中" });
    try {
      await copyText(nextSessionId);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "复制失败");
    } finally {
      setSessionAction((current) => (current?.sessionId === nextSessionId ? null : current));
    }
  }

  async function copySessionTitle(session: ChatSessionItem) {
    setSessionAction({ sessionId: session.session_id, label: "复制中" });
    try {
      await copyText(session.title?.trim() || "未命名对话");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "复制失败");
    } finally {
      setSessionAction((current) => (current?.sessionId === session.session_id ? null : current));
    }
  }

  async function copySessionContent(nextSessionId: string) {
    setSessionAction({ sessionId: nextSessionId, label: "复制内容中" });
    try {
      const data = await fetchChatSession(nextSessionId);
      await copyText(formatChatTranscript(data));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "复制内容失败");
    } finally {
      setSessionAction((current) => (current?.sessionId === nextSessionId ? null : current));
    }
  }

  async function removeSession(nextSessionId: string) {
    setSessionAction({ sessionId: nextSessionId, label: "删除中" });
    try {
      if (nextSessionId === sessionId) abortControllerRef.current?.abort();
      await deleteChatSession(nextSessionId);
      if (nextSessionId === sessionId) {
        clearActiveSessionId();
        setBottomFollowMode(true);
        setHasNewMessagesBelow(false);
        setSessionId(null);
        setMessages([]);
        setCanContinue(false);
        setFollowUpSuggestion(null);
      }
      await refreshSessions();
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除对话失败");
    } finally {
      setSessionAction((current) => (current?.sessionId === nextSessionId ? null : current));
    }
  }

  return {
    activeSessionId: sessionId,
    autoFollowBottom,
    canContinue,
    draft,
    error,
    followUpSuggestion,
    hasNewMessagesBelow,
    composerHidden,
    historyOpen,
    loadingSessions,
    messageListRef,
    messages,
    messagesEndRef,
    modelOptions,
    selectedProviderName,
    sessionAction,
    sending,
    sessions,
    visibleContext,
    changeProvider,
    continueTurn,
    copySessionContent,
    copySessionId,
    copySessionTitle,
    jumpToLatestMessage,
    refreshSessions,
    removeSession,
    restoreSession,
    acceptFollowUpSuggestion,
    dismissFollowUpSuggestion,
    setDraft: updateDraft,
    setHistoryOpen,
    startNewSession,
    stopStreaming,
    submitTurn,
    updateMessageScrollState,
  };

  function acceptFollowUpSuggestion() {
    const suggestion = readFollowUpSuggestion(followUpSuggestion);
    if (!suggestion) {
      return;
    }
    setDraft(suggestion);
    setFollowUpSuggestion(null);
  }

  function dismissFollowUpSuggestion() {
    setFollowUpSuggestion(null);
  }

  function updateDraft(value: string) {
    setDraft(value);
    if (value.trim()) {
      setFollowUpSuggestion(null);
    }
  }
}

function followUpSuggestionFromMessages(messages: ChatMessageItem[]): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== "assistant") {
      continue;
    }
    const suggestion = readFollowUpSuggestion(message.metadata.follow_up_suggestion);
    if (suggestion) {
      return suggestion;
    }
    return null;
  }
  return null;
}

function readFollowUpSuggestion(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const suggestion = value.trim();
  return suggestion ? suggestion : null;
}

function chatTurnErrorMessage(err: unknown, fallback: string): string | null {
  if (err instanceof DOMException && err.name === "AbortError") {
    return null;
  }
  const message = err instanceof Error ? err.message : fallback;
  return normalizeChatErrorMessage(message, fallback);
}

function isChatStreamNetworkError(err: unknown): boolean {
  if (err instanceof DOMException && err.name === "AbortError") {
    return false;
  }
  const message = err instanceof Error ? err.message : `${err}`;
  return /load failed|failed to fetch|networkerror/i.test(message.trim());
}

function normalizeChatErrorMessage(message: string, fallback: string): string {
  const text = message.trim();
  if (!text) {
    return fallback;
  }
  if (/load failed|failed to fetch|networkerror/i.test(text)) {
    return "连接中断，可以点右下角继续生成。";
  }
  return text;
}

function hasVisibleAssistantAnswer(messages: ChatMessageItem[]): boolean {
  return messages.some((message) => message.role === "assistant" && Boolean(message.content.trim()));
}
