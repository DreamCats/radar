import { AnimatePresence, motion } from "motion/react";
import type { RefObject } from "react";

import type { ChatMessageItem } from "../types";
import { toolActivities } from "./chatHelpers";
import { MarkdownContent } from "./MarkdownContent";

type ChatMessageListProps = {
  endRef: RefObject<HTMLDivElement | null>;
  messages: ChatMessageItem[];
};

export function ChatMessageList(props: ChatMessageListProps) {
  return (
    <div className="chat-message-list">
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
  );
}
