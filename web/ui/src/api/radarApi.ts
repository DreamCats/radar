import type {
  AnalystBacktestRequest,
  AnalystBacktestEvidence,
  AnalystBacktestMessageEvidence,
  AnalystBacktestSummary,
  ChatContinueRequest,
  ChatActiveRunResponse,
  ChatMessageItem,
  ChatModelOptions,
  ChatRunItem,
  ChatRunListResponse,
  ChatRunResponse,
  ChatSessionDetail,
  ChatStreamEvent,
  ChatToolMessageDetail,
  ChatTurnRequest,
  ChatTurnResponse,
  AuthStatus,
  CatalystFeedPage,
  CatalystFeedQuery,
  CatalystValuationReportArchiveDetail,
  CatalystValuationReportArchiveItem,
  CatalystValuationReportJobRequest,
  CatalystValuationReportNotifyResponse,
  CatalystTermLibrary,
  DerivedJobItem,
  IngestJobItem,
  IngestRequest,
  IngestResultItem,
  IndustryChainDetail,
  IndustryChainList,
  MessageConversationPage,
  MessageConversationQuery,
  MessageGroupItem,
  MessagePage,
  MessageQuery,
  MarketStockRefreshRequest,
  RunItem,
  PremarketSignalQuery,
  PremarketConceptRank,
  PremarketSignalResult,
  ScheduleItem,
  ScheduleTickItem,
  ThsConceptRefreshRequest,
} from "../types";

const apiBase = import.meta.env.VITE_RADAR_API_BASE ?? "";
export const AUTH_EXPIRED_EVENT = "radar:auth-expired";
const AUTH_TOKEN_STORAGE_KEY = "radar.authToken";

export async function fetchAuthStatus(): Promise<AuthStatus> {
  return getJson("/api/auth/status");
}

export async function login(token: string): Promise<AuthStatus> {
  const response = await apiFetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const status = (await response.json()) as AuthStatus;
  writeAuthToken(token);
  return status;
}

export async function logout(): Promise<AuthStatus> {
  clearAuthToken();
  const response = await apiFetch("/api/auth/logout", { method: "POST" });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as AuthStatus;
}

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

export async function fetchCatalystTerms(): Promise<CatalystTermLibrary> {
  return getJson("/api/catalyst/terms");
}

