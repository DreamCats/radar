import { Copy, FileText, Plus, Trash2 } from "lucide-react";
import type { MouseEvent } from "react";
import { useEffect, useState } from "react";

import type { ChatSessionItem } from "../types";

type SessionMenuState = {
  confirmDelete: boolean;
  session: ChatSessionItem;
  x: number;
  y: number;
};

type ChatHistoryPanelProps = {
  activeSessionId: string | null;
  loading: boolean;
  sessions: ChatSessionItem[];
  onCopySessionContent: (sessionId: string) => void;
  onCopySessionId: (sessionId: string) => void;
  onCopySessionTitle: (session: ChatSessionItem) => void;
  onDeleteSession: (sessionId: string) => void;
  onNewSession: () => void;
  onRefresh: () => void;
  onRestore: (sessionId: string) => void;
};

export function ChatHistoryPanel(props: ChatHistoryPanelProps) {
  const [menu, setMenu] = useState<SessionMenuState | null>(null);

  useEffect(() => {
    if (!menu) {
      return;
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenu(null);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [menu]);

  function openMenu(event: MouseEvent<HTMLButtonElement>, session: ChatSessionItem) {
    event.preventDefault();
    event.stopPropagation();
    setMenu({
      confirmDelete: false,
      session,
      x: Math.min(event.clientX, window.innerWidth - 220),
      y: Math.min(event.clientY, window.innerHeight - 210),
    });
  }

  function runMenuAction(action: () => void) {
    setMenu(null);
    action();
  }

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
            onContextMenu={(event) => openMenu(event, session)}
          >
            <strong>{session.title || "未命名对话"}</strong>
            <span>{session.preview || "暂无内容"}</span>
            <em>
              {formatSessionTime(session.updated_at)} · {session.message_count} 条
            </em>
          </button>
        ))}
      </div>
      {menu ? (
        <>
          <button className="chat-session-menu-scrim" type="button" aria-label="关闭 session 菜单" onClick={() => setMenu(null)} />
          <div className="chat-session-menu" style={{ left: menu.x, top: menu.y }}>
            {!menu.confirmDelete ? (
              <>
                <button type="button" onClick={() => runMenuAction(() => props.onCopySessionId(menu.session.session_id))}>
                  <Copy size={14} />
                  复制 session id
                </button>
                <button type="button" onClick={() => runMenuAction(() => props.onCopySessionTitle(menu.session))}>
                  <Copy size={14} />
                  复制名称
                </button>
                <button type="button" onClick={() => runMenuAction(() => props.onCopySessionContent(menu.session.session_id))}>
                  <FileText size={14} />
                  复制内容
                </button>
                <button className="danger" type="button" onClick={() => setMenu({ ...menu, confirmDelete: true })}>
                  <Trash2 size={14} />
                  删除 session
                </button>
              </>
            ) : (
              <div className="chat-session-menu-confirm">
                <span>确认删除？</span>
                <div>
                  <button type="button" onClick={() => setMenu({ ...menu, confirmDelete: false })}>
                    取消
                  </button>
                  <button className="danger" type="button" onClick={() => runMenuAction(() => props.onDeleteSession(menu.session.session_id))}>
                    删除
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      ) : null}
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
