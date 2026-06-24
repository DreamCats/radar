import { ArrowDown, Check, ChevronDown, CircleAlert, Copy, Image as ImageIcon, Maximize2, SquareTerminal, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState, type ComponentType, type RefObject, type UIEvent } from "react";
import { createPortal } from "react-dom";

import type { ChatMessageItem } from "../types";
import { fetchChatToolMessage } from "../api/radarApi";
import { copyElementAsPng, copyText, renderElementAsPngBlob } from "../lib/clipboard";
import {
  MODEL_THINKING_STATUS,
  chatTraceItems,
  statusForChatMessage,
  toolActivities,
  type ChatTraceItem,
  type ToolActivityItem,
} from "./chatHelpers";
import { DrawerMarkdownContent } from "./DrawerMarkdownContent";
import { MarkdownContent } from "./MarkdownContent";

type ChatMessageListProps = {
  activeSessionId?: string | null;
  endRef: RefObject<HTMLDivElement | null>;
  listRef: RefObject<HTMLDivElement | null>;
  messages: ChatMessageItem[];
  emptyState?: "overview";
  markdownSurface?: "drawer";
  showJumpToBottom: boolean;
  onJumpToBottom: () => void;
  onScrollStateChange: (isNearBottom: boolean) => void;
};

export function ChatMessageList(props: ChatMessageListProps) {
  const Content = props.markdownSurface === "drawer" ? DrawerMarkdownContent : MarkdownContent;
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [copiedImageMessageId, setCopiedImageMessageId] = useState<string | null>(null);
  const [copyImageError, setCopyImageError] = useState<CopyImageErrorState | null>(null);
  const [copyingImageMessageId, setCopyingImageMessageId] = useState<string | null>(null);
  const [imagePreview, setImagePreview] = useState<ImagePreviewState | null>(null);
  const [readingMessage, setReadingMessage] = useState<ChatMessageItem | null>(null);
  const [toolResult, setToolResult] = useState<ToolResultState | null>(null);
  const copySurfaceRefs = useRef(new Map<string, HTMLDivElement>());

  function handleScroll(event: UIEvent<HTMLDivElement>) {
    props.onScrollStateChange(isNearBottom(event.currentTarget));
  }

  useEffect(() => {
    return () => {
      if (imagePreview?.url) {
        URL.revokeObjectURL(imagePreview.url);
      }
    };
  }, [imagePreview]);

  async function handleCopyMessage(message: ChatMessageItem) {
    try {
      await copyText(message.content);
      setCopiedMessageId(message.message_id);
      setCopiedImageMessageId(null);
      setCopyImageError(null);
      window.setTimeout(() => {
        setCopiedMessageId((current) => (current === message.message_id ? null : current));
      }, 1400);
    } catch {
      setCopiedMessageId(null);
    }
  }

  async function handleCopyMessageImage(message: ChatMessageItem) {
    const surface = copySurfaceRefs.current.get(message.message_id);
    if (!surface) {
      return;
    }

    setCopyingImageMessageId(message.message_id);
    setCopyImageError(null);
    try {
      if (window.isSecureContext) {
        await copyElementAsPng(surface);
        setCopiedImageMessageId(message.message_id);
        setCopiedMessageId(null);
        window.setTimeout(() => {
          setCopiedImageMessageId((current) => (current === message.message_id ? null : current));
        }, 1400);
      } else {
        const blob = await renderElementAsPngBlob(surface);
        setImagePreview({ url: URL.createObjectURL(blob) });
      }
    } catch (error) {
      const reason = describeCopyImageError(error);
      console.warn("复制图片失败", {
        clipboard: {
          hasClipboard: Boolean(navigator.clipboard),
          hasWrite: Boolean(navigator.clipboard?.write),
          hasWriteText: Boolean(navigator.clipboard?.writeText),
        },
        clipboardItem: {
          hasClipboardItem: typeof ClipboardItem !== "undefined",
          hasSupports: typeof ClipboardItem !== "undefined" && typeof ClipboardItem.supports === "function",
          supportsPng:
            typeof ClipboardItem !== "undefined" && typeof ClipboardItem.supports === "function"
              ? ClipboardItem.supports("image/png")
              : "unknown",
        },
        error,
        isSecureContext: window.isSecureContext,
        locationProtocol: window.location.protocol,
      });
      setCopiedImageMessageId(null);
      setCopyImageError({ messageId: message.message_id, reason });
      window.setTimeout(() => {
        setCopyImageError((current) =>
          current?.messageId === message.message_id && current.reason === reason ? null : current,
        );
      }, 2600);
    } finally {
      setCopyingImageMessageId((current) => (current === message.message_id ? null : current));
    }
  }

  function closeImagePreview() {
    setImagePreview((current) => {
      if (current?.url) {
        URL.revokeObjectURL(current.url);
      }
      return null;
    });
  }

  function setCopySurfaceRef(messageId: string, node: HTMLDivElement | null) {
    if (node) {
      copySurfaceRefs.current.set(messageId, node);
      return;
    }
    copySurfaceRefs.current.delete(messageId);
  }

  async function handleOpenToolResult(toolMessageId: string, label: string) {
    if (!props.activeSessionId) {
      setToolResult({ title: `工具结果 · ${label}`, content: "", loading: false, error: "当前会话还没有落盘。" });
      return;
    }
    setToolResult({ title: `工具结果 · ${label}`, content: "", loading: true });
    try {
      const message = await fetchChatToolMessage(props.activeSessionId, toolMessageId);
      setToolResult({ title: `工具结果 · ${label}`, content: formatToolResultContent(message.content), loading: false });
    } catch (error) {
      setToolResult({
        title: `工具结果 · ${label}`,
        content: "",
        loading: false,
        error: error instanceof Error ? error.message : "读取工具结果失败",
      });
    }
  }

  return (
    <div className="chat-message-list-shell">
      <div
        className={props.showJumpToBottom ? "chat-message-list with-jump-to-bottom" : "chat-message-list"}
        ref={props.listRef}
        onScroll={handleScroll}
      >
        {props.messages.length === 0 && props.emptyState === "overview" ? (
          <div className="chat-empty-state">
            <strong>本地消息已就绪</strong>
            <span>等待一个股票、产业链或消息线索。</span>
          </div>
        ) : null}
        <AnimatePresence initial={false}>
          {props.messages.map((message) => {
            const status = message.role === "assistant" ? statusForChatMessage(message.metadata) : "";
            const activities = toolActivities(message.metadata.tool_activities);
            const traceItems = normalizeTraceItems(chatTraceItems(message.metadata.trace_items));
            const hasAssistantTrace = traceItems.some((item) => item.type === "assistant");
            const hasCompletedAssistantContent =
              message.role === "assistant" && Boolean(message.content.trim()) && !message.metadata.streaming;
            const isCopied = copiedMessageId === message.message_id;
            const isImageCopied = copiedImageMessageId === message.message_id;
            const imageCopyError = copyImageError?.messageId === message.message_id ? copyImageError : null;
            const isImageCopyFailed = Boolean(imageCopyError);
            const isCopyingImage = copyingImageMessageId === message.message_id;
            return (
              <motion.article
                className={`chat-message chat-message-${message.role}`}
                key={message.message_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.16 }}
              >
                <div className="chat-message-copy-surface" ref={(node) => setCopySurfaceRef(message.message_id, node)}>
                  {message.role === "assistant" && (status || activities.length > 0 || traceItems.length > 0) ? (
                    <AssistantTrace
                      activities={activities}
                      Content={Content}
                      onOpenToolResult={handleOpenToolResult}
                      status={status || "正在处理"}
                      streaming={Boolean(message.metadata.streaming)}
                      traceItems={traceItems}
                    />
                  ) : null}
                  {message.content && !hasAssistantTrace ? (
                    <>
                      <SmoothStreamingContent
                        Content={Content}
                        content={message.content}
                        streaming={Boolean(message.metadata.streaming)}
                      />
                      {message.metadata.streaming ? <i className="chat-stream-cursor" aria-hidden="true" /> : null}
                    </>
                  ) : !hasAssistantTrace && message.metadata.streaming ? (
                    <div className="chat-typing" aria-label="生成中">
                      <span>正在整理</span>
                      <em />
                      <em />
                      <em />
                    </div>
                  ) : null}
                </div>
                {hasCompletedAssistantContent ? (
                  <div className="chat-message-actions">
                    <button
                      className={isCopied ? "chat-message-action chat-message-copy is-copied" : "chat-message-action chat-message-copy"}
                      type="button"
                      aria-label={isCopied ? "已复制回复" : "复制回复"}
                      title={isCopied ? "已复制" : "复制"}
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleCopyMessage(message);
                      }}
                    >
                      {isCopied ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                    <button
                      className={
                        isImageCopied
                          ? "chat-message-action is-copied"
                          : isImageCopyFailed
                            ? "chat-message-action is-error"
                            : "chat-message-action"
                      }
                      type="button"
                      aria-label={isImageCopied ? "已复制图片" : isImageCopyFailed ? "复制图片失败" : "复制为图片"}
                      title={isImageCopied ? "已复制图片" : isImageCopyFailed ? "复制图片失败" : "复制图片"}
                      disabled={isCopyingImage}
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleCopyMessageImage(message);
                      }}
                    >
                      {isImageCopied ? <Check size={14} /> : isImageCopyFailed ? <CircleAlert size={14} /> : <ImageIcon size={14} />}
                    </button>
                    {imageCopyError ? <span className="chat-message-copy-error">{imageCopyError.reason}</span> : null}
                    <button
                      className="chat-message-action"
                      type="button"
                      aria-label="打开阅读视图"
                      title="阅读视图"
                      onClick={(event) => {
                        event.stopPropagation();
                        setReadingMessage(message);
                      }}
                    >
                      <Maximize2 size={14} />
                    </button>
                  </div>
                ) : null}
              </motion.article>
            );
          })}
        </AnimatePresence>
        <div ref={props.endRef} />
      </div>
      {props.showJumpToBottom ? (
        <button className="chat-jump-to-bottom" type="button" onClick={props.onJumpToBottom}>
          <ArrowDown size={14} />
          <span>新内容</span>
        </button>
      ) : null}
      {readingMessage ? <ChatReadingModal content={readingMessage.content} onClose={() => setReadingMessage(null)} /> : null}
      {toolResult ? <ToolResultModal result={toolResult} onClose={() => setToolResult(null)} /> : null}
      {imagePreview ? <ImagePreviewModal preview={imagePreview} onClose={closeImagePreview} /> : null}
    </div>
  );
}

