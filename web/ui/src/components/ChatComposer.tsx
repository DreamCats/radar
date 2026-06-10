import { ArrowUp, Brain, ChevronDown, Square } from "lucide-react";
import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";

import type { ChatMessageItem, ChatModelOption } from "../types";

type ChatContextItem = {
  label: string;
  value?: string | number | null;
};

type ContextUsage = {
  usedTokens: number;
  totalTokens: number;
  usedPercent: number;
};

type ChatComposerProps = {
  draft: string;
  sending: boolean;
  modelOptions: ChatModelOption[];
  selectedProviderName: string | null;
  messages: ChatMessageItem[];
  contextItems: ChatContextItem[];
  evidence?: string[];
  placeholder?: string;
  quickPrompts?: { label: string; prompt: string }[];
  onDraftChange: (value: string) => void;
  onProviderChange: (value: string | null) => void;
  onSubmit: () => void;
  onStop: () => void;
};

export function ChatComposer({
  draft,
  sending,
  modelOptions,
  selectedProviderName,
  messages,
  contextItems,
  evidence,
  placeholder,
  quickPrompts,
  onDraftChange,
  onProviderChange,
  onSubmit,
  onStop,
}: ChatComposerProps) {
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const modelMenuRef = useRef<HTMLDivElement | null>(null);
  const isComposingRef = useRef(false);
  const selectedOption = modelOptions.find((item) => item.provider_name === selectedProviderName) ?? modelOptions[0];
  const modelLabel = labelForModelOption(selectedOption);
  const contextUsage = estimateContextUsage({
    draft,
    messages,
    contextItems,
    evidence: evidence ?? [],
    totalTokens: selectedOption?.context_window_tokens ?? 256_000,
  });
  const contextTooltip = [
    "背景信息窗口：",
    `${contextUsage.usedPercent}% 已用（剩余 ${100 - contextUsage.usedPercent}%）`,
    `约 ${formatTokenCount(contextUsage.usedTokens)} 标记，共 ${formatTokenCount(contextUsage.totalTokens)}`,
  ].join("\n");

  useEffect(() => {
    if (!modelMenuOpen) {
      return;
    }
    function closeOnOutsideClick(event: MouseEvent) {
      if (modelMenuRef.current && !modelMenuRef.current.contains(event.target as Node)) {
        setModelMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [modelMenuOpen]);

  return (
    <div className={quickPrompts && quickPrompts.length > 0 ? "chat-composer with-shortcuts" : "chat-composer"}>
      <textarea
        value={draft}
        onChange={(event) => onDraftChange(event.target.value)}
        onCompositionStart={() => {
          isComposingRef.current = true;
        }}
        onCompositionEnd={() => {
          isComposingRef.current = false;
        }}
        rows={3}
        placeholder={placeholder ?? "输入你的问题..."}
        onKeyDown={(event) => {
          const nativeEvent = event.nativeEvent as KeyboardEvent;
          if (isComposingRef.current || nativeEvent.isComposing || nativeEvent.keyCode === 229) {
            return;
          }
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (sending) {
              onStop();
            } else {
              onSubmit();
            }
          }
        }}
      />
      {quickPrompts && quickPrompts.length > 0 ? (
        <div className="chat-composer-shortcuts" aria-label="快捷问题">
          {quickPrompts.map((item) => (
            <button key={item.label} type="button" onClick={() => onDraftChange(item.prompt)}>
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
      <div className="chat-composer-actions">
        <div className="chat-context-meter" tabIndex={0} aria-label={contextTooltip}>
          <span
            className="chat-context-ring"
            style={{ "--ctx-used": `${contextUsage.usedPercent}%` } as CSSProperties}
            aria-hidden="true"
          />
          <span className="chat-context-tooltip" role="tooltip">
            <strong>背景信息窗口：</strong>
            <span>{contextUsage.usedPercent}% 已用（剩余 {100 - contextUsage.usedPercent}%）</span>
            <span>
              约 {formatTokenCount(contextUsage.usedTokens)} 标记，共 {formatTokenCount(contextUsage.totalTokens)}
            </span>
          </span>
        </div>
        <div className="chat-model-menu" ref={modelMenuRef}>
          <button
            className="chat-model-trigger"
            type="button"
            disabled={modelOptions.length === 0 || sending}
            aria-expanded={modelMenuOpen}
            aria-haspopup="menu"
            aria-label="选择模型"
            onClick={() => setModelMenuOpen((value) => !value)}
          >
            <Brain size={14} />
            <span>{modelLabel}</span>
            <ChevronDown size={14} />
          </button>
          {modelMenuOpen && modelOptions.length > 0 ? (
            <div className="chat-model-options" role="menu">
              {modelOptions.map((option) => (
                <button
                  className={option.provider_name === selectedOption?.provider_name ? "selected" : ""}
                  key={option.provider_name}
                  type="button"
                  role="menuitemradio"
                  aria-checked={option.provider_name === selectedOption?.provider_name}
                  onClick={() => {
                    onProviderChange(option.provider_name);
                    setModelMenuOpen(false);
                  }}
                >
                  <span>{labelForModelOption(option)}</span>
                  <em>{option.model}</em>
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <button
          className="chat-send-button"
          type="button"
          disabled={!sending && !draft.trim()}
          onClick={() => (sending ? onStop() : onSubmit())}
          aria-label={sending ? "停止生成" : "发送"}
        >
          {sending ? <Square size={14} /> : <ArrowUp size={18} />}
        </button>
      </div>
    </div>
  );
}

function labelForModelOption(option: ChatModelOption | undefined): string {
  if (!option) {
    return "默认";
  }
  if (option.is_default) {
    return "默认";
  }
  return option.provider_name;
}

function estimateContextUsage(args: {
  draft: string;
  messages: ChatMessageItem[];
  contextItems: ChatContextItem[];
  evidence: string[];
  totalTokens: number;
}): ContextUsage {
  const contextText = args.contextItems
    .filter((item) => item.value !== undefined && item.value !== null && `${item.value}`.trim() !== "")
    .map((item) => `${item.label}: ${item.value}`)
    .join("\n");
  const transcriptText = args.messages.map((message) => `${message.role}: ${message.content}`).join("\n");
  const evidenceText = args.evidence.join("\n");
  const usedTokens = estimateTokenCount([transcriptText, args.draft, contextText, evidenceText].join("\n"));
  const totalTokens = Math.max(1, args.totalTokens);
  const usedPercent = Math.min(100, Math.max(0, Math.round((usedTokens / totalTokens) * 100)));
  return { usedTokens, totalTokens, usedPercent };
}

function estimateTokenCount(text: string): number {
  const trimmed = text.trim();
  if (!trimmed) {
    return 0;
  }
  const cjkCount = (trimmed.match(/[\u3400-\u9fff]/g) ?? []).length;
  const otherText = trimmed.replace(/[\u3400-\u9fff]/g, " ");
  const latinTokenCount = (otherText.match(/[A-Za-z0-9_]+|[^\sA-Za-z0-9_]/g) ?? []).reduce(
    (total, token) => total + Math.max(1, Math.ceil(token.length / 4)),
    0,
  );
  return cjkCount + latinTokenCount;
}

function formatTokenCount(tokens: number): string {
  if (tokens >= 1000) {
    return `${Math.round(tokens / 100) / 10}k`;
  }
  return `${tokens}`;
}
