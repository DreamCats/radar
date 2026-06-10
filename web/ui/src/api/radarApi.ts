import type {
  ClassifyJobItem,
  ClassifyRequest,
  AggregateRefineRequest,
  AggregateRefineResult,
  AnchorRequest,
  ChatMessageItem,
  ChatModelOptions,
  ChatSessionDetail,
  ChatSessionList,
  ChatStreamEvent,
  ChatTurnRequest,
  ChatTurnResponse,
  DashboardSummary,
  DerivedJobItem,
  IngestJobItem,
  IngestRequest,
  IngestResultItem,
  MessageConversationPage,
  MessageConversationQuery,
  MessageGroupItem,
  MessageOverview,
  MessagePage,
  MessageQuery,
  OrganizeAggregateEvidencePage,
  OrganizeAggregateEvidenceQuery,
  OrganizeAggregatePage,
  OrganizeAggregateQuery,
  OrganizeClassificationPage,
  OrganizeClassificationQuery,
  OrganizeEvidencePage,
  OrganizeEvidenceQuery,
  RecommendationBacktestRequest,
  RecommendationBacktestSummary,
  RunItem,
  StrategyDashboard,
  StockEvidenceChainJobRequest,
  StrategySnapshotBackfillJobRequest,
  StrategySnapshotSaveRequest,
  StrategySnapshotSaveResult,
  StrategyQuery,
  StrategyStockChart,
  StrategyStockChartQuery,
  StrategyValidationQuery,
  StrategyValidationSummary,
} from "../types";

const apiBase = import.meta.env.VITE_RADAR_API_BASE ?? "";

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
  query: { days?: number; top_limit?: number; anchor_limit?: number } = {},
): Promise<MessageOverview> {
  return getJson(`/api/messages/overview?${params(query)}`);
}

export async function sendChatTurn(request: ChatTurnRequest): Promise<ChatTurnResponse> {
  const response = await fetch(`${apiBase}/api/chat/turn`, {
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

export async function deleteChatSession(sessionId: string): Promise<void> {
  const response = await fetch(`${apiBase}/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
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
  const response = await fetch(`${apiBase}/api/chat/turn/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: options.signal,
  });
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

export async function fetchOrganizeAggregates(
  query: OrganizeAggregateQuery = {},
): Promise<OrganizeAggregatePage> {
  return getJson(`/api/organize/aggregates?${params(query)}`);
}

export async function fetchOrganizeAggregateEvidence(
  query: OrganizeAggregateEvidenceQuery,
): Promise<OrganizeAggregateEvidencePage> {
  return getJson(`/api/organize/aggregates/evidence?${params(query)}`);
}

export async function fetchRuns(query: { kind?: string; kinds?: string[]; status?: RunItem["status"]; limit?: number } = {}): Promise<RunItem[]> {
  const data = await getJson<{ items: RunItem[] }>(`/api/runs?${params({ limit: 20, ...query })}`);
  return data.items;
}

export async function cancelRun(runId: string): Promise<RunItem> {
  const response = await fetch(`${apiBase}/api/runs/${runId}/cancel`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as RunItem;
}

export async function fetchAggregateRefineResults(): Promise<AggregateRefineResult[]> {
  const data = await getJson<{ items: AggregateRefineResult[] }>("/api/aggregate/refine/results?limit=5");
  return data.items;
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

export async function fetchStrategyOpportunities(query: StrategyQuery = {}): Promise<StrategyDashboard> {
  return getJson(`/api/strategy/opportunities?${params(query)}`);
}

export async function fetchStrategyStockChart(tsCode: string, query: StrategyStockChartQuery = {}): Promise<StrategyStockChart> {
  return getJson(`/api/strategy/stocks/${encodeURIComponent(tsCode)}/chart?${params(query)}`);
}

export async function fetchStrategyValidation(query: StrategyValidationQuery = {}): Promise<StrategyValidationSummary> {
  return getJson(`/api/strategy/validation?${params(query)}`);
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

export async function startClassifyMessagesJob(request: ClassifyRequest): Promise<ClassifyJobItem[]> {
  const response = await fetch(`${apiBase}/api/classify/messages/jobs`, {
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

export async function startAnchorMessagesJob(request: AnchorRequest): Promise<DerivedJobItem[]> {
  const response = await fetch(`${apiBase}/api/anchor/messages/jobs`, {
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

export async function startAggregateRefineJob(request: AggregateRefineRequest): Promise<DerivedJobItem[]> {
  const response = await fetch(`${apiBase}/api/aggregate/refine/jobs`, {
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
  const response = await fetch(`${apiBase}/api/recommendation/backtest/jobs`, {
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

export async function saveStrategySnapshot(request: StrategySnapshotSaveRequest): Promise<StrategySnapshotSaveResult> {
  const response = await fetch(`${apiBase}/api/strategy/snapshots`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as StrategySnapshotSaveResult;
}

export async function startStrategyBackfillJob(request: StrategySnapshotBackfillJobRequest): Promise<DerivedJobItem[]> {
  const response = await fetch(`${apiBase}/api/strategy/snapshots/backfill/jobs`, {
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
  const response = await fetch(`${apiBase}/api/strategy/evidence-chain/jobs`, {
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