type ToolResultState = {
  title: string;
  content: string;
  loading: boolean;
  error?: string;
};

type CopyImageErrorState = {
  messageId: string;
  reason: string;
};

type ImagePreviewState = {
  url: string;
};

function describeCopyImageError(error: unknown): string {
  const name = error instanceof Error ? error.name : "";
  const message = error instanceof Error ? error.message : String(error);
  const detail = `${name} ${message}`.toLowerCase();
  if (detail.includes("copy-image:insecure-context")) {
    return "当前页面不是 HTTPS/localhost，浏览器禁止写入图片剪贴板。";
  }
  if (detail.includes("copy-image:missing-navigator-clipboard")) {
    return "缺 navigator.clipboard：当前浏览器没有开放异步剪贴板。";
  }
  if (detail.includes("copy-image:missing-clipboard-write")) {
    return "缺 navigator.clipboard.write：当前浏览器不能写入图片剪贴板。";
  }
  if (detail.includes("copy-image:missing-clipboard-item")) {
    return "缺 ClipboardItem：当前浏览器不能写入图片剪贴板。";
  }
  if (detail.includes("copy-image:unsupported-image-png")) {
    return "ClipboardItem 不支持 image/png，当前浏览器不能复制 PNG 图片。";
  }
  if (detail.includes("notallowed")) {
    return "图片复制被浏览器拒绝：检查 HTTPS、页面聚焦和 Safari 手势限制。";
  }
  if (detail.includes("clipboard") || detail.includes("not support") || detail.includes("不支持")) {
    return "当前浏览器不支持写入图片剪贴板。";
  }
  if (detail.includes("tainted") || detail.includes("security") || detail.includes("canvas") || detail.includes("生成图片失败")) {
    return "生成 PNG 失败：可能是 Safari 的 DOM 转图限制。";
  }
  return message ? `图片复制失败：${message}` : "图片复制失败，详情见控制台。";
}

