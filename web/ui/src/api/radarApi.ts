import type {
  ClassifyJobItem,
  ClassifyRequest,
  AggregateRefineRequest,
  AggregateRefineResult,
  AnchorRequest,
  ChatTurnRequest,
  ChatTurnResponse,
  DashboardSummary,
  DerivedJobItem,
  IngestJobItem,
  IngestRequest,
  IngestResultItem,
  LeadSignalQuery,
  LeadSignalSummary,
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
  SourceRadarQuery,
  SourceRadarJobRequest,
  SourceRadarSnapshot,
  SourceRadarValidationQuery,
  SourceRadarValidationSummary,
  StrategyDashboard,
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

export async function fetchRuns(query: { kind?: string; status?: RunItem["status"]; limit?: number } = {}): Promise<RunItem[]> {
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

export async function fetchLeadSignals(query: LeadSignalQuery = {}): Promise<LeadSignalSummary> {
  return getJson(`/api/strategy/lead-signals?${params(query)}`);
}

export async function fetchSourceRadarSnapshot(query: SourceRadarQuery = {}): Promise<SourceRadarSnapshot> {
  return getJson(`/api/strategy/source-radar?${params(query)}`);
}

export async function fetchSourceRadarValidation(query: SourceRadarValidationQuery = {}): Promise<SourceRadarValidationSummary> {
  return getJson(`/api/strategy/source-radar/validation?${params(query)}`);
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

export async function startSourceRadarJob(request: SourceRadarJobRequest): Promise<DerivedJobItem[]> {
  const response = await fetch(`${apiBase}/api/source/radar/jobs`, {
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
