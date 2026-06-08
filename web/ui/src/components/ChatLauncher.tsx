import { History, MessageCircle, Plus, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { fetchChatModelOptions, fetchChatSession, fetchChatSessions, streamChatTurn } from "../api/radarApi";
import type { ChatMessageItem, ChatModelOption, ChatSessionItem } from "../types";
import {
  formatToolName,
  mergeAssistantMetadata,
  clearActiveSessionId,
  readActiveSessionId,
  statusForAgentEvent,
  toolActivities,
  updateToolActivities,
  writeActiveSessionId,
} from "./chatHelpers";
import { ChatComposer } from "./ChatComposer";
import { ChatHistoryPanel } from "./ChatHistoryPanel";
import { MarkdownContent } from "./MarkdownContent";

export type ChatContextItem = {
  label: string;
  value?: string | number | null;
};

export type ChatLauncherProps = {
  title: string;
  subtitle: string;
  surface: string;
  entityId: string;
  buttonLabel: string;
  buttonClassName?: string;
  context: ChatContextItem[];
  evidence?: string[];
  suggestedQuestions: string[];
};

export function ChatLauncher(props: ChatLauncherProps) {
  const [open, setOpen] = useState(false);
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
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const visibleContext = props.context.filter((item) => item.value !== undefined && item.value !== null && `${item.value}`.trim() !== "");

  useEffect(() => {
    if (open) {
      messagesEndRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
    }
  }, [messages, open, sending]);

  useEffect(() => {
    if (!open) {
      return;
    }
    void refreshSessions();
    void refreshModelOptions();
    if (!sessionId && messages.length === 0) {
      const activeSessionId = readActiveSessionId();
      if (activeSessionId) {
        void restoreSession(activeSessionId);
      }
    }
  }, [open]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  async function submitTurn() {
    const content = draft.trim();
    if (!content || sending) {
      return;
    }
    setSending(true);
    setError(null);
    setDraft("");
    const userDraftId = `user-local-${Date.now()}`;
    const assistantDraftId = `assistant-stream-${Date.now()}`;
    const selectedModelOption = modelOptions.find((item) => item.provider_name === selectedProviderName) ?? null;
    let hasAssistantDraft = true;
    const controller = new AbortController();
    abortControllerRef.current = controller;
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
          if (event.type === "user_message") {
            return;
          }
          if (event.type === "assistant_delta") {
            if (!event.content) {
              return;
            }
            setMessages((current) => {
              if (!hasAssistantDraft) {
                hasAssistantDraft = true;
                return [
                  ...current,
                  {
                    message_id: assistantDraftId,
                    role: "assistant",
                    content: event.content,
                    created_at: new Date().toISOString(),
                    metadata: { streaming: true },
                  },
                ];
              }
              return current.map((message) =>
                message.message_id === assistantDraftId ? { ...message, content: `${message.content}${event.content}` } : message,
              );
            });
            return;
          }
          if (event.type === "assistant_reasoning_delta") {
            if (!event.content) {
              return;
            }
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
            return;
          }
          if (event.type === "assistant_message") {
            const message = event.message;
            if (!message.content.trim()) {
              setMessages((current) =>
                current.map((item) =>
                  item.message_id === assistantDraftId
                    ? { ...item, metadata: { ...item.metadata, streaming: true, status: "正在查询本地数据" } }
                    : item,
                ),
              );
              return;
            }
            setMessages((current) => {
              if (hasAssistantDraft) {
                hasAssistantDraft = false;
                return current.map((item) => (item.message_id === assistantDraftId ? mergeAssistantMetadata(item, message) : item));
              }
              return [...current, message];
            });
            return;
          }
          if (event.type === "tool_message") {
            const toolName = typeof event.message.metadata.tool_name === "string" ? event.message.metadata.tool_name : "工具";
            setMessages((current) =>
              current.map((message) =>
                message.message_id === assistantDraftId
                  ? { ...message, metadata: { ...message.metadata, streaming: true, status: `已读取 ${formatToolName(toolName)}` } }
                  : message,
              ),
            );
            return;
          }
          if (event.type === "agent_event") {
            const eventType = typeof event.event.type === "string" ? event.event.type : "";
            const payload = typeof event.event.payload === "object" && event.event.payload ? event.event.payload : {};
            const toolName = "tool_name" in payload && typeof payload.tool_name === "string" ? payload.tool_name : "";
            const toolCallId = "tool_call_id" in payload && typeof payload.tool_call_id === "string" ? payload.tool_call_id : toolName;
            const status = statusForAgentEvent(eventType, toolName);
            if (!status) {
              return;
            }
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
            message.message_id === assistantDraftId
              ? { ...message, metadata: { ...message.metadata, streaming: false, stopped: true } }
              : message,
          ),
      );
    } finally {
      abortControllerRef.current = null;
      setSending(false);
      void refreshSessions();
    }
  }

  function closeLauncher() {
    abortControllerRef.current?.abort();
    setOpen(false);
  }

  function stopStreaming() {
    abortControllerRef.current?.abort();
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
        if (current && data.items.some((item) => item.provider_name === current)) {
          return current;
        }
        return data.default_provider_name ?? data.items[0]?.provider_name ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取模型配置失败");
    }
  }

  async function restoreSession(nextSessionId: string) {
    try {
      const data = await fetchChatSession(nextSessionId);
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
    setSessionId(null);
    setMessages([]);
    setDraft("");
    setError(null);
    setHistoryOpen(false);
  }

  return (
    <>
      <button className={props.buttonClassName ?? "btn btn-sm"} type="button" onClick={() => setOpen(true)}>
        <MessageCircle size={14} />
        {props.buttonLabel}
      </button>
      <AnimatePresence>
        {open && (
        <motion.div
          className="chat-launcher-shell"
          role="dialog"
          aria-modal="true"
          aria-label={props.title}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
        >
          <motion.button
            className="chat-launcher-scrim"
            type="button"
            aria-label="关闭对话"
            onClick={closeLauncher}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
          <motion.aside
            className="chat-launcher-panel"
            initial={{ opacity: 0, y: 18, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
          >
            <header className="chat-launcher-head">
              <div className="chat-launcher-title">
                <span>{props.surface}</span>
                <strong>{props.title}</strong>
                <em>{props.subtitle}</em>
              </div>
              <div className="chat-launcher-actions">
                <button className="icon-btn" type="button" aria-label="历史对话" onClick={() => setHistoryOpen((value) => !value)}>
                  <History size={16} />
                </button>
                <button className="icon-btn" type="button" aria-label="新对话" onClick={startNewSession}>
                  <Plus size={16} />
                </button>
                <button className="icon-btn" type="button" aria-label="关闭" onClick={closeLauncher}>
                  <X size={16} />
                </button>
              </div>
            </header>

            <div className={historyOpen ? "chat-launcher-body with-history" : "chat-launcher-body"}>
              {historyOpen ? (
                <ChatHistoryPanel
                  activeSessionId={sessionId}
                  loading={loadingSessions}
                  sessions={sessions}
                  onNewSession={startNewSession}
                  onRefresh={() => void refreshSessions()}
                  onRestore={(nextSessionId) => void restoreSession(nextSessionId)}
                />
              ) : null}
              <div className="chat-main-panel">
              <div className="chat-launcher-reference">
                <details>
                  <summary>
                    <span>上下文</span>
                    <em>{props.entityId}</em>
                  </summary>
                  <div className="chat-context-grid">
                    {visibleContext.map((item) => (
                      <article key={item.label}>
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                      </article>
                    ))}
                  </div>
                </details>

                {props.evidence && props.evidence.length > 0 && (
                  <details>
                    <summary>
                      <span>证据</span>
                      <em>{props.evidence.length} 条</em>
                    </summary>
                    <ul className="chat-evidence-list">
                      {props.evidence.slice(0, 5).map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>

              <div className="chat-message-list">
                <AnimatePresence initial={false}>
                  {messages.map((message) => {
                    const status = typeof message.metadata.status === "string" ? message.metadata.status : "";
                    const reasoning = typeof message.metadata.reasoning === "string" ? message.metadata.reasoning : "";
                    const activities = toolActivities(message.metadata.tool_activities);
                    return (
                    <motion.article
                      className={`chat-message chat-message-${message.role}`}
                      key={message.message_id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -6 }}
                      transition={{ duration: 0.16 }}
                    >
                      {message.role === "assistant" && status ? <div className="chat-agent-status">{status}</div> : null}
                      {message.role === "assistant" && (reasoning || activities.length > 0) ? (
                        <details className="chat-reasoning" open={Boolean(message.metadata.streaming)}>
                          <summary>推理过程</summary>
                          {reasoning ? <MarkdownContent content={reasoning} /> : null}
                          {activities.length > 0 ? (
                            <ul className="chat-tool-activity-list">
                              {activities.map((activity) => (
                                <li className={`chat-tool-activity-${activity.status}`} key={activity.key}>
                                  {activity.label}
                                </li>
                              ))}
                            </ul>
                          ) : null}
                        </details>
                      ) : null}
                      {message.content ? (
                        <>
                          <MarkdownContent content={message.content} />
                          {message.metadata.streaming ? <i className="chat-stream-cursor" aria-hidden="true" /> : null}
                        </>
                      ) : (
                        <div className="chat-typing" aria-label="生成中">
                          <span>正在整理</span>
                          <em />
                          <em />
                          <em />
                        </div>
                      )}
                    </motion.article>
                    );
                  })}
                </AnimatePresence>
                <div ref={messagesEndRef} />
              </div>

              <ChatComposer
                draft={draft}
                modelOptions={modelOptions}
                selectedProviderName={selectedProviderName}
                sending={sending}
                onDraftChange={setDraft}
                onProviderChange={setSelectedProviderName}
                onStop={stopStreaming}
                onSubmit={() => void submitTurn()}
              />
                {error && <p className="chat-error">{error}</p>}
              </div>
            </div>
          </motion.aside>
        </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