function ChatReadingModal({ content, onClose, title = "助手回复" }: { content: string; onClose: () => void; title?: string }) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return createPortal(
    <div
      className="chat-reading-modal-shell"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section className="chat-reading-modal" role="dialog" aria-modal="true" aria-label="阅读视图">
        <header className="chat-reading-modal-head">
          <div>
            <span>阅读视图</span>
            <strong>{title}</strong>
          </div>
          <button className="icon-btn" type="button" aria-label="关闭阅读视图" title="关闭" onClick={onClose}>
            <X size={16} />
          </button>
        </header>
        <div className="chat-reading-modal-body">
          <DrawerMarkdownContent content={content} />
        </div>
      </section>
    </div>,
    document.body,
  );
}

function ImagePreviewModal({ preview, onClose }: { preview: ImagePreviewState; onClose: () => void }) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return createPortal(
    <div
      className="chat-reading-modal-shell"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section className="chat-image-preview-modal" role="dialog" aria-modal="true" aria-label="图片预览">
        <header className="chat-reading-modal-head">
          <div>
            <span>图片预览</span>
            <strong>长按图片保存或分享</strong>
          </div>
          <button className="icon-btn" type="button" aria-label="关闭图片预览" title="关闭" onClick={onClose}>
            <X size={16} />
          </button>
        </header>
        <div className="chat-image-preview-body">
          <img alt="助手回复截图" src={preview.url} />
        </div>
      </section>
    </div>,
    document.body,
  );
}

