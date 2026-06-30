import type { RefObject } from "react";

import type { ChatMessageItem, ChatModelOption } from "../types";

export type ChatContextItem = {
  label: string;
  value?: string | number | null;
  copyValue?: string | number | null;
  copyLabel?: string;
};

export type ChatSurfaceProps = {
  title: string;
  subtitle: string;
  surface: string;
  entityId: string;
  context: ChatContextItem[];
  evidence?: string[];
  initialDraft?: string | null;
  initialRunId?: string | null;
  initialSessionId?: string | null;
  skipActiveRunRestore?: boolean;
};

export type ChatController = {
  activeSessionId: string | null;
  autoFollowBottom: boolean;
  canContinue: boolean;
  draft: string;
  error: string | null;
  hasNewMessagesBelow: boolean;
  composerHidden: boolean;
  messageListRef: RefObject<HTMLDivElement | null>;
  messages: ChatMessageItem[];
  messagesEndRef: RefObject<HTMLDivElement | null>;
  modelOptions: ChatModelOption[];
  selectedProviderName: string | null;
  sending: boolean;
  visibleContext: ChatContextItem[];
  changeProvider: (providerName: string | null) => void;
  continueTurn: () => Promise<void>;
  jumpToLatestMessage: () => void;
  setDraft: (value: string) => void;
  startNewSession: () => void;
  stopStreaming: () => void;
  submitTurn: () => Promise<void>;
  updateMessageScrollState: (isNearBottom: boolean) => void;
};
