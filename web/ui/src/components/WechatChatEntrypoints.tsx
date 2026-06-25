import { ChevronLeft, Search } from "lucide-react";

import { formatTime } from "../lib/datetime";
import type { MessageConversationItem, MessageConversationQuery } from "../types";
import { ChatLauncher } from "./ChatLauncher";
import { Avatar } from "./WechatControls";

const wechatListQuickPrompts = [
  {
    label: "扫会话",
    prompt:
      "先浏览最近微信会话列表，再按需要调用 radar_list_conversations / radar_search_messages，找出当前消息流里最值得继续研究的 3 条线索；每条都区分原文证据、推断和待验证项。",
  },
  {
    label: "找高频主题",
    prompt:
      "从微信消息里找最近反复出现的股票、行业和主题：说明哪些会话在提、原文证据是什么、是否需要补行情或公开资料验证。",
  },
  {
    label: "排噪音",
    prompt:
      "帮我过滤当前微信消息噪音：找出可能只是情绪转发、旧题材复读、利好兑现或证据不足的内容，并说明为什么暂缓跟踪。",
  },
];

const wechatThreadQuickPrompts = [
  {
    label: "总结群聊",
    prompt:
      "站在投资研究视角总结这个会话：最近主要在聊什么，涉及哪些股票、行业或主题；哪些是原文明确证据，哪些只是推断；最后列出 3 条值得继续验证的线索。",
  },
  {
    label: "投资线索",
    prompt:
      "从这个会话里筛出值得继续研究的股票或主题线索：按证据强度排序，说明催化、来源、需要补的行情或公开资料验证。",
  },
  {
    label: "反证风险",
    prompt:
      "帮我排除噪音：哪些内容只是旧题材、情绪转发、利好兑现或证据不足；分别给出反证和暂缓跟踪理由。",
  },
];

export function WechatListChatLauncher(props: {
  conversations: MessageConversationItem[];
  query: MessageConversationQuery;
  canNext: boolean;
}) {
  return (
    <ChatLauncher
      title="微信会话"
      subtitle={`${props.conversations.length} 个会话${props.canNext ? " · 可继续翻页" : ""}`}
      surface="微信会话"
      entityId="wechat:list"
      buttonLabel="AI"
      buttonClassName="btn btn-sm wechat-list-ai-action"
      context={[
        { label: "入口", value: "会话列表" },
        { label: "来源", value: props.query.source ?? "全部" },
        { label: "群", value: props.query.group_name ?? "全部" },
        { label: "关键词", value: props.query.keyword ?? "无" },
        { label: "当前页会话", value: props.conversations.length },
        { label: "可继续翻页", value: props.canNext ? "是" : "否" },
      ]}
      evidence={props.conversations.slice(0, 8).map(formatConversationEvidence)}
      quickPrompts={wechatListQuickPrompts}
    />
  );
}

export function WechatThreadHeader(props: {
  conversation: MessageConversationItem;
  filteredCount: number;
  matchedSenderStats: { sender: string; count: number }[];
  selectedSender: string | null;
  senderQuery: string;
  threadEvidence: string[];
  threadKeyword: string;
  totalCount: number;
  onSenderChange: (sender: string | null) => void;
  onSenderQueryChange: (value: string) => void;
  onThreadKeywordChange: (value: string) => void;
  onBack: () => void;
}) {
  return (
    <div className="wechat-thread-head">
      <button className="mini-button wechat-thread-back" type="button" onClick={props.onBack} aria-label="返回会话列表">
        <ChevronLeft size={15} />
      </button>
      <Avatar name={props.conversation.title} />
      <div className="wechat-thread-head-main">
        <div className="wechat-thread-title-row">
          <div className="wechat-thread-title-main">
            <h2>{props.conversation.title}</h2>
            <span>
              {props.conversation.source} · {props.filteredCount}/{props.totalCount} 条
            </span>
          </div>
          <ChatLauncher
            title={props.conversation.title}
            subtitle={`${props.conversation.source} · 当前可见 ${props.filteredCount}/${props.totalCount} 条`}
            surface="微信会话"
            entityId={props.conversation.key}
            buttonLabel="AI"
            buttonClassName="btn btn-primary btn-sm wechat-thread-ai-action"
            context={[
              { label: "入口", value: "单个会话" },
              { label: "会话", value: props.conversation.title },
              { label: "来源", value: props.conversation.source },
              { label: "最新发送人", value: props.conversation.latest_sender },
              { label: "最新时间", value: formatTime(props.conversation.latest_time) },
              { label: "当前筛选发送人", value: props.selectedSender ?? "全部" },
              { label: "当前关键词", value: props.threadKeyword || "无" },
              { label: "当前可见", value: `${props.filteredCount}/${props.totalCount} 条` },
            ]}
            evidence={props.threadEvidence}
            quickPrompts={wechatThreadQuickPrompts}
          />
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

function formatConversationEvidence(item: MessageConversationItem) {
  return `${item.source} · ${item.title} · ${formatTime(item.latest_time)} · ${item.latest_sender}：${item.latest_content}`;
}