function ToolResultModal({ result, onClose }: { result: ToolResultState; onClose: () => void }) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return createPortal(
    <div
      className="chat-reading-modal-shell"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section className="chat-reading-modal" role="dialog" aria-modal="true" aria-label="工具结果">
        <header className="chat-reading-modal-head">
          <div>
            <span>按需加载</span>
            <strong>{result.title}</strong>
          </div>
          <button className="icon-btn" type="button" aria-label="关闭工具结果" title="关闭" onClick={onClose}>
            <X size={16} />
          </button>
        </header>
        <div className="chat-reading-modal-body">
          {result.loading ? <p className="chat-tool-result-state">正在读取工具结果...</p> : null}
          {result.error ? <p className="chat-tool-result-state is-error">{result.error}</p> : null}
          {!result.loading && !result.error ? (
            <pre className="chat-tool-result-raw">
              <code>{result.content}</code>
            </pre>
          ) : null}
        </div>
      </section>
    </div>,
    document.body,
  );
}

const TRANSIENT_STATUS_LABELS = new Set([
  "正在推理",
  "正在查询本地数据",
  "正在整理结果",
  "正在生成回答",
  MODEL_THINKING_STATUS,
]);
const PROCESS_SUMMARIES = new Set([
  "我会先拆解你的问题，确定需要查哪些证据。",
  "我会先准备要查的数据，再按证据强度比较。",
  "我会先拉取候选、消息和行情相关数据，之后再统一比较。",
  "我会先从策略候选里拿到可比较的标的池。",
  "我会回到本地消息里补原文证据、来源密度和反证。",
  "我会补证据链详情，检查触发、验证点和暂缓条件。",
  "我会补行情和资金流，确认市场是否已经定价。",
  "我会补必要的分析模板，再把结果整理成结论。",
  "我会补齐下一步判断需要的数据。",
  "工具结果开始返回，我会把新增数据并入判断。",
  "判断已经形成，开始整理成可读回答。",
]);

type ToolActivityDisplayItem = ToolActivityItem & {
  count: number;
};

type TraceDisplayItem =
  | ChatTraceItem
  | {
      key: string;
      type: "tool_group";
      label: string;
      status: ToolActivityItem["status"];
      count: number;
    };

