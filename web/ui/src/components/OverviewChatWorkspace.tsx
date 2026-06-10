import type { ReactNode } from "react";
import { History, PanelRightClose, PanelRightOpen, Plus } from "lucide-react";

import { ChatComposer } from "./ChatComposer";
import { ChatHistoryPanel } from "./ChatHistoryPanel";
import { ChatMessageList } from "./ChatMessageList";
import type { ChatController } from "./chatTypes";

type OverviewChatWorkspaceProps = {
  controller: ChatController;
  title: string;
  subtitle: string;
  surface: string;
  evidence?: string[];
  intro?: ReactNode;
  rightRail?: ReactNode;
  rightRailOpen: boolean;
  composerPlaceholder: string;
  quickPrompts: { label: string; prompt: string }[];
  onToggleRightRail: () => void;
};

export function OverviewChatWorkspace(props: OverviewChatWorkspaceProps) {
  const controller = props.controller;
  const bodyClassName = [
    "overview-chat-body",
    controller.historyOpen ? "with-history" : "",
    props.rightRail && props.rightRailOpen ? "with-context-rail" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="overview-chat-workspace">
      <header className="overview-chat-head">
        <div className="chat-launcher-title">
          <span>{props.surface}</span>
          <strong>{props.title}</strong>
          <em>{props.subtitle}</em>
        </div>
        <div className="chat-launcher-actions">
          {props.rightRail ? (
            <button className="icon-btn" type="button" aria-label="切换上下文栏" onClick={props.onToggleRightRail}>
              {props.rightRailOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
            </button>
          ) : null}
          <button className="icon-btn" type="button" aria-label="历史对话" onClick={() => controller.setHistoryOpen((value) => !value)}>
            <History size={16} />
          </button>
          <button className="icon-btn" type="button" aria-label="新对话" onClick={controller.startNewSession}>
            <Plus size={16} />
          </button>
        </div>
      </header>
      <div className={bodyClassName}>
        {controller.historyOpen ? (
          <ChatHistoryPanel
            activeSessionId={controller.activeSessionId}
            loading={controller.loadingSessions}
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
        <div className={props.intro ? "overview-chat-main" : "overview-chat-main without-intro"}>
          {props.intro}
          <ChatMessageList
            messages={controller.messages}
            emptyState="overview"
            endRef={controller.messagesEndRef}
            listRef={controller.messageListRef}
            showJumpToBottom={!controller.autoFollowBottom && controller.hasNewMessagesBelow}
            onJumpToBottom={controller.jumpToLatestMessage}
            onScrollStateChange={controller.updateMessageScrollState}
          />
          <ChatComposer
            draft={controller.draft}
            modelOptions={controller.modelOptions}
            selectedProviderName={controller.selectedProviderName}
            messages={controller.messages}
            contextItems={controller.visibleContext}
            evidence={props.evidence}
            placeholder={props.composerPlaceholder}
            quickPrompts={props.quickPrompts}
            sending={controller.sending}
            onDraftChange={controller.setDraft}
            onProviderChange={controller.changeProvider}
            onStop={controller.stopStreaming}
            onSubmit={() => void controller.submitTurn()}
          />
          {controller.error && <p className="chat-error">{controller.error}</p>}
        </div>
        {props.rightRail && props.rightRailOpen ? <aside className="overview-context-rail">{props.rightRail}</aside> : null}
      </div>
    </div>
  );
}
