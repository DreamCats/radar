import { Plus } from "lucide-react";

import type { ChatSessionItem } from "../types";

type ChatHistoryPanelProps = {
  activeSessionId: string | null;
  loading: boolean;
  sessions: ChatSessionItem[];
  onNewSession: () => void;
  onRefresh: () => void;
  onRestore: (sessionId: string) => void;
};

export function ChatHistoryPanel(props: ChatHistoryPanelProps) {
  return (
    <aside className="chat-history-panel" aria-label="历史对话">
      <div className="chat-history-head">
        <strong>历史对话</strong>
        <button className="chat-history-refresh" type="button" onClick={props.onRefresh}>
          刷新
        </button>
      </div>
      <button className="chat-history-new" type="button" onClick={props.onNewSession}>
        <Plus size={14} />
        新对话
      </button>
      <div className="chat-history-list">
        {props.loading && props.sessions.length === 0 ? <p className="empty-line">加载中</p> : null}
        {!props.loading && props.sessions.length === 0 ? <p className="empty-line">暂无历史</p> : null}
        {props.sessions.map((session) => (
          <button
            className={session.session_id === props.activeSessionId ? "chat-history-item active" : "chat-history-item"}
            key={session.session_id}
            type="button"
            onClick={() => props.onRestore(session.session_id)}
          >
            <strong>{session.title || "未命名对话"}</strong>
            <span>{session.preview || "暂无内容"}</span>
            <em>
              {formatSessionTime(session.updated_at)} · {session.message_count} 条
            </em>
          </button>
        ))}
      </div>
    </aside>
  );
}

function formatSessionTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
