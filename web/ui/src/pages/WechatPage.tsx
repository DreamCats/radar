import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";

import { fetchConversations, fetchMessageGroups, fetchMessages } from "../api/radarApi";
import { Avatar, WechatFilters } from "../components/WechatControls";
import { formatTime } from "../lib/datetime";
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

type ThreadScrollIntent =
  | { mode: "bottom" }
  | { mode: "preserve"; scrollTop: number; scrollHeight: number };

export function WechatPage() {
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
  const [loading, setLoading] = useState(false);
  const [threadLoading, setThreadLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threadError, setThreadError] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const threadScrollIntentRef = useRef<ThreadScrollIntent | null>(null);

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

  useEffect(() => {
    void loadConversations(defaultQuery);
  }, []);

  useEffect(() => {
    void fetchMessageGroups({ source: query.source, limit: 200 })
      .then((groups) => setGroupNames(groups.map((item) => item.group_name).filter((name) => !isSelfName(name))))
      .catch(() => setGroupNames([]));
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

  return (
    <section className="wechat-page">
      <WechatFilters
        groupNames={groupNames}
        loading={loading}
        query={query}
        onChange={setQuery}
        onSubmit={() => {
          setHistory([]);
          void loadConversations({ ...query, cursor_time: undefined, cursor_key: undefined });
        }}
      />

      <div className="wechat-workspace">
        <aside className="wechat-conversation-panel content-panel panel">
          <div className="wechat-panel-head">
            <div>
              <h2>微信</h2>
              <span>{conversations.length} 个会话</span>
            </div>
          </div>
          {error && <p className="error-line">{error}</p>}
          <div
            className={showConversationSkeleton ? "wechat-conversation-list is-loading" : "wechat-conversation-list"}
            aria-busy={showConversationSkeleton}
          >
            {showConversationSkeleton &&
              conversationSkeletonItems.map((item) => <ConversationSkeleton key={item} />)}
            {!showConversationSkeleton &&
              conversations.map((conversation) => (
                <button
                  className={
                    conversation.key === selectedConversation?.key
                      ? "wechat-conversation active"
                      : "wechat-conversation"
                  }
                  key={conversation.key}
                  type="button"
                  onClick={() => setSelectedKey(conversation.key)}
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
                </button>
              ))}
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
              <ThreadHeader
                conversation={selectedConversation}
                filteredCount={filteredThreadItems.length}
                matchedSenderStats={matchedSenderStats}
                selectedSender={selectedSender}
                senderQuery={senderQuery}
                threadKeyword={threadKeyword}
                totalCount={threadItems.length}
                onSenderChange={setSelectedSender}
                onSenderQueryChange={setSenderQuery}
                onThreadKeywordChange={setThreadKeyword}
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

function ThreadHeader(props: {
  conversation: MessageConversationItem;
  filteredCount: number;
  matchedSenderStats: { sender: string; count: number }[];
  selectedSender: string | null;
  senderQuery: string;
  threadKeyword: string;
  totalCount: number;
  onSenderChange: (sender: string | null) => void;
  onSenderQueryChange: (value: string) => void;
  onThreadKeywordChange: (value: string) => void;
}) {
  return (
    <div className="wechat-thread-head">
      <Avatar name={props.conversation.title} />
      <div className="wechat-thread-head-main">
        <div className="wechat-thread-title-row">
          <h2>{props.conversation.title}</h2>
          <span>
            {props.conversation.source} · {props.filteredCount}/{props.totalCount} 条
          </span>
        </div>
        <div className="wechat-thread-filters" aria-label="群内筛选">
          <div className="wechat-filter-input">
            <Search size={13} />
            <input
              value={props.senderQuery}
              placeholder="搜人"
              onChange={(event) => props.onSenderQueryChange(event.target.value)}
            />
          </div>
          <div className="wechat-filter-input wide">
            <Search size={13} />
            <input
              value={props.threadKeyword}
              placeholder="搜信息"
              onChange={(event) => props.onThreadKeywordChange(event.target.value)}
            />
          </div>
        </div>
        <div className="wechat-sender-chips" aria-label="发送人">
          <button
            className={props.selectedSender === null ? "wechat-sender-chip active" : "wechat-sender-chip"}
            type="button"
            onClick={() => props.onSenderChange(null)}
          >
            全部
            <span>{props.totalCount}</span>
          </button>
          {props.matchedSenderStats.map((item) => (
            <button
              className={props.selectedSender === item.sender ? "wechat-sender-chip active" : "wechat-sender-chip"}
              key={item.sender}
              type="button"
              onClick={() => props.onSenderChange(item.sender)}
              title={item.sender}
            >
              {item.sender}
              <span>{item.count}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
