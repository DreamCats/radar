import { ArrowLeft, Check, Copy, Plus, X } from "lucide-react";
import { useCallback, useState } from "react";

import { copyText } from "../lib/clipboard";
import { useSwipeToCloseSheet } from "../lib/useSwipeToCloseSheet";
import { ChatComposer } from "./ChatComposer";
import { ChatMessageList } from "./ChatMessageList";
import type { ChatController } from "./chatTypes";

type ChatWorkspaceProps = {
  controller: ChatController;
  title: string;
  subtitle: string;
  surface: string;
  entityId: string;
  evidence?: string[];
  quickPrompts?: { label: string; prompt: string }[];
  onClose?: () => void;
};

export function ChatWorkspace(props: ChatWorkspaceProps) {
  const controller = props.controller;
  const [copiedContextKey, setCopiedContextKey] = useState<string | null>(null);
  const handleSwipeBack = useCallback(() => {
    props.onClose?.();
  }, [props.onClose]);
  const swipeBack = useSwipeToCloseSheet(handleSwipeBack, {
    direction: "right",
    enabled: Boolean(props.onClose),
    mediaQuery: "(max-width: 640px)",
    minDistance: 72,
    startEdgeWidth: 48,
  });

  async function copyContextValue(key: string, value: string) {
    await copyText(value);
    setCopiedContextKey(key);
    window.setTimeout(() => {
      setCopiedContextKey((current) => (current === key ? null : current));
    }, 1200);
  }

  return (
    <div className="chat-workspace" {...swipeBack}>
      <header className="chat-launcher-head">
        {props.onClose ? (
          <button className="icon-btn chat-launcher-back" type="button" aria-label="返回上一页" title="返回上一页" onClick={props.onClose}>
            <ArrowLeft size={17} />
          </button>
        ) : null}
        <div className="chat-launcher-head-main">
          <div className="chat-launcher-title">
            <span>{props.surface}</span>
            <strong>{props.title}</strong>
            <em>{props.subtitle}</em>
          </div>
          <div className="chat-launcher-reference">
            <details>
              <summary>
                <span>上下文</span>
                <em>{props.entityId}</em>
              </summary>
              <div className="chat-context-grid">
                {controller.visibleContext.map((item) => (
                  <article className={item.copyValue !== undefined && item.copyValue !== null ? "is-copyable" : ""} key={item.label}>
                    <span>{item.label}</span>
                    <div className="chat-context-value">
                      <strong>{item.value}</strong>
                      {item.copyValue !== undefined && item.copyValue !== null ? (
                        <button
                          className={copiedContextKey === item.label ? "chat-context-copy is-copied" : "chat-context-copy"}
                          type="button"
                          aria-label={item.copyLabel ?? `复制${item.label}`}
                          title={copiedContextKey === item.label ? "已复制" : item.copyLabel ?? `复制${item.label}`}
                          onClick={() => void copyContextValue(item.label, `${item.copyValue}`)}
                        >
                          {copiedContextKey === item.label ? <Check size={12} /> : <Copy size={12} />}
                        </button>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            </details>
            {props.evidence && props.evidence.length > 0 ? (
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
            ) : null}
          </div>
        </div>
        <div className="chat-launcher-actions">
          <button className="icon-btn chat-launcher-action" type="button" aria-label="新建对话" title="新建对话" onClick={controller.startNewSession}>
            <Plus size={16} />
          </button>
          {props.onClose ? (
            <button className="icon-btn chat-launcher-action chat-launcher-close" type="button" aria-label="关闭聊天" title="关闭聊天" onClick={props.onClose}>
              <X size={16} />
            </button>
          ) : null}
        </div>
      </header>
      <div className="chat-launcher-body">
        <div className="chat-main-panel">
          <ChatMessageList
            activeSessionId={controller.activeSessionId}
            messages={controller.messages}
            endRef={controller.messagesEndRef}
            listRef={controller.messageListRef}
            markdownSurface="drawer"
            emptyState="overview"
            showJumpToBottom={!controller.autoFollowBottom && controller.hasNewMessagesBelow}
            onJumpToBottom={controller.jumpToLatestMessage}
            onScrollStateChange={controller.updateMessageScrollState}
          />
          <ChatComposer
            draft={controller.draft}
            canContinue={controller.canContinue}
            modelOptions={controller.modelOptions}
            selectedProviderName={controller.selectedProviderName}
            messages={controller.messages}
            contextItems={controller.visibleContext}
            evidence={props.evidence}
            quickPrompts={props.quickPrompts}
            readingHidden={controller.composerHidden}
            sending={controller.sending}
            onDraftChange={controller.setDraft}
            onProviderChange={controller.changeProvider}
            onContinue={() => void controller.continueTurn()}
            onStop={controller.stopStreaming}
            onSubmit={() => void controller.submitTurn()}
          />
          {controller.error && <p className="chat-error">{controller.error}</p>}
        </div>
      </div>
    </div>
  );
}
