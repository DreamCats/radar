import { ArrowLeft, History, Plus, X } from "lucide-react";

import { ChatComposer } from "./ChatComposer";
import { ChatHistoryPanel } from "./ChatHistoryPanel";
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
  const bodyClassName = [
    "chat-launcher-body",
    controller.historyOpen ? "with-history" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="chat-workspace">
      <header className="chat-launcher-head">
        {props.onClose ? (
          <button className="icon-btn chat-launcher-back" type="button" aria-label="返回上一页" onClick={props.onClose}>
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
                  <article key={item.label}>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
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
          <button className="icon-btn" type="button" aria-label="历史对话" onClick={() => controller.setHistoryOpen((value) => !value)}>
            <History size={16} />
          </button>
          <button className="icon-btn" type="button" aria-label="新对话" onClick={controller.startNewSession}>
            <Plus size={16} />
          </button>
          {props.onClose ? (
            <button className="icon-btn chat-launcher-close" type="button" aria-label="关闭" onClick={props.onClose}>
              <X size={16} />
            </button>
          ) : null}
        </div>
      </header>
      <div className={bodyClassName}>
        {controller.historyOpen ? (
          <ChatHistoryPanel
            activeSessionId={controller.activeSessionId}
            loading={controller.loadingSessions}
            sessionAction={controller.sessionAction}
            sessions={controller.sessions}
            onNewSession={controller.startNewSession}
            onCopySessionContent={(nextSessionId) => void controller.copySessionContent(nextSessionId)}
            onCopySessionId={(nextSessionId) => void controller.copySessionId(nextSessionId)}
            onCopySessionTitle={(session) => void controller.copySessionTitle(session)}
            onDeleteSession={(nextSessionId) => void controller.removeSession(nextSessionId)}
            onRefresh={() => void controller.refreshSessions()}
            onRestore={(nextSessionId) => void controller.restoreSession(nextSessionId)}
          />
        ) : null}
        <div className="chat-main-panel">
          <ChatMessageList
            activeSessionId={controller.activeSessionId}
            messages={controller.messages}
            endRef={controller.messagesEndRef}
            listRef={controller.messageListRef}
            markdownSurface="drawer"
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
            followUpSuggestion={controller.followUpSuggestion}
            quickPrompts={props.quickPrompts}
            readingHidden={controller.composerHidden}
            sending={controller.sending}
            onAcceptFollowUpSuggestion={controller.acceptFollowUpSuggestion}
            onDraftChange={controller.setDraft}
            onDismissFollowUpSuggestion={controller.dismissFollowUpSuggestion}
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
