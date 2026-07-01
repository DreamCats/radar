import { useEffect, useMemo, useState } from "react";
import { Bot, RefreshCw } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { createPortal } from "react-dom";

import { fetchChatRuns } from "../api/radarApi";
import { ChatWorkspace } from "../components/ChatWorkspace";
import { useChatController } from "../components/useChatController";
import { formatTime } from "../lib/datetime";
import { useEscapeToClose } from "../lib/useEscapeToClose";
import type { ChatRunItem } from "../types";

type TaskListItem = {
  id: string;
  title: string;
  subtitle: string;
  status: string;
  updatedAt: string;
  createdAt: string;
  chatRun: ChatRunItem;
};

const TASK_LIMIT = 80;

export function TasksPage() {
  const [chatRuns, setChatRuns] = useState<ChatRunItem[]>([]);
  const [selectedChatRun, setSelectedChatRun] = useState<ChatRunItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tasks = useMemo(() => buildTaskItems(chatRuns), [chatRuns]);
  const runningCount = tasks.filter((task) => isRunningStatus(task)).length;

  useEffect(() => {
    void refresh();
  }, []);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setChatRuns(await fetchChatRuns(TASK_LIMIT));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载任务失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="tasks-page">
      <div className="tasks-header">
        <div className="panel-title">
          <div className="panel-title-heading">
            <h2>AI 任务</h2>
            <p>{loading ? "同步中" : `${tasks.length} 条 · ${runningCount} 运行中`}</p>
          </div>
        </div>
        <button className="btn btn-sm" type="button" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw size={14} />
          {loading ? "刷新中" : "刷新"}
        </button>
      </div>

      {error && <p className="error-line">{error}</p>}

      <div className="content-panel tasks-list-panel">
        <div className="tasks-list">
          {tasks.map((task) => (
            <TaskRow key={task.id} task={task} onOpenChat={setSelectedChatRun} />
          ))}
          {tasks.length === 0 && <p className="empty-line">{loading ? "正在加载 AI 任务。" : "暂无 AI 任务。"}</p>}
        </div>
      </div>

      {selectedChatRun ? <TaskChatDrawer key={selectedChatRun.run_id} run={selectedChatRun} onClose={() => setSelectedChatRun(null)} /> : null}
    </section>
  );
}

function TaskRow(props: { task: TaskListItem; onOpenChat: (run: ChatRunItem) => void }) {
  const statusClassName = `tasks-status ${statusTone(props.task.status)}`;
  const rowClassName = props.task.status === "running" ? "tasks-row is-running" : "tasks-row";
  return (
    <article className={rowClassName}>
      <div className="tasks-row-icon">
        <Bot size={17} />
      </div>
      <div className="tasks-row-main">
        <strong>{props.task.title}</strong>
        <span>{props.task.subtitle}</span>
      </div>
      <div className="tasks-row-actions">
        <span className={statusClassName}>{statusText(props.task.status)}</span>
        <span className="tasks-row-time">{formatTime(props.task.updatedAt)}</span>
        <button className="btn btn-sm" type="button" onClick={() => props.onOpenChat(props.task.chatRun)}>
          {props.task.status === "running" ? "继续" : "查看"}
        </button>
      </div>
    </article>
  );
}

function TaskChatDrawer(props: { run: ChatRunItem; onClose: () => void }) {
  const title = props.run.display_title || metadataString(props.run.metadata.title) || "AI 任务";
  const surface = metadataString(props.run.metadata.surface) || "task";
  const entityId = metadataString(props.run.metadata.entity_id) || props.run.session_id;
  const subtitle = `${props.run.display_subtitle || surface} · ${statusText(props.run.status)} · ${formatTime(props.run.updated_at)}`;
  const controller = useChatController(
    {
      title,
      subtitle,
      surface,
      entityId,
      context: [
        { label: "Run", value: compactId(props.run.run_id), copyValue: props.run.run_id, copyLabel: "复制 run id" },
        { label: "Session", value: compactId(props.run.session_id), copyValue: props.run.session_id, copyLabel: "复制 session id" },
        { label: "状态", value: statusText(props.run.status) },
        { label: "来源", value: surface },
      ],
      initialRunId: props.run.run_id,
      initialSessionId: props.run.session_id,
    },
    true,
  );
  useEscapeToClose(props.onClose, { ignoreWhenSelector: ".chat-reading-modal-shell" });

  const overlay = (
    <AnimatePresence>
      <motion.div
        className="chat-launcher-shell"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.16 }}
      >
        <motion.button
          className="chat-launcher-scrim"
          type="button"
          aria-label="关闭对话"
          onClick={props.onClose}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        />
        <motion.aside
          className="chat-launcher-panel"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
        >
          <ChatWorkspace
            controller={controller}
            title={title}
            subtitle={subtitle}
            surface={surface}
            entityId={entityId}
            onClose={props.onClose}
          />
        </motion.aside>
      </motion.div>
    </AnimatePresence>
  );

  return createPortal(overlay, document.body);
}

function buildTaskItems(chatRuns: ChatRunItem[]): TaskListItem[] {
  return chatRuns.map((run): TaskListItem => {
    const title = run.display_title || metadataString(run.metadata.title) || "AI 任务";
    const surface = metadataString(run.metadata.surface) || "chat";
    const entityId = run.display_subtitle || readableEntityId(metadataString(run.metadata.entity_id)) || run.session_id;
    return {
      id: run.run_id,
      title,
      subtitle: entityId.startsWith(surface) ? entityId : `${surface} · ${entityId}`,
      status: run.status,
      updatedAt: run.updated_at,
      createdAt: run.created_at,
      chatRun: run,
    };
  }).sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
}

function isRunningStatus(task: TaskListItem): boolean {
  return task.status === "running";
}

function metadataString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function readableEntityId(value: string): string {
  if (!value || /^[0-9a-f]{24,}$/i.test(value)) {
    return "";
  }
  return value;
}

function compactId(value: string): string {
  if (value.length <= 16) {
    return value;
  }
  return `${value.slice(0, 8)}...${value.slice(-6)}`;
}

function statusTone(status: string): string {
  if (status === "running") return "running";
  if (status === "completed" || status === "succeeded") return "success";
  if (status === "failed" || status === "partial_failed") return "failed";
  if (status === "cancelled" || status === "skipped") return "muted";
  return "muted";
}

function statusText(status: string): string {
  const labels: Record<string, string> = {
    running: "运行中",
    completed: "已完成",
    succeeded: "已完成",
    failed: "失败",
    partial_failed: "部分失败",
    cancelled: "已取消",
    skipped: "已跳过",
  };
  return labels[status] ?? status;
}