export async function saveCatalystTerms(library: CatalystTermLibrary): Promise<CatalystTermLibrary> {
  const response = await apiFetch("/api/catalyst/terms", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(library),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as CatalystTermLibrary;
}

export async function resetCatalystTerms(): Promise<CatalystTermLibrary> {
  const response = await apiFetch("/api/catalyst/terms", { method: "DELETE" });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as CatalystTermLibrary;
}

export async function fetchCatalystFeed(query: CatalystFeedQuery): Promise<CatalystFeedPage> {
  return getJson(`/api/catalyst/feed?${params(query)}`);
}

export async function fetchPremarketSignal(query: PremarketSignalQuery): Promise<PremarketSignalResult> {
  const startedAt = performance.now();
  const path = `/api/premarket/signals?${params(query)}`;
  console.info("[premarket] fetch:start", query);
  const response = await apiFetch(path);
  console.info("[premarket] fetch:response", {
    status: response.status,
    ok: response.ok,
    elapsed_ms: Math.round(performance.now() - startedAt),
    content_type: response.headers.get("content-type"),
    content_length: response.headers.get("content-length"),
    content_encoding: response.headers.get("content-encoding"),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  console.info("[premarket] json:start", { elapsed_ms: Math.round(performance.now() - startedAt) });
  const data = (await response.json()) as PremarketSignalResult;
  console.info("[premarket] json:done", {
    elapsed_ms: Math.round(performance.now() - startedAt),
    keys: Object.keys(data),
    concepts: Array.isArray(data.concepts) ? data.concepts.length : null,
    top_concepts: Array.isArray(data.top_concepts) ? data.top_concepts.length : null,
    bottom_concepts: Array.isArray(data.bottom_concepts) ? data.bottom_concepts.length : null,
    velocity_concepts: Array.isArray(data.velocity_concepts) ? data.velocity_concepts.length : null,
    messages_scanned: data.summary?.messages_scanned ?? null,
    catalyst_items: data.summary?.catalyst_items ?? null,
  });
  return data;
}

export async function fetchPremarketConceptDetail(
  query: PremarketSignalQuery,
  conceptCode: string,
): Promise<PremarketConceptRank> {
  const startedAt = performance.now();
  const path = `/api/premarket/signals/concepts/${encodeURIComponent(conceptCode)}?${params(query)}`;
  console.info("[premarket] detail:start", { ...query, concept_code: conceptCode });
  const response = await apiFetch(path);
  console.info("[premarket] detail:response", {
    status: response.status,
    ok: response.ok,
    elapsed_ms: Math.round(performance.now() - startedAt),
    content_type: response.headers.get("content-type"),
    content_length: response.headers.get("content-length"),
    content_encoding: response.headers.get("content-encoding"),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const data = (await response.json()) as PremarketConceptRank;
  console.info("[premarket] detail:done", {
    elapsed_ms: Math.round(performance.now() - startedAt),
    concept_code: data.concept_code,
    stocks: Array.isArray(data.top_stocks) ? data.top_stocks.length : null,
    evidence: Array.isArray(data.evidence) ? data.evidence.length : null,
  });
  return data;
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

export async function fetchChatSession(sessionId: string): Promise<ChatSessionDetail> {
  return getJson(`/api/chat/sessions/${encodeURIComponent(sessionId)}`);
}

export async function fetchChatToolMessage(sessionId: string, messageId: string): Promise<ChatToolMessageDetail> {
  return getJson(`/api/chat/sessions/${encodeURIComponent(sessionId)}/tool-messages/${encodeURIComponent(messageId)}`);
}

export async function fetchChatModelOptions(): Promise<ChatModelOptions> {
  return getJson("/api/chat/model-options");
}

export async function createChatRun(request: ChatTurnRequest): Promise<ChatRunResponse> {
  const response = await apiFetch("/api/chat/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as ChatRunResponse;
}

export async function fetchChatRuns(limit = 50): Promise<ChatRunItem[]> {
  const data = await getJson<ChatRunListResponse>(`/api/chat/runs?${params({ limit })}`);
  return data.items;
}

export async function fetchChatRun(runId: string): Promise<ChatRunResponse> {
  return getJson(`/api/chat/runs/${encodeURIComponent(runId)}`);
}

export async function fetchActiveChatRun(query: {
  sessionId?: string | null;
  surface?: string | null;
  entityId?: string | null;
} = {}): Promise<ChatActiveRunResponse> {
  return getJson(
    `/api/chat/runs/active?${params({
      session_id: query.sessionId,
      surface: query.surface,
      entity_id: query.entityId,
    })}`,
  );
}

export async function cancelChatRun(runId: string): Promise<ChatRunResponse> {
  const response = await apiFetch(`/api/chat/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as ChatRunResponse;
}

export async function streamChatRun(
  runId: string,
  onEvent: (event: ChatStreamEvent) => void,
  options: { signal?: AbortSignal; afterSeq?: number } = {},
): Promise<void> {
  const response = await apiFetch(
    `/api/chat/runs/${encodeURIComponent(runId)}/stream?${params({ after_seq: options.afterSeq ?? 0 })}`,
    { signal: options.signal },
  );
  await readChatEventStream(response, onEvent);
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
  const sequenceNumber = Number(data.sequence_number);
  const streamMeta = {
    ...(Number.isFinite(sequenceNumber) && sequenceNumber > 0 ? { sequence_number: sequenceNumber } : {}),
    ...(typeof data.run_id === "string" ? { run_id: data.run_id } : {}),
  };
  switch (eventName) {
    case "ping":
      return { type: "ping", ...streamMeta };
    case "session":
      return { type: "session", session_id: String(data.session_id ?? ""), ...streamMeta };
    case "user_message":
    case "assistant_message":
    case "tool_message":
      return { type: eventName, message: data.message as ChatMessageItem, ...streamMeta };
    case "assistant_delta":
      return { type: "assistant_delta", content: String(data.content ?? ""), ...streamMeta };
    case "assistant_candidate_delta":
      return { type: "assistant_candidate_delta", content: String(data.content ?? ""), ...streamMeta };
    case "assistant_candidate_commit":
      return { type: "assistant_candidate_commit", content: String(data.content ?? ""), ...streamMeta };
    case "assistant_candidate_discard":
      return { type: "assistant_candidate_discard", content: String(data.content ?? ""), ...streamMeta };
    case "assistant_progress_delta":
      return { type: "assistant_progress_delta", content: String(data.content ?? ""), ...streamMeta };
    case "assistant_reasoning_delta":
      return { type: "assistant_reasoning_delta", content: String(data.content ?? ""), ...streamMeta };
    case "agent_event":
      return { type: "agent_event", event: (data.event as Record<string, unknown>) ?? {}, ...streamMeta };
    case "error":
      return { type: "error", message: String(data.message ?? "发送失败"), status_code: Number(data.status_code) || undefined, ...streamMeta };
    default:
      return { type: "agent_event", event: data, ...streamMeta };
  }
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

export async function fetchSchedules(): Promise<ScheduleItem[]> {
  const data = await getJson<{ items: ScheduleItem[] }>("/api/schedules");
  return data.items;
}

export async function enableSchedule(scheduleId: string): Promise<ScheduleItem[]> {
  const response = await apiFetch(`/api/schedules/${encodeURIComponent(scheduleId)}/enable`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const data = (await response.json()) as { items: ScheduleItem[] };
  return data.items;
}

export async function disableSchedule(scheduleId: string): Promise<ScheduleItem[]> {
  const response = await apiFetch(`/api/schedules/${encodeURIComponent(scheduleId)}/disable`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const data = (await response.json()) as { items: ScheduleItem[] };
  return data.items;
}

export async function runScheduleNow(scheduleId: string): Promise<ScheduleTickItem> {
  const response = await apiFetch(`/api/schedules/${encodeURIComponent(scheduleId)}/run-now`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  const data = (await response.json()) as { item: ScheduleTickItem };
  return data.item;
}

export async function fetchScheduleTicks(scheduleId: string, limit = 20): Promise<ScheduleTickItem[]> {
  const data = await getJson<{ items: ScheduleTickItem[] }>(
    `/api/schedules/${encodeURIComponent(scheduleId)}/ticks?${params({ limit })}`,
  );
  return data.items;
}

export async function fetchAnalystBacktestSummary(query: {
  start_time: string;
  end_time: string;
  source?: string;
  window?: number[];
  min_count?: number;
  limit?: number;
  include_broad_list?: boolean;
}): Promise<AnalystBacktestSummary> {
  return getJson(`/api/analyst/backtest/summary?${params(query)}`);
}

export async function fetchAnalystBacktestEvidence(query: {
  start_time: string;
  end_time: string;
  window?: number;
  analyst?: string;
  ts_code?: string;
  source?: string;
  limit?: number;
  include_broad_list?: boolean;
}): Promise<AnalystBacktestEvidence> {
  return getJson(`/api/analyst/backtest/evidence?${params(query)}`);
}

export async function fetchAnalystBacktestMessageEvidence(query: {
  start_time: string;
  end_time: string;
  window?: number;
  analyst?: string;
  source?: string;
  limit?: number;
  include_broad_list?: boolean;
}): Promise<AnalystBacktestMessageEvidence> {
  return getJson(`/api/analyst/backtest/message-evidence?${params(query)}`);
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

export async function startAnalystBacktestJob(request: AnalystBacktestRequest): Promise<DerivedJobItem[]> {
  const response = await apiFetch("/api/analyst/backtest/jobs", {
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

export async function startMarketStockRefreshJob(request: MarketStockRefreshRequest): Promise<DerivedJobItem[]> {
  const response = await apiFetch("/api/market/stocks/refresh/jobs", {
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

export async function startThsConceptRefreshJob(request: ThsConceptRefreshRequest): Promise<DerivedJobItem[]> {
  const response = await apiFetch("/api/market/ths-concepts/refresh/jobs", {
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

export async function startCatalystValuationReportJob(request: CatalystValuationReportJobRequest): Promise<DerivedJobItem[]> {
  const response = await apiFetch("/api/catalyst-valuation-report/jobs", {
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

export async function fetchCatalystValuationReports(query: {
  start_time?: string;
  end_time?: string;
  granularity_minutes?: number;
  limit?: number;
} = {}): Promise<CatalystValuationReportArchiveItem[]> {
  const data = await getJson<{ items: CatalystValuationReportArchiveItem[] }>(
    `/api/catalyst-valuation-reports?${params({ limit: 50, ...query })}`,
  );
  return data.items;
}

export async function fetchCatalystValuationReport(reportId: string): Promise<CatalystValuationReportArchiveDetail> {
  const data = await getJson<{ item: CatalystValuationReportArchiveDetail }>(
    `/api/catalyst-valuation-reports/${encodeURIComponent(reportId)}`,
  );
  return data.item;
}

export async function sendCatalystValuationReportBark(reportId: string): Promise<CatalystValuationReportNotifyResponse> {
  const response = await apiFetch(`/api/catalyst-valuation-reports/${encodeURIComponent(reportId)}/bark`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as CatalystValuationReportNotifyResponse;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return (await response.json()) as T;
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = readAuthToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${apiBase}${path}`, { ...init, headers, credentials: "omit" });
  if (response.status === 401 && !path.startsWith("/api/auth/")) {
    clearAuthToken();
    window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail: { path } }));
  }
  return response;
}

function readAuthToken(): string | null {
  try {
    return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeAuthToken(token: string): void {
  try {
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
  } catch {
    // localStorage may be unavailable in private or embedded contexts; current request still succeeds.
  }
}

function clearAuthToken(): void {
  try {
    window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  } catch {
    // Ignore storage failures; the next request will still be rejected by the server if no valid token is sent.
  }
}

function params(query: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
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
