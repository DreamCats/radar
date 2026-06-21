import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { fetchConversations, fetchMessageGroups, fetchMessages } from "../api/radarApi";
import { WechatListChatLauncher, WechatThreadHeader } from "../components/WechatChatEntrypoints";
import { Avatar, WechatFilters } from "../components/WechatControls";
import { formatTime } from "../lib/datetime";
import { panelMotionState } from "../lib/motion";
import {
  buildSenderStats,
  displayName,
  isSelfName,
  matchesMessage,
  mergeMessages,
  normalizeKeyword,
  sourceKey,
} from "../lib/wechat";
import type { MessageConversationItem, MessageConversationPage, MessageConversationQuery, MessageItem } from "../types";

const defaultQuery: MessageConversationQuery = {
  limit: 40,
};

const threadLimit = 30;
const conversationSkeletonItems = Array.from({ length: 7 }, (_, index) => index);

type ThreadScrollIntent = { mode: "bottom" } | { mode: "preserve"; scrollTop: number; scrollHeight: number };

function formatThreadEvidence(item: MessageItem) {
  return `${formatTime(item.message_time)} ${displayName(item)}：${item.raw_content}`;
}

export function WechatPage() {
  const shouldReduceMotion = useReducedMotion();
  const [query, setQuery] = useState<MessageConversationQuery>(defaultQuery);
  const [conversationPage, setConversationPage] = useState<MessageConversationPage>({ items: [] });
  const [history, setHistory] = useState<MessageConversationQuery[]>([]);
  const [groupNames, setGroupNames] = useState<string[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [threadItems, setThreadItems] = useState<MessageItem[]>([]);
  const [threadCursor, setThreadCursor] = useState<{ time?: string | null; id?: string | null }>({});
  const [selectedSender, setSelectedSender] = useState<string | null>(null);
  const [senderQuery, setSenderQuery] = useState("");
  const [threadKeyword, setThreadKeyword] = useState("");
  const [mobileThreadOpen, setMobileThreadOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [groupNamesLoading, setGroupNamesLoading] = useState(false);
  const [threadLoading, setThreadLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threadError, setThreadError] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const threadScrollIntentRef = useRef<ThreadScrollIntent | null>(null);
  const mobileThreadOpenRef = useRef(false);
  const mobileThreadHistoryRef = useRef(false);

  const conversations = conversationPage.items;
  const selectedConversation = conversations.find((item) => item.key === selectedKey) ?? conversations[0] ?? null;
  const senderStats = useMemo(() => buildSenderStats(threadItems), [threadItems]);
  const matchedSenderStats = useMemo(() => {
    const keyword = normalizeKeyword(senderQuery);
    const matched = keyword
      ? senderStats.filter((item) => normalizeKeyword(item.sender).includes(keyword))
      : senderStats;
    return matched.slice(0, 18);
  }, [senderQuery, senderStats]);
  const filteredThreadItems = useMemo(() => {
    return threadItems.filter((item) => {
      if (selectedSender && item.sender !== selectedSender) {
        return false;
      }
      return matchesMessage(item, threadKeyword);
    });
  }, [selectedSender, threadItems, threadKeyword]);
  const canNext = Boolean(conversationPage.next_cursor_time && conversationPage.next_cursor_key);
  const canLoadOlder = Boolean(threadCursor.time && threadCursor.id);
  const showConversationSkeleton = loading && conversations.length === 0;
  const conversationMotion = panelMotionState(shouldReduceMotion);

  useEffect(() => {
    void loadConversations(defaultQuery);
  }, []);

  useEffect(() => {
    mobileThreadOpenRef.current = mobileThreadOpen;
  }, [mobileThreadOpen]);

  useEffect(() => {
    const onPopState = (event: PopStateEvent) => {
      if (mobileThreadOpenRef.current && !event.state?.radarWechatThread) {
        mobileThreadHistoryRef.current = false;
        setMobileThreadOpen(false);
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setGroupNamesLoading(true);
    void fetchMessageGroups({ source: query.source, limit: 200 })
      .then((groups) => {
        if (!cancelled) {
          setGroupNames(groups.map((item) => item.group_name).filter((name) => !isSelfName(name)));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setGroupNames([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setGroupNamesLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [query.source]);

  useEffect(() => {
    setSelectedSender(null);
    setSenderQuery("");
    setThreadKeyword("");
    setThreadItems([]);
    setThreadCursor({});
    if (selectedConversation) {
      void loadThread(selectedConversation);
    }
  }, [selectedConversation?.key]);

  useLayoutEffect(() => {
    const thread = threadRef.current;
    const intent = threadScrollIntentRef.current;
    if (!thread || !intent) {
      return;
    }

    if (intent.mode === "bottom") {
      thread.scrollTop = thread.scrollHeight;
    } else {
      thread.scrollTop = thread.scrollHeight - intent.scrollHeight + intent.scrollTop;
    }
    threadScrollIntentRef.current = null;
  }, [threadItems]);

  async function loadConversations(nextQuery: MessageConversationQuery, pushHistory = false) {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchConversations(nextQuery);
      setConversationPage(data);
      setQuery(nextQuery);
      setSelectedKey((current) =>
        current && data.items.some((item) => item.key === current) ? current : data.items[0]?.key ?? null,
      );
      if (pushHistory) {
        setHistory((items) => [...items, query]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "查询失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadThread(conversation: MessageConversationItem, older = false) {
    if (older && (!threadCursor.time || !threadCursor.id)) {
      return;
    }
    setThreadLoading(true);
    setThreadError(null);
    const thread = threadRef.current;
    const scrollIntent: ThreadScrollIntent =
      older && thread
        ? { mode: "preserve", scrollTop: thread.scrollTop, scrollHeight: thread.scrollHeight }
        : { mode: "bottom" };
    try {
      const data = await fetchMessages({
        source: sourceKey(conversation.source),
        group_name: conversation.source === "个人群" ? conversation.title : undefined,
        sender: conversation.source === "个人消息" ? conversation.title : undefined,
        cursor_time: older ? threadCursor.time ?? undefined : undefined,
        cursor_id: older ? threadCursor.id ?? undefined : undefined,
        limit: threadLimit,
      });
      threadScrollIntentRef.current = scrollIntent;
      setThreadItems((current) => (older ? mergeMessages(current, data.items) : mergeMessages([], data.items)));
      setThreadCursor({ time: data.next_cursor_time, id: data.next_cursor_id });
    } catch (err) {
      threadScrollIntentRef.current = null;
      setThreadError(err instanceof Error ? err.message : "消息加载失败");
    } finally {
      setThreadLoading(false);
    }
  }

  function loadOlderThread() {
    if (selectedConversation) {
      void loadThread(selectedConversation, true);
    }
  }

  function openMobileThread(conversation: MessageConversationItem) {
    setSelectedKey(conversation.key);
    setMobileThreadOpen(true);
    if (isMobileThreadLayout() && !mobileThreadOpenRef.current) {
      window.history.pushState({ radarWechatThread: conversation.key }, "", window.location.href);
      mobileThreadHistoryRef.current = true;
    }
  }

  function closeMobileThread() {
    if (mobileThreadHistoryRef.current) {
      mobileThreadHistoryRef.current = false;
      window.history.back();
      return;
    }
    setMobileThreadOpen(false);
  }

  return (
    <section className="wechat-page">
      <WechatFilters
        groupNames={groupNames}
        groupNamesLoading={groupNamesLoading}
        loading={loading}
        query={query}
        onChange={setQuery}
        onSubmit={() => {
          setHistory([]);
          setMobileThreadOpen(false);
          void loadConversations({ ...query, cursor_time: undefined, cursor_key: undefined });
        }}
      />

      <div className={mobileThreadOpen ? "wechat-workspace thread-open" : "wechat-workspace"}>
        <aside className="wechat-conversation-panel content-panel panel">
          <div className="wechat-panel-head">
            <div>
              <h2>微信</h2>
              <span>{conversations.length} 个会话</span>
            </div>
            <WechatListChatLauncher conversations={conversations} query={query} canNext={canNext} />
          </div>
          {error && <p className="error-line">{error}</p>}
          <div
            className={showConversationSkeleton ? "wechat-conversation-list is-loading" : "wechat-conversation-list"}
            aria-busy={showConversationSkeleton}
          >
            {showConversationSkeleton && conversationSkeletonItems.map((item) => <ConversationSkeleton key={item} />)}
            <AnimatePresence initial={false}>
              {!showConversationSkeleton &&
                conversations.map((conversation) => (
                  <motion.button
                    animate={conversationMotion.animate}
                    className={conversation.key === selectedConversation?.key ? "wechat-conversation active" : "wechat-conversation"}
                    exit={conversationMotion.exit}
                    initial={conversationMotion.initial}
                    key={conversation.key}
                    layout
                    transition={conversationMotion.transition}
                    type="button"
                    onClick={() => openMobileThread(conversation)}
                  >
                    <Avatar name={conversation.title} />
                    <span className="wechat-conversation-main">
                      <span className="wechat-conversation-title">
                        <strong>{conversation.title}</strong>
                        <em>{formatTime(conversation.latest_time)}</em>
                      </span>
                      <span className="wechat-conversation-preview">{conversation.latest_content}</span>
                      <span className="wechat-conversation-meta">
                        {conversation.source} · {conversation.latest_sender}
                      </span>
                    </span>
                  </motion.button>
                ))}
            </AnimatePresence>
            {loading && conversations.length > 0 && (
              <div className="wechat-list-refresh" role="status" aria-live="polite">
                正在刷新会话
              </div>
            )}
            {!loading && conversations.length === 0 && <p className="empty-line">暂无数据</p>}
          </div>
          <div className="wechat-pager">
            <button
              className="mini-button"
              type="button"
              disabled={history.length === 0 || loading}
              onClick={() => {
                const previous = history[history.length - 1];
                if (previous) {
                  setHistory((items) => items.slice(0, -1));
                  void loadConversations(previous);
                }
              }}
              title="上一页"
            >
              <ChevronLeft size={15} />
            </button>
            <button
              className="mini-button"
              type="button"
              disabled={!canNext || loading}
              onClick={() =>
                void loadConversations(
                  {
                    ...query,
                    cursor_time: conversationPage.next_cursor_time ?? undefined,
                    cursor_key: conversationPage.next_cursor_key ?? undefined,
                  },
                  true,
                )
              }
              title="下一页"
            >
              <ChevronRight size={15} />
            </button>
          </div>
        </aside>

        <section className="wechat-thread-panel content-panel panel">
          {selectedConversation ? (
            <>
              <WechatThreadHeader
                conversation={selectedConversation}
                filteredCount={filteredThreadItems.length}
                matchedSenderStats={matchedSenderStats}
                selectedSender={selectedSender}
                senderQuery={senderQuery}
                threadEvidence={filteredThreadItems.slice(-20).map(formatThreadEvidence)}
                threadKeyword={threadKeyword}
                totalCount={threadItems.length}
                onSenderChange={setSelectedSender}
                onSenderQueryChange={setSenderQuery}
                onThreadKeywordChange={setThreadKeyword}
                onBack={closeMobileThread}
              />
              <div
                className="wechat-thread"
                ref={threadRef}
                onScroll={(event) => {
                  if (event.currentTarget.scrollTop < 24 && canLoadOlder && !threadLoading) {
                    loadOlderThread();
                  }
                }}
              >
                {canLoadOlder && (
                  <button
                    className="wechat-thread-older"
                    type="button"
                    disabled={threadLoading}
                    onClick={loadOlderThread}
                  >
                    {threadLoading ? "加载中" : "更早消息"}
                  </button>
                )}
                {threadError && <p className="error-line">{threadError}</p>}
                {threadLoading && threadItems.length === 0 && <p className="empty-line">正在加载消息。</p>}
                {filteredThreadItems.map((item) => (
                  <article className="wechat-bubble-row" key={item.message_id}>
                    <Avatar name={displayName(item)} small />
                    <div className="wechat-message">
                      <div className="wechat-message-meta">
                        <strong>{item.sender}</strong>
                        <span>{formatTime(item.message_time)}</span>
                      </div>
                      <p>{item.raw_content}</p>
                    </div>
                  </article>
                ))}
                {filteredThreadItems.length === 0 && !threadLoading && <p className="empty-line">没有匹配的消息</p>}
              </div>
            </>
          ) : (
            <p className="empty-line">选择一个会话查看消息流</p>
          )}
        </section>
      </div>
    </section>
  );
}

function ConversationSkeleton() {
  return (
    <div className="wechat-conversation-skeleton" aria-hidden="true">
      <span className="wechat-skeleton-avatar" />
      <span className="wechat-skeleton-main">
        <span className="wechat-skeleton-line title" />
        <span className="wechat-skeleton-line preview" />
        <span className="wechat-skeleton-line meta" />
      </span>
    </div>
  );
}

function isMobileThreadLayout(): boolean {
  return window.matchMedia("(max-width: 760px)").matches;
}
