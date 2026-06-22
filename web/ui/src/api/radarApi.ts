import type {
  ClassifyJobItem,
  ClassifyRequest,
  AnchorRequest,
  ChatContinueRequest,
  ChatMessageItem,
  ChatModelOptions,
  ChatSessionDetail,
  ChatSessionList,
  ChatStreamEvent,
  ChatToolMessageDetail,
  ChatTurnRequest,
  ChatTurnResponse,
  AuthStatus,
  DashboardSummary,
  DerivedJobItem,
  IngestJobItem,
  IngestRequest,
  IngestResultItem,
  IndustryChainDetail,
  IndustryChainList,
  LifecycleDigestJobRequest,
  LifecycleDigestPreview,
  MessageConversationPage,
  MessageConversationQuery,
  MessageGroupItem,
  MessageOverview,
  MessagePage,
  MessageQuery,
  OrganizeClassificationPage,
  OrganizeClassificationQuery,
  OrganizeEvidencePage,
  OrganizeEvidenceQuery,
  RecommendationBacktestRequest,
  RecommendationBacktestSummary,
  RunItem,
  StockEvidenceChainDashboard,
  StockEvidenceChainSnapshotList,
  StockEvidenceFinancials,
  StockEvidenceChainJobRequest,
  StockEvidenceStockChart,
  StockEvidenceStockChartQuery,
} from "../types";

const apiBase = import.meta.env.VITE_RADAR_API_BASE ?? "";
export const AUTH_EXPIRED_EVENT = "radar:auth-expired";

export async function fetchAuthStatus(): Promise<AuthStatus> {
  return getJson("/api/auth/status");
}

export async function login(username: string, password: string): Promise<AuthStatus> {
  const response = await apiFetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as AuthStatus;
}

export async function logout(): Promise<AuthStatus> {
  const response = await apiFetch("/api/auth/logout", { method: "POST" });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as AuthStatus;
}

export async function fetchMessages(query: MessageQuery): Promise<MessagePage> {
  return getJson(`/api/messages?${params(query)}`);
}

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  return getJson("/api/dashboard/summary");
}

export async function fetchConversations(query: MessageConversationQuery): Promise<MessageConversationPage> {
  return getJson(`/api/conversations?${params(query)}`);
}

export async function fetchMessageGroups(query: { source?: string; keyword?: string; limit?: number } = {}): Promise<MessageGroupItem[]> {
  const data = await getJson<{ items: MessageGroupItem[] }>(`/api/message-groups?${params(query)}`);
  return data.items;
}

export async function fetchMessageOverview(
  query: { days?: number; top_limit?: number } = {},
): Promise<MessageOverview> {
  return getJson(`/api/messages/overview?${params(query)}`);
}

export async function fetchIndustryChains(): Promise<IndustryChainList> {
  return getJson("/api/industry-chains");
}

export async function fetchIndustryChainDetail(chainId: string): Promise<IndustryChainDetail> {
  return getJson(`/api/industry-chains/${encodeURIComponent(chainId)}`);
}

export async function sendChatTurn(request: ChatTurnRequest): Promise<ChatTurnResponse> {
  const response = await apiFetch("/api/chat/turn", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as ChatTurnResponse;
}

export async function fetchChatSessions(limit = 50): Promise<ChatSessionList> {
  return getJson(`/api/chat/sessions?${params({ limit })}`);
}

export async function fetchChatSession(sessionId: string): Promise<ChatSessionDetail> {
  return getJson(`/api/chat/sessions/${encodeURIComponent(sessionId)}`);
}

export async function fetchChatToolMessage(sessionId: string, messageId: string): Promise<ChatToolMessageDetail> {
  return getJson(`/api/chat/sessions/${encodeURIComponent(sessionId)}/tool-messages/${encodeURIComponent(messageId)}`);
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  const response = await apiFetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
}

export async function fetchChatModelOptions(): Promise<ChatModelOptions> {
  return getJson("/api/chat/model-options");
}

export async function streamChatTurn(
  request: ChatTurnRequest,
  onEvent: (event: ChatStreamEvent) => void,
  options: { signal?: AbortSignal } = {},
): Promise<void> {
  const response = await apiFetch("/api/chat/turn/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: options.signal,
  });
  await readChatEventStream(response, onEvent);
}

export async function continueChatTurn(
  sessionId: string,
  request: ChatContinueRequest,
  onEvent: (event: ChatStreamEvent) => void,
  options: { signal?: AbortSignal } = {},
): Promise<void> {
  const response = await apiFetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/continue/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: options.signal,
  });
  await readChatEventStream(response, onEvent);
}

async function readChatEventStream(response: Response, onEvent: (event: ChatStreamEvent) => void): Promise<void> {
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  if (!response.body) {
    throw new Error("浏览器不支持流式响应");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const rawEvent of events) {
      const event = parseChatStreamEvent(rawEvent);
      if (event.type === "error") {
        onEvent(event);
        throw new Error(event.message);
      }
      onEvent(event);
    }
    if (done) {
      break;
    }
  }
  if (buffer.trim()) {
    const event = parseChatStreamEvent(buffer);
    if (event.type === "error") {
      onEvent(event);
      throw new Error(event.message);
    }
    onEvent(event);
  }
}

