import { ArrowDown } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import type { RefObject, UIEvent } from "react";

import type { ChatMessageItem } from "../types";
import { toolActivities } from "./chatHelpers";
import { MarkdownContent } from "./MarkdownContent";

type ChatMessageListProps = {
  endRef: RefObject<HTMLDivElement | null>;
  listRef: RefObject<HTMLDivElement | null>;
  messages: ChatMessageItem[];
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
                    {activities.length > 0 ? (
                      <ul className="chat-tool-activity-list">
                        {activities.map((activity) => (
                          <li className={`chat-tool-activity-${activity.status}`} key={activity.key}>
                            {activity.label}
                          </li>
                        ))}
                      </ul>
                    ) : null}
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

function isNearBottom(element: HTMLDivElement): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight < 80;
}
