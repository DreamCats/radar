import type {
  IngestJobItem,
  IngestRequest,
  IngestResultItem,
  MessageConversationPage,
  MessageConversationQuery,
  MessageGroupItem,
  MessagePage,
  MessageQuery,
  RunItem,
} from "../types";

const apiBase = import.meta.env.VITE_RADAR_API_BASE ?? "";

export async function fetchMessages(query: MessageQuery): Promise<MessagePage> {
  return getJson(`/api/messages?${params(query)}`);
}

export async function fetchConversations(query: MessageConversationQuery): Promise<MessageConversationPage> {
  return getJson(`/api/conversations?${params(query)}`);
}

export async function fetchMessageGroups(query: { source?: string; keyword?: string; limit?: number } = {}): Promise<MessageGroupItem[]> {
  const data = await getJson<{ items: MessageGroupItem[] }>(`/api/message-groups?${params(query)}`);
  return data.items;
}

export async function fetchRuns(): Promise<RunItem[]> {
  const data = await getJson<{ items: RunItem[] }>("/api/runs?limit=20");
  return data.items;
}

export async function ingestWechat(request: IngestRequest): Promise<IngestResultItem[]> {
  const response = await fetch(`${apiBase}/api/ingest/wechat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const data = (await response.json()) as { items: IngestResultItem[] };
  return data.items;
}

export async function startIngestWechatJob(request: IngestRequest): Promise<IngestJobItem[]> {
  const response = await fetch(`${apiBase}/api/ingest/wechat/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const data = (await response.json()) as { items: IngestJobItem[] };
  return data.items;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`);
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as T;
}

function params(query: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  return search.toString();
}

async function errorText(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: string };
    return data.detail ?? `请求失败: ${response.status}`;
  } catch {
    return `请求失败: ${response.status}`;
  }
}
