import { useEffect, useRef, useState } from "react";

import {
  cancelChatRun,
  continueChatTurn,
  createChatRun,
  deleteChatSession,
  fetchActiveChatRun,
  fetchChatModelOptions,
  fetchChatSession,
  fetchChatSessions,
  streamChatRun,
} from "../api/radarApi";
import { formatChatTranscript } from "../lib/chatTranscript";
import { copyText } from "../lib/clipboard";
import type { ChatMessageItem, ChatModelOption, ChatSessionItem } from "../types";
import {
  MODEL_THINKING_STATUS,
  type ActiveChatRunRecord,
  appendErrorTrace,
  appendStatusTrace,
  chatTraceItems,
  clearActiveChatRun,
  clearActiveSessionId,
  clearSelectedProviderName,
  completedStatus,
  readActiveChatRun,
  readActiveSessionId,
  readSelectedProviderName,
  writeActiveChatRun,
  writeActiveSessionId,
  writeSelectedProviderName,
} from "./chatHelpers";
import { createChatStreamHandler } from "./chatStreamHandler";
import type { ChatController, ChatSurfaceProps } from "./chatTypes";

const CHAT_RUN_STALE_RECONNECT_MS = 25_000;
const CHAT_RUN_RECONNECT_DELAY_MS = 800;

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
  const activeRunRef = useRef<ActiveChatRunRecord | null>(null);
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
    void restoreActiveRun();
    void refreshSessions();
    void refreshModelOptions();
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

  function createIdleStatusScheduler(assistantDraftId: string) {
    return (status = MODEL_THINKING_STATUS) => {
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

  function markRunSubscriptionStale(assistantDraftId: string) {
    setMessages((current) =>
      current.map((message) =>
        message.message_id === assistantDraftId && message.metadata.streaming
          ? {
              ...message,
              metadata: {
                ...message.metadata,
                status: "连接无响应，正在重新连接",
                trace_items: appendStatusTrace(message.metadata.trace_items, "连接无响应，正在重新连接"),
              },
            }
          : message,
      ),
    );
  }

  function markRunSubscriptionRetrying(assistantDraftId: string) {
    setMessages((current) =>
      current.map((message) =>
        message.message_id === assistantDraftId && message.metadata.streaming
          ? {
              ...message,
              metadata: {
                ...message.metadata,
                status: "正在重新连接后台任务",
                trace_items: appendStatusTrace(message.metadata.trace_items, "正在重新连接后台任务"),
              },
            }
          : message,
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
    const controller = new AbortController();
    abortControllerRef.current = controller;
    const scheduleIdleStatus = createIdleStatusScheduler(assistantDraftId);
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
      const request = buildChatTurnRequest(content, selectedModelOption);
      const response = await createChatRun(request);
      const nextRun: ActiveChatRunRecord = {
        runId: response.run.run_id,
        sessionId: response.run.session_id,
        assistantDraftId,
        lastSeq: 0,
        surface: props.surface,
        entityId: props.entityId,
        createdAt: response.run.created_at,
      };
      activeRunRef.current = nextRun;
      writeActiveChatRun(nextRun);
      setSessionId(response.run.session_id);
      writeActiveSessionId(response.run.session_id);
      await subscribeToRun(nextRun, { controller, userDraftId });
    } catch (err) {
      const errorMessage = chatTurnErrorMessage(err, "发送失败");
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }
      const currentSessionId = activeRunRef.current?.sessionId ?? sessionId;
      const networkError = isChatStreamNetworkError(err);
      if (networkError && currentSessionId && (await recoverCompletedTurn(currentSessionId, assistantDraftId))) {
        const recoveredRunId = activeRunRef.current?.runId;
        if (recoveredRunId) {
          clearActiveChatRun(recoveredRunId);
        }
        activeRunRef.current = null;
        return;
      }
      const activeRunId = activeRunRef.current?.runId;
      if (!networkError && activeRunId) {
        clearActiveChatRun(activeRunId);
        activeRunRef.current = null;
      }
      setError(null);
      stopAssistantDraft(assistantDraftId, errorMessage);
      setCanContinue(false);
    } finally {
      clearIdleTimer();
      abortControllerRef.current = null;
      setSending(false);
      void refreshSessions();
    }
  }

  async function subscribeToRun(
    record: ActiveChatRunRecord,
    options: { controller: AbortController; userDraftId?: string; afterSeq?: number },
  ) {
    const scheduleIdleStatus = createIdleStatusScheduler(record.assistantDraftId);
    const handleStreamEvent = createChatStreamHandler({
      assistantDraftId: record.assistantDraftId,
      userDraftId: options.userDraftId,
      setMessages,
      clearIdleTimer,
      scheduleIdleStatus,
      onSession: (nextSessionId) => {
        const nextRecord = { ...record, sessionId: nextSessionId };
        activeRunRef.current = nextRecord;
        writeActiveChatRun(nextRecord);
        setSessionId(nextSessionId);
        writeActiveSessionId(nextSessionId);
      },
      onFollowUpSuggestion: setFollowUpSuggestion,
    });
    let afterSeq = options.afterSeq ?? record.lastSeq;
    while (!options.controller.signal.aborted) {
      const streamController = new AbortController();
      const abortStream = () => streamController.abort();
      options.controller.signal.addEventListener("abort", abortStream, { once: true });
      let staleTimer: number | null = null;
      let abortedByWatchdog = false;
      const clearStaleTimer = () => {
        if (staleTimer === null) {
          return;
        }
        window.clearTimeout(staleTimer);
        staleTimer = null;
      };
      const armStaleTimer = () => {
        clearStaleTimer();
        staleTimer = window.setTimeout(() => {
          abortedByWatchdog = true;
          markRunSubscriptionStale(record.assistantDraftId);
          streamController.abort();
        }, CHAT_RUN_STALE_RECONNECT_MS);
      };
      armStaleTimer();
      try {
        await streamChatRun(
          record.runId,
          (event) => {
            armStaleTimer();
            const sequenceNumber = event.sequence_number;
            if (typeof sequenceNumber === "number" && Number.isFinite(sequenceNumber)) {
              const nextRecord = { ...(activeRunRef.current ?? record), lastSeq: sequenceNumber };
              activeRunRef.current = nextRecord;
              writeActiveChatRun(nextRecord);
              afterSeq = sequenceNumber;
            }
            handleStreamEvent(event);
          },
          { signal: streamController.signal, afterSeq },
        );
        break;
      } catch (err) {
        if (options.controller.signal.aborted) {
          throw err;
        }
        if (!abortedByWatchdog && !isChatStreamNetworkError(err)) {
          throw err;
        }
        const currentRecord = activeRunRef.current ?? record;
        afterSeq = currentRecord.lastSeq;
        markRunSubscriptionRetrying(currentRecord.assistantDraftId);
        await waitForChatRunReconnect(options.controller.signal);
      } finally {
        clearStaleTimer();
        options.controller.signal.removeEventListener("abort", abortStream);
      }
    }
    if (options.controller.signal.aborted) {
      return;
    }
    clearActiveChatRun(record.runId);
    if (activeRunRef.current?.runId === record.runId) {
      activeRunRef.current = null;
    }
    setCanContinue(false);
  }

  function buildChatTurnRequest(content: string, selectedModelOption: ChatModelOption | null) {
    return {
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
    };
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
    const scheduleIdleStatus = (status = MODEL_THINKING_STATUS) => {
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
    const activeRun = activeRunRef.current;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    if (activeRun) {
      void cancelChatRun(activeRun.runId).catch(() => undefined);
      clearActiveChatRun(activeRun.runId);
      activeRunRef.current = null;
      stopAssistantDraft(activeRun.assistantDraftId, "已停止");
    }
    setSending(false);
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

  async function restoreActiveRun() {
    let record = readActiveChatRun();
    if (!record || record.surface !== props.surface || record.entityId !== props.entityId) {
      const active = await fetchActiveChatRun({
        sessionId: readActiveSessionId(),
        surface: props.surface,
        entityId: props.entityId,
      });
      if (!active.run) {
        return;
      }
      record = {
        runId: active.run.run_id,
        sessionId: active.run.session_id,
        assistantDraftId: `assistant-stream-${Date.now()}`,
        lastSeq: 0,
        surface: props.surface,
        entityId: props.entityId,
        createdAt: active.run.created_at,
      };
      writeActiveChatRun(record);
    }
    if (activeRunRef.current?.runId === record.runId) {
      return;
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    activeRunRef.current = record;
    setSessionId(record.sessionId);
    writeActiveSessionId(record.sessionId);
    setSending(true);
    setCanContinue(false);
    setFollowUpSuggestion(null);
    setError(null);
    setMessages([
      {
        message_id: record.assistantDraftId,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
        metadata: { streaming: true, resumed: true, status: "正在同步后台进度" },
      },
    ]);
    try {
      await subscribeToRun(record, { controller, afterSeq: 0 });
      await recoverCompletedTurn(record.sessionId, record.assistantDraftId);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }
      if (!isChatStreamNetworkError(err)) {
        clearActiveChatRun(record.runId);
        if (activeRunRef.current?.runId === record.runId) {
          activeRunRef.current = null;
        }
      }
      stopAssistantDraft(record.assistantDraftId, chatTurnErrorMessage(err, "同步后台进度失败"));
    } finally {
      clearIdleTimer();
      abortControllerRef.current = null;
      setSending(false);
      void refreshSessions();
    }
  }

  async function restoreSession(nextSessionId: string) {
    setSessionAction({ sessionId: nextSessionId, label: "打开中" });
    try {
      if (activeRunRef.current && activeRunRef.current.sessionId !== nextSessionId) {
        abortControllerRef.current?.abort();
        abortControllerRef.current = null;
        activeRunRef.current = null;
        setSending(false);
      }
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

  function resetSessionState() {
    const activeRun = activeRunRef.current;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    if (activeRun) {
      void cancelChatRun(activeRun.runId).catch(() => undefined);
      clearActiveChatRun(activeRun.runId);
      activeRunRef.current = null;
    }
    clearActiveSessionId();
    setSessionId(null);
    setMessages([]);
    setDraft("");
    setCanContinue(false);
    setFollowUpSuggestion(null);
    setError(null);
    setHistoryOpen(false);
  }

  function startNewSession() {
    setBottomFollowMode(true);
    setHasNewMessagesBelow(false);
    resetSessionState();
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
      if (nextSessionId === sessionId) {
        resetSessionState();
      }
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
    return "连接中断，后台仍在处理，重新打开会同步。";
  }
  return text;
}

function hasVisibleAssistantAnswer(messages: ChatMessageItem[]): boolean {
  return messages.some((message) => message.role === "assistant" && Boolean(message.content.trim()));
}

function waitForChatRunReconnect(signal: AbortSignal): Promise<void> {
  if (signal.aborted) {
    return Promise.reject(new DOMException("Aborted", "AbortError"));
  }
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, CHAT_RUN_RECONNECT_DELAY_MS);
    const abort = () => {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal.addEventListener("abort", abort, { once: true });
  });
}
