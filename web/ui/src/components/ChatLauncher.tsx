import { MessageCircle, SendHorizonal, X } from "lucide-react";
import { useState } from "react";

import { sendChatTurn } from "../api/radarApi";
import type { ChatMessageItem } from "../types";

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
  const [draft, setDraft] = useState(props.suggestedQuestions[0] ?? "");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const visibleContext = props.context.filter((item) => item.value !== undefined && item.value !== null && `${item.value}`.trim() !== "");

  async function submitTurn() {
    const content = draft.trim();
    if (!content || sending) {
      return;
    }
    setSending(true);
    setError(null);
    try {
      const response = await sendChatTurn({
        session_id: sessionId,
        title: props.title,
        content,
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
        },
      });
      setSessionId(response.session_id);
      setMessages((current) => [...current, response.user_message, response.assistant_message]);
      setDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "发送失败");
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <button className={props.buttonClassName ?? "btn btn-sm"} type="button" onClick={() => setOpen(true)}>
        <MessageCircle size={14} />
        {props.buttonLabel}
      </button>
      {open && (
        <div className="chat-launcher-shell" role="dialog" aria-modal="true" aria-label={props.title}>
          <button className="chat-launcher-scrim" type="button" aria-label="关闭对话" onClick={() => setOpen(false)} />
          <aside className="chat-launcher-panel">
            <header className="chat-launcher-head">
              <div>
                <span>{props.surface}</span>
                <strong>{props.title}</strong>
                <em>{props.subtitle}</em>
              </div>
              <button className="icon-btn" type="button" aria-label="关闭" onClick={() => setOpen(false)}>
                <X size={16} />
              </button>
            </header>

            <div className="chat-launcher-body">
              <section className="chat-launcher-card">
                <div className="chat-launcher-card-title">
                  <strong>上下文</strong>
                  <span>{props.entityId}</span>
                </div>
                <div className="chat-context-grid">
                  {visibleContext.map((item) => (
                    <article key={item.label}>
                      <span>{item.label}</span>
                      <strong>{item.value}</strong>
                    </article>
                  ))}
                </div>
              </section>

              {props.evidence && props.evidence.length > 0 && (
                <section className="chat-launcher-card">
                  <div className="chat-launcher-card-title">
                    <strong>证据</strong>
                    <span>{props.evidence.length} 条</span>
                  </div>
                  <ul className="chat-evidence-list">
                    {props.evidence.slice(0, 5).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </section>
              )}

              {messages.length > 0 && (
                <section className="chat-launcher-card">
                  <div className="chat-launcher-card-title">
                    <strong>对话</strong>
                    <span>{messages.length} 条</span>
                  </div>
                  <div className="chat-message-list">
                    {messages.map((message) => (
                      <article className={`chat-message chat-message-${message.role}`} key={message.message_id}>
                        <span>{message.role === "assistant" ? "radar" : "你"}</span>
                        <p>{message.content}</p>
                      </article>
                    ))}
                  </div>
                </section>
              )}

              <section className="chat-launcher-card">
                <div className="chat-launcher-card-title">
                  <strong>提问</strong>
                </div>
                <div className="chat-question-list">
                  {props.suggestedQuestions.map((question) => (
                    <button type="button" key={question} onClick={() => setDraft(question)}>
                      {question}
                    </button>
                  ))}
                </div>
                <div className="chat-composer">
                  <textarea value={draft} onChange={(event) => setDraft(event.target.value)} rows={3} />
                  <button className="btn btn-primary btn-sm" type="button" disabled={sending || !draft.trim()} onClick={() => void submitTurn()}>
                    <SendHorizonal size={14} />
                    {sending ? "发送中" : "发送"}
                  </button>
                </div>
                {error && <p className="chat-error">{error}</p>}
              </section>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
