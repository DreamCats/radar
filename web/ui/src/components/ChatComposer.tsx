import { ArrowUp, Brain, ChevronDown, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { ChatModelOption } from "../types";

type ChatComposerProps = {
  draft: string;
  sending: boolean;
  modelOptions: ChatModelOption[];
  selectedProviderName: string | null;
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
    <div className="chat-composer">
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
        placeholder="输入你的问题..."
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
      <div className="chat-composer-actions">
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
