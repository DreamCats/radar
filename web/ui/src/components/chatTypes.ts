import type { RefObject } from "react";

import type { ChatMessageItem, ChatModelOption, ChatSessionItem } from "../types";

export type ChatContextItem = {
  label: string;
  value?: string | number | null;
};

export type ChatSurfaceProps = {
  title: string;
  subtitle: string;
  surface: string;
  entityId: string;
  context: ChatContextItem[];
  evidence?: string[];
  suggestedQuestions: string[];
};

export type ChatController = {
  activeSessionId: string | null;
  autoFollowBottom: boolean;
  draft: string;
  error: string | null;
  hasNewMessagesBelow: boolean;
  historyOpen: boolean;
  loadingSessions: boolean;
  messageListRef: RefObject<HTMLDivElement | null>;
  messages: ChatMessageItem[];
  messagesEndRef: RefObject<HTMLDivElement | null>;
  modelOptions: ChatModelOption[];
  selectedProviderName: string | null;
  sessionAction: { label: string; sessionId: string } | null;
  sending: boolean;
  sessions: ChatSessionItem[];
  visibleContext: ChatContextItem[];
  changeProvider: (providerName: string | null) => void;
  copySessionContent: (nextSessionId: string) => Promise<void>;
  copySessionId: (nextSessionId: string) => Promise<void>;
  copySessionTitle: (session: ChatSessionItem) => Promise<void>;
  jumpToLatestMessage: () => void;
  refreshSessions: () => Promise<void>;
  removeSession: (nextSessionId: string) => Promise<void>;
  restoreSession: (nextSessionId: string) => Promise<void>;
  setDraft: (value: string) => void;
  setHistoryOpen: (value: boolean | ((current: boolean) => boolean)) => void;
  startNewSession: () => void;
  stopStreaming: () => void;
  submitTurn: () => Promise<void>;
  updateMessageScrollState: (isNearBottom: boolean) => void;
};
