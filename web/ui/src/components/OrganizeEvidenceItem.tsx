import { Sparkles } from "lucide-react";

import { formatTime } from "../lib/datetime";
import type { OrganizeEvidenceMessage } from "../types";

export function OrganizeEvidenceItem(props: { item: OrganizeEvidenceMessage }) {
  return (
    <article className="evidence-item">
      <div className="evidence-avatar">{shortName(props.item.sender)}</div>
      <div className="evidence-body">
        <div className="evidence-meta">
          <span className="evidence-identity">
            <strong>{props.item.sender}</strong>
            <span>{props.item.group_name || props.item.source}</span>
          </span>
          <time>{formatTime(props.item.message_time)}</time>
        </div>
        <p>{props.item.raw_content}</p>
        {props.item.reason && (
          <div className="evidence-reason">
            <Sparkles size={13} />
            {props.item.reason}
          </div>
        )}
      </div>
    </article>
  );
}

function shortName(name: string): string {
  const cleaned = name.trim();
  if (/^[a-z0-9]/i.test(cleaned)) {
    return cleaned.slice(0, 2).toUpperCase();
  }
  return cleaned.slice(0, 2);
}
