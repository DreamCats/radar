import type { ChatMessageItem, ChatSessionDetail } from "../types";

export function formatChatTranscript(detail: ChatSessionDetail): string {
  const title = detail.session.title?.trim() || "未命名对话";
  const lines = [
    `# ${title}`,
    `session_id: ${detail.session.session_id}`,
    `created_at: ${detail.session.created_at}`,
    `updated_at: ${detail.session.updated_at}`,
    "",
  ];

  for (const message of detail.messages) {
    const content = message.content.trim();
    if (!content) {
      continue;
    }
    lines.push(`## ${roleLabel(message)} · ${message.created_at}`, content, "");
  }

  if (lines.length === 5) {
    lines.push("暂无内容");
  }
  return lines.join("\n").trimEnd();
}

function roleLabel(message: ChatMessageItem): string {
  if (message.role === "user") {
    return "用户";
  }
  if (message.role === "assistant") {
    return "助手";
  }
  return message.role;
}
