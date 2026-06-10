import { ArrowDown } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState, type RefObject, type UIEvent } from "react";

import type { ChatMessageItem } from "../types";
import { toolActivities, type ToolActivityItem } from "./chatHelpers";
import { MarkdownContent } from "./MarkdownContent";

type ChatMessageListProps = {
  endRef: RefObject<HTMLDivElement | null>;
  listRef: RefObject<HTMLDivElement | null>;
  messages: ChatMessageItem[];
  emptyState?: "overview";
  showJumpToBottom: boolean;
  onJumpToBottom: () => void;
  onScrollStateChange: (isNearBottom: boolean) => void;
};

export function ChatMessageList(props: ChatMessageListProps) {
  function handleScroll(event: UIEvent<HTMLDivElement>) {
    props.onScrollStateChange(isNearBottom(event.currentTarget));
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
            const status = typeof message.metadata.status === "string" ? message.metadata.status : "";
            const reasoning = typeof message.metadata.reasoning === "string" ? message.metadata.reasoning : "";
            const activities = toolActivities(message.metadata.tool_activities);
            return (
              <motion.article
                className={`chat-message chat-message-${message.role}`}
                key={message.message_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.16 }}
              >
                {message.role === "assistant" && status ? <div className="chat-agent-status">{status}</div> : null}
                {message.role === "assistant" && (reasoning || activities.length > 0) ? (
                  <details className="chat-reasoning" open={Boolean(message.metadata.streaming)}>
                    <summary>推理过程</summary>
                    {reasoning ? <MarkdownContent content={reasoning} /> : null}
                    {activities.length > 0 ? <ChatToolActivityList activities={activities} /> : null}
                  </details>
                ) : null}
                {message.content ? (
                  <>
                    <MarkdownContent content={message.content} />
                    {message.metadata.streaming ? <i className="chat-stream-cursor" aria-hidden="true" /> : null}
                  </>
                ) : (
                  <div className="chat-typing" aria-label="生成中">
                    <span>正在整理</span>
                    <em />
                    <em />
                    <em />
                  </div>
                )}
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
    </div>
  );
}

const TOOL_ACTIVITY_COLLAPSE_LIMIT = 6;

type ToolActivityDisplayItem = ToolActivityItem & {
  count: number;
};

function ChatToolActivityList({ activities }: { activities: ToolActivityItem[] }) {
  const [expanded, setExpanded] = useState(false);
  const groupedActivities = groupConsecutiveToolActivities(activities);
  const hasHiddenGroups = groupedActivities.length > TOOL_ACTIVITY_COLLAPSE_LIMIT;
  const hasGroupedItems = groupedActivities.some((activity) => activity.count > 1);
  const canExpand = hasHiddenGroups || hasGroupedItems;
  const displayActivities =
    expanded ? activities.map((activity) => ({ ...activity, count: 1 })) : groupedActivities.slice(0, TOOL_ACTIVITY_COLLAPSE_LIMIT);
  const hiddenCount = hasHiddenGroups
    ? groupedActivities.slice(TOOL_ACTIVITY_COLLAPSE_LIMIT).reduce((total, activity) => total + activity.count, 0)
    : 0;

  return (
    <div className="chat-tool-activity-block">
      <ul className="chat-tool-activity-list">
        {displayActivities.map((activity) => (
          <li className={`chat-tool-activity-${activity.status}`} key={activity.key}>
            {activity.label}
            {activity.count > 1 ? <span className="chat-tool-activity-count">x{activity.count}</span> : null}
          </li>
        ))}
      </ul>
      {canExpand ? (
        <button className="chat-tool-activity-toggle" type="button" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "收起工具调用" : hiddenCount > 0 ? `还有 ${hiddenCount} 个工具调用` : `展开 ${activities.length} 个工具调用`}
        </button>
      ) : null}
    </div>
  );
}

function groupConsecutiveToolActivities(activities: ToolActivityItem[]): ToolActivityDisplayItem[] {
  return activities.reduce<ToolActivityDisplayItem[]>((groups, activity) => {
    const last = groups[groups.length - 1];
    if (last && last.label === activity.label && last.status === activity.status) {
      last.count += 1;
      return groups;
    }
    groups.push({ ...activity, count: 1 });
    return groups;
  }, []);
}

function isNearBottom(element: HTMLDivElement): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight < 80;
}