function parseChatStreamEvent(rawEvent: string): ChatStreamEvent {
  const eventName = rawEvent
    .split("\n")
    .find((line) => line.startsWith("event:"))
    ?.slice("event:".length)
    .trim();
  const dataText = rawEvent
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice("data:".length).trimStart())
    .join("\n");
  const data = dataText ? (JSON.parse(dataText) as Record<string, unknown>) : {};
  switch (eventName) {
    case "session":
      return { type: "session", session_id: String(data.session_id ?? "") };
    case "user_message":
    case "assistant_message":
    case "tool_message":
      return { type: eventName, message: data.message as ChatMessageItem };
    case "assistant_delta":
      return { type: "assistant_delta", content: String(data.content ?? "") };
    case "assistant_reasoning_delta":
      return { type: "assistant_reasoning_delta", content: String(data.content ?? "") };
    case "agent_event":
      return { type: "agent_event", event: (data.event as Record<string, unknown>) ?? {} };
    case "error":
      return { type: "error", message: String(data.message ?? "发送失败"), status_code: Number(data.status_code) || undefined };
    default:
      return { type: "agent_event", event: data };
  }
}

export async function fetchOrganizeClassifications(
  query: OrganizeClassificationQuery = {},
): Promise<OrganizeClassificationPage> {
  return getJson(`/api/organize/classifications?${params(query)}`);
}

export async function fetchOrganizeEvidence(query: OrganizeEvidenceQuery): Promise<OrganizeEvidencePage> {
  return getJson(`/api/organize/classifications/evidence?${params(query)}`);
}

export async function fetchRuns(query: { kind?: string; kinds?: string[]; status?: RunItem["status"]; limit?: number } = {}): Promise<RunItem[]> {
  const data = await getJson<{ items: RunItem[] }>(`/api/runs?${params({ limit: 20, ...query })}`);
  return data.items;
}

export async function cancelRun(runId: string): Promise<RunItem> {
  const response = await apiFetch(`/api/runs/${runId}/cancel`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as RunItem;
}

export async function fetchRecommendationBacktestSummary(query: {
  start_time: string;
  end_time: string;
  source?: string;
  group_by?: string;
  min_count?: number;
  limit?: number;
}): Promise<RecommendationBacktestSummary> {
  return getJson(`/api/recommendation/backtest/summary?${params(query)}`);
}

export async function fetchStockEvidenceChainLatest(query: { limit?: number; as_of_time?: string } = {}): Promise<StockEvidenceChainDashboard> {
  return getJson(`/api/strategy/evidence-chain/latest?${params(query)}`);
}

export async function fetchStockEvidenceChainSnapshots(query: { limit?: number } = {}): Promise<StockEvidenceChainSnapshotList> {
  return getJson(`/api/strategy/evidence-chain/snapshots?${params(query)}`);
}

export async function fetchStockEvidenceStockChart(tsCode: string, query: StockEvidenceStockChartQuery = {}): Promise<StockEvidenceStockChart> {
  return getJson(`/api/strategy/stocks/${encodeURIComponent(tsCode)}/chart?${params(query)}`);
}

export async function fetchStockEvidenceFinancials(tsCode: string, query: { years?: number } = {}): Promise<StockEvidenceFinancials> {
  return getJson(`/api/strategy/stocks/${encodeURIComponent(tsCode)}/financials?${params(query)}`);
}

export async function fetchLifecycleDigestPreview(query: { limit?: number; force?: boolean } = {}): Promise<LifecycleDigestPreview> {
  return getJson(`/api/strategy/lifecycle-digests/preview?${params(query)}`);
}

export async function ingestWechat(request: IngestRequest): Promise<IngestResultItem[]> {
  const response = await apiFetch("/api/ingest/wechat", {
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
  const response = await apiFetch("/api/ingest/wechat/jobs", {
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

export async function startClassifyMessagesJob(request: ClassifyRequest): Promise<ClassifyJobItem[]> {
  const response = await apiFetch("/api/classify/messages/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const data = (await response.json()) as { items: ClassifyJobItem[] };
  return data.items;
}

export async function startMarketAnchorUpdateJob(request: AnchorRequest): Promise<DerivedJobItem[]> {
  const response = await apiFetch("/api/market/anchors/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const data = (await response.json()) as { items: DerivedJobItem[] };
  return data.items;
}

export async function startRecommendationBacktestJob(request: RecommendationBacktestRequest): Promise<DerivedJobItem[]> {
  const response = await apiFetch("/api/recommendation/backtest/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const data = (await response.json()) as { items: DerivedJobItem[] };
  return data.items;
}

export async function startStockEvidenceChainJob(request: StockEvidenceChainJobRequest): Promise<DerivedJobItem[]> {
  const response = await apiFetch("/api/strategy/evidence-chain/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const data = (await response.json()) as { items: DerivedJobItem[] };
  return data.items;
}

export async function startLifecycleDigestJob(request: LifecycleDigestJobRequest): Promise<DerivedJobItem[]> {
  const response = await apiFetch("/api/strategy/lifecycle-digests/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const data = (await response.json()) as { items: DerivedJobItem[] };
  return data.items;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as T;
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(`${apiBase}${path}`, { ...init, credentials: "include" });
  if (response.status === 401 && !path.startsWith("/api/auth/")) {
    window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail: { path } }));
  }
  return response;
}

function params(query: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") {
      search.set(key, Array.isArray(value) ? value.join(",") : String(value));
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