function normalizeTraceItems(items: ChatTraceItem[]): ChatTraceItem[] {
  return items.filter((item) => {
    if (item.type === "reasoning") {
      return false;
    }
    if (item.type === "status") {
      return !TRANSIENT_STATUS_LABELS.has(item.label);
    }
    if (item.type === "summary") {
      return PROCESS_SUMMARIES.has(item.content);
    }
    return true;
  });
}

function AssistantTrace({
  activities,
  Content,
  onOpenToolResult,
  status,
  streaming,
  traceItems,
}: {
  activities: ToolActivityItem[];
  Content: ComponentType<{ content: string }>;
  onOpenToolResult: (toolMessageId: string, label: string) => void;
  status: string;
  streaming: boolean;
  traceItems: ChatTraceItem[];
}) {
  const hasProcess = traceItems.length > 0 || activities.length > 0;
  const hasAssistantTrace = traceItems.some((item) => item.type === "assistant");
  const hasFinalAssistantTrace = traceItems.some((item) => item.type === "assistant" && isFinalAssistantContent(item.content));
  const logEventCount = traceItems.filter((item) => item.type !== "assistant").length;
  const [expanded, setExpanded] = useState(streaming && !hasFinalAssistantTrace);
  const previousHasFinalAssistantTraceRef = useRef(hasFinalAssistantTrace);
  const userToggledExpandedRef = useRef(false);

  useEffect(() => {
    const changed = previousHasFinalAssistantTraceRef.current !== hasFinalAssistantTrace;
    previousHasFinalAssistantTraceRef.current = hasFinalAssistantTrace;
    if (!changed || userToggledExpandedRef.current) {
      return;
    }
    setExpanded(!hasFinalAssistantTrace && streaming);
  }, [hasFinalAssistantTrace, streaming]);

  function toggleExpanded() {
    userToggledExpandedRef.current = true;
    setExpanded((value) => !value);
  }

  if (!hasProcess) {
    return (
      <div className="chat-agent-status">
        {status}
        <StreamingPulse status={status} streaming={streaming} />
      </div>
    );
  }

  if (hasAssistantTrace) {
    return (
      <div className={expanded ? "chat-agent-trace is-open" : "chat-agent-trace"}>
        <button
          className="chat-agent-summary"
          type="button"
          aria-expanded={expanded}
          onClick={toggleExpanded}
        >
          <span>{status}</span>
          <StreamingPulse status={status} streaming={streaming} />
          {logEventCount > 0 ? <em>消息日志事件 {logEventCount} 条</em> : null}
          <ChevronDown size={14} aria-hidden="true" />
        </button>
        <div className="chat-agent-process">
          <ChatTraceTimeline
            Content={Content}
            items={traceItems}
            onOpenToolResult={onOpenToolResult}
            showProcess={expanded}
            streaming={streaming}
          />
        </div>
      </div>
    );
  }

  return (
    <div className={expanded ? "chat-agent-trace is-open" : "chat-agent-trace"}>
      <button
        className="chat-agent-summary"
        type="button"
        aria-expanded={expanded}
        onClick={toggleExpanded}
      >
        <span>{status}</span>
        <StreamingPulse status={status} streaming={streaming} />
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {expanded ? (
        <div className="chat-agent-process">
          {traceItems.length > 0 ? (
            <ChatProcessTimeline items={traceItems} onOpenToolResult={onOpenToolResult} streaming={streaming} />
          ) : (
            <ChatToolActivityList activities={activities} onOpenToolResult={onOpenToolResult} />
          )}
        </div>
      ) : null}
    </div>
  );
}

function StreamingPulse({ status, streaming }: { status: string; streaming: boolean }) {
  if (!streaming || status.includes("连接")) {
    return null;
  }
  return <span className="chat-agent-live-pulse" aria-hidden="true" />;
}

