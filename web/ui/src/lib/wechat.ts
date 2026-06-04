import type { MessageConversationItem, MessageItem, MessageSource, SourceKey } from "../types";

export type SenderStat = {
  sender: string;
  count: number;
};

const selfNames = new Set(["我", "自己", "本人", "me", "self", "maifeng", "maifeng@bytedance.com"]);

export function sourceKey(source: MessageSource): SourceKey {
  return source === "个人群" ? "group_message" : "personal_message";
}

export function displayName(item: MessageItem): string {
  const name = item.group_name?.trim() || item.sender.trim();
  return name || "未知";
}

export function isSelfMessage(item: MessageItem): boolean {
  return isSelfName(item.sender) || isSelfName(displayName(item));
}

export function isSelfConversation(item: MessageConversationItem): boolean {
  return isSelfName(item.title) || isSelfName(item.latest_sender);
}

export function buildSenderStats(items: MessageItem[]): SenderStat[] {
  const stats = new Map<string, number>();
  for (const item of items) {
    stats.set(item.sender, (stats.get(item.sender) ?? 0) + 1);
  }
  return Array.from(stats.entries())
    .map(([sender, count]) => ({ sender, count }))
    .sort((a, b) => b.count - a.count || a.sender.localeCompare(b.sender));
}

export function mergeMessages(current: MessageItem[], incoming: MessageItem[]): MessageItem[] {
  const messages = new Map<string, MessageItem>();
  for (const item of [...current, ...incoming]) {
    messages.set(item.message_id, item);
  }
  return Array.from(messages.values()).sort((a, b) => a.message_time.localeCompare(b.message_time));
}

export function matchesMessage(item: MessageItem, keyword: string): boolean {
  const normalized = normalizeKeyword(keyword);
  if (!normalized) {
    return true;
  }
  return normalizeKeyword(item.raw_content).includes(normalized) || normalizeKeyword(item.sender).includes(normalized);
}

export function avatarText(name: string): string {
  const compact = name.trim().replace(/\s+/g, "");
  return Array.from(compact || "未知").slice(0, 2).join("");
}

export function normalizeKeyword(value: string): string {
  return value.trim().toLocaleLowerCase();
}

function isSelfName(value: string): boolean {
  const name = normalizeKeyword(value).replace(/\s+/g, "");
  if (!name) {
    return false;
  }
  return selfNames.has(name) || name.includes("maifeng") || name.includes("自己发");
}
