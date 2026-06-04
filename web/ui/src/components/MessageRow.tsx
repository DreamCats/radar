import { formatTime } from "../lib/datetime";
import type { MessageItem } from "../types";

export function MessageRow({ item }: { item: MessageItem }) {
  return (
    <article className="message-row">
      <div className="row-meta">
        <span>{formatTime(item.message_time)}</span>
        <span>{item.source}</span>
        <span>{item.group_name || "-"}</span>
        <span>{item.sender}</span>
      </div>
      <p>{item.raw_content}</p>
    </article>
  );
}