function SmoothStreamingContent({
  Content,
  content,
  streaming,
}: {
  Content: ComponentType<{ content: string }>;
  content: string;
  streaming: boolean;
}) {
  const [displayContent, setDisplayContent] = useState(content);

  useEffect(() => {
    if (displayContent === content) {
      return undefined;
    }
    if (!content.startsWith(displayContent)) {
      setDisplayContent(content);
      return undefined;
    }

    const timer = window.setTimeout(() => {
      const remaining = content.length - displayContent.length;
      setDisplayContent(content.slice(0, displayContent.length + revealStepForRemaining(remaining)));
    }, 34);

    return () => window.clearTimeout(timer);
  }, [content, displayContent]);

  const className =
    content.startsWith(displayContent) && displayContent.length < content.length
      ? "chat-stream-smooth is-streaming is-catching-up"
      : streaming
        ? "chat-stream-smooth is-streaming"
        : "chat-stream-smooth";

  return (
    <div className={className}>
      <Content content={displayContent} />
    </div>
  );
}

function revealStepForRemaining(remaining: number): number {
  if (remaining > 1200) {
    return 96;
  }
  if (remaining > 600) {
    return 56;
  }
  if (remaining > 240) {
    return 32;
  }
  if (remaining > 80) {
    return 16;
  }
  if (remaining > 24) {
    return 8;
  }
  return 4;
}

function isFinalAssistantContent(content: string): boolean {
  const text = content.trim();
  if (!text) {
    return false;
  }
  return !isProcessAssistantContent(text);
}

function isProcessAssistantContent(content: string): boolean {
  const text = content.replace(/\s+/g, " ").trim();
  if (!text) {
    return true;
  }
  if (/^(我(来|会|先|将|需要|继续|准备|再)?|接下来|下一步|先|再)(查|查询|拉|拉取|补|补齐|确认|看一下|准备|获取|核对|验证)/.test(text)) {
    return true;
  }
  if (/^(我(来|会|先|将|需要|继续|准备|再)?|接下来|下一步|再).*(然后|再|之后|以便|用于|基于).*(测算|估算|判断|比较|分析|确认|验证)/.test(text)) {
    return true;
  }
  return false;
}

function ChatProcessTimeline({
  items,
  onOpenToolResult,
  streaming,
}: {
  items: ChatTraceItem[];
  onOpenToolResult: (toolMessageId: string, label: string) => void;
  streaming: boolean;
}) {
  const visibleItems = groupTraceItems(items.filter((item) => item.type !== "assistant"));
  const activeStatusKey = streaming ? latestItemKey(visibleItems, "status") : undefined;
  const activeSummaryKey = streaming && !activeStatusKey ? visibleItems[visibleItems.length - 1]?.key : undefined;
  const cursorKey = streaming ? visibleItems[visibleItems.length - 1]?.key : undefined;
  return (
    <div className="chat-trace-timeline">
      {visibleItems.map((item) =>
        item.type === "tool_group" ? (
          <ChatTraceToolRow
            count={item.count}
            cursor={item.key === cursorKey}
            key={item.key}
            label={item.label}
            onOpenToolResult={onOpenToolResult}
            status={item.status}
          />
        ) : item.type === "tool" ? (
          <ChatTraceToolRow
            count={1}
            cursor={item.key === cursorKey}
            key={item.key}
            label={item.label}
            onOpenToolResult={onOpenToolResult}
            status={item.status}
            toolMessageId={item.toolMessageId}
          />
        ) : item.type === "status" ? (
          <ChatTraceStatusRow key={item.key} active={item.key === activeStatusKey} cursor={item.key === cursorKey} label={item.label} />
        ) : item.type === "summary" ? (
          <ChatTraceSummaryRow key={item.key} active={item.key === activeSummaryKey} content={item.content} cursor={item.key === cursorKey} />
        ) : item.type === "error" ? (
          <ChatTraceErrorRow key={item.key} cursor={item.key === cursorKey} message={item.message} />
        ) : null,
      )}
    </div>
  );
}

function ChatTraceTimeline({
  Content,
  items,
  onOpenToolResult,
  showProcess,
  streaming,
}: {
  Content: ComponentType<{ content: string }>;
  items: ChatTraceItem[];
  onOpenToolResult: (toolMessageId: string, label: string) => void;
  showProcess: boolean;
  streaming: boolean;
}) {
  const displayItems = groupTraceItems(items);
  const visibleItems = showProcess ? displayItems : displayItems.filter((item) => item.type === "assistant");
  const cursorKey = streaming ? visibleItems[visibleItems.length - 1]?.key : undefined;
  const activeStatusKey = streaming ? latestItemKey(displayItems, "status") : undefined;
  const activeSummaryKey = streaming && !activeStatusKey ? displayItems[displayItems.length - 1]?.key : undefined;
  return (
    <div className="chat-trace-timeline">
      {displayItems.map((item) => {
        if (item.type === "assistant") {
          return (
            <div className="chat-trace-entry chat-trace-entry-assistant" key={item.key}>
              <span className="chat-trace-node" aria-hidden="true" />
              <div className="chat-trace-body chat-trace-assistant">
                <SmoothStreamingContent Content={Content} content={item.content} streaming={streaming && item.key === cursorKey} />
                {item.key === cursorKey ? <i className="chat-stream-cursor" aria-hidden="true" /> : null}
              </div>
            </div>
          );
        }
        if (!showProcess) {
          return null;
        }
        if (item.type === "tool_group") {
          return (
            <ChatTraceToolRow
              count={item.count}
              cursor={item.key === cursorKey}
              key={item.key}
              label={item.label}
              onOpenToolResult={onOpenToolResult}
              status={item.status}
            />
          );
        }
        if (item.type === "tool") {
          return (
            <ChatTraceToolRow
              count={1}
              cursor={item.key === cursorKey}
              key={item.key}
              label={item.label}
              onOpenToolResult={onOpenToolResult}
              status={item.status}
              toolMessageId={item.toolMessageId}
            />
          );
        }
        if (item.type === "status") {
          return <ChatTraceStatusRow key={item.key} active={item.key === activeStatusKey} cursor={item.key === cursorKey} label={item.label} />;
        }
        if (item.type === "summary") {
          return <ChatTraceSummaryRow key={item.key} active={item.key === activeSummaryKey} content={item.content} cursor={item.key === cursorKey} />;
        }
        if (item.type === "error") {
          return <ChatTraceErrorRow key={item.key} cursor={item.key === cursorKey} message={item.message} />;
        }
        return null;
      })}
    </div>
  );
}

function latestItemKey(items: TraceDisplayItem[], type: TraceDisplayItem["type"]): string | undefined {
  return [...items].reverse().find((item) => item.type === type)?.key;
}

function groupTraceItems(items: ChatTraceItem[]): TraceDisplayItem[] {
  return items.reduce<TraceDisplayItem[]>((groups, item) => {
    if (item.type !== "tool") {
      groups.push(item);
      return groups;
    }
    if (item.toolMessageId) {
      groups.push(item);
      return groups;
    }
    const last = groups[groups.length - 1];
    if (last?.type === "tool_group" && last.label === item.label && last.status === item.status) {
      last.count += 1;
      return groups;
    }
    groups.push({
      key: `tool-group-${item.key}`,
      type: "tool_group",
      label: item.label,
      status: item.status,
      count: 1,
    });
    return groups;
  }, []);
}

function ChatTraceStatusRow({ active, cursor, label }: { active?: boolean; cursor?: boolean; label: string }) {
  return (
    <div className={active ? "chat-trace-entry chat-trace-entry-status is-active" : "chat-trace-entry chat-trace-entry-status"}>
      <span className="chat-trace-node" aria-hidden="true" />
      <span className="chat-trace-body">
        {label}
        {cursor ? <i className="chat-stream-cursor" aria-hidden="true" /> : null}
      </span>
    </div>
  );
}

function ChatTraceSummaryRow({ active, content, cursor }: { active?: boolean; content: string; cursor?: boolean }) {
  return (
    <div className={active ? "chat-trace-entry chat-trace-entry-summary is-active" : "chat-trace-entry chat-trace-entry-summary"}>
      <span className="chat-trace-node" aria-hidden="true" />
      <span className="chat-trace-body">
        {content}
        {cursor ? <i className="chat-stream-cursor" aria-hidden="true" /> : null}
      </span>
    </div>
  );
}

function ChatTraceErrorRow({ cursor, message }: { cursor?: boolean; message: string }) {
  return (
    <div className="chat-trace-entry chat-trace-entry-error">
      <span className="chat-trace-node" aria-hidden="true">
        <CircleAlert size={14} />
      </span>
      <span className="chat-trace-body">
        {message}
        {cursor ? <i className="chat-stream-cursor" aria-hidden="true" /> : null}
      </span>
    </div>
  );
}

function ChatTraceToolRow({
  count,
  cursor,
  label,
  onOpenToolResult,
  status,
  toolMessageId,
}: {
  count: number;
  cursor?: boolean;
  label: string;
  onOpenToolResult: (toolMessageId: string, label: string) => void;
  status: ToolActivityItem["status"];
  toolMessageId?: string;
}) {
  return (
    <div className={`chat-trace-entry chat-trace-entry-tool chat-trace-entry-tool-${status}`}>
      <span className="chat-trace-node" aria-hidden="true">
        <SquareTerminal size={14} />
      </span>
      <span className="chat-trace-body">
        <span>{toolActivitySummary(status, count)}</span>
        <em>{label}</em>
        {status === "completed" && toolMessageId ? (
          <button className="chat-tool-result-button" type="button" onClick={() => onOpenToolResult(toolMessageId, label)}>
            结果
          </button>
        ) : null}
        {cursor ? <i className="chat-stream-cursor" aria-hidden="true" /> : null}
      </span>
    </div>
  );
}

function ChatToolActivityList({
  activities,
  onOpenToolResult,
}: {
  activities: ToolActivityItem[];
  onOpenToolResult: (toolMessageId: string, label: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const groupedActivities = groupConsecutiveToolActivities(activities);
  const hasGroupedItems = groupedActivities.some((activity) => activity.count > 1);
  const displayActivities = expanded ? activities.map((activity) => ({ ...activity, count: 1 })) : groupedActivities;

  return (
    <div className="chat-tool-activity-block">
      <ul className="chat-tool-activity-list">
        {displayActivities.map((activity) => (
          <ChatToolActivityRow
            count={activity.count}
            key={activity.key}
            label={activity.label}
            onOpenToolResult={onOpenToolResult}
            status={activity.status}
            toolMessageId={activity.toolMessageId}
          />
        ))}
      </ul>
      {hasGroupedItems ? (
        <button className="chat-tool-activity-toggle" type="button" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "合并同类工具" : `展开 ${activities.length} 条工具明细`}
        </button>
      ) : null}
    </div>
  );
}

function ChatToolActivityRow({
  count,
  label,
  onOpenToolResult,
  status,
  toolMessageId,
}: {
  count: number;
  label: string;
  onOpenToolResult: (toolMessageId: string, label: string) => void;
  status: ToolActivityItem["status"];
  toolMessageId?: string;
}) {
  return (
    <li className={`chat-tool-activity-${status}`}>
      <SquareTerminal size={14} aria-hidden="true" />
      <span>{toolActivitySummary(status, count)}</span>
      <em>{label}</em>
      {status === "completed" && toolMessageId ? (
        <button className="chat-tool-result-button" type="button" onClick={() => onOpenToolResult(toolMessageId, label)}>
          结果
        </button>
      ) : null}
    </li>
  );
}

function toolActivitySummary(status: ToolActivityItem["status"], count: number): string {
  const verb = status === "running" ? "正在运行" : "已运行";
  return `${verb} ${count} 条工具调用`;
}

function groupConsecutiveToolActivities(activities: ToolActivityItem[]): ToolActivityDisplayItem[] {
  return activities.reduce<ToolActivityDisplayItem[]>((groups, activity) => {
    if (activity.toolMessageId) {
      groups.push({ ...activity, count: 1 });
      return groups;
    }
    const last = groups[groups.length - 1];
    if (last && last.label === activity.label && last.status === activity.status) {
      last.count += 1;
      return groups;
    }
    groups.push({ ...activity, count: 1 });
    return groups;
  }, []);
}

function formatToolResultContent(content: string): string {
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return content;
  }
}

function isNearBottom(element: HTMLDivElement): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight < 80;
}
