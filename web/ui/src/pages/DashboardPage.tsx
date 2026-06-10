import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { fetchDashboardSummary } from "../api/radarApi";
import { ChatLauncher } from "../components/ChatLauncher";
import { PageLoadingState, PageRefreshProgress } from "../components/PageLoadingState";
import { formatTime } from "../lib/datetime";
import type { MessageOverview, RunItem } from "../types";

export function DashboardPage() {
  const [overview, setOverview] = useState<MessageOverview | null>(null);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const summary = await fetchDashboardSummary();
      setOverview(summary.overview);
      setRuns(summary.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const summary = overview?.summary;
  const filteredTotal = runs.reduce((sum, run) => sum + run.filtered_count, 0);
  const initialLoading = loading && !overview;

  return (
    <section className="dashboard-page">
      <div className="dashboard-actions">
        <p>
          {initialLoading
            ? "正在加载总览数据"
            : summary?.latest_message_time
              ? `最新消息 ${formatTime(summary.latest_message_time)}`
              : "暂无消息数据"}
        </p>
        <div>
          {loading && !initialLoading && <PageRefreshProgress label="正在刷新总览" />}
          {summary && (
            <ChatLauncher
              title="总览简报"
              subtitle={summary.latest_message_time ? `最新消息 ${formatTime(summary.latest_message_time)}` : "本地数据总览"}
              surface="总览"
              entityId={summary.latest_message_time ?? "dashboard"}
              buttonLabel="今日简报"
              buttonClassName="btn btn-sm chat-inline-action"
              context={[
                { label: "总消息", value: summary.total_count },
                { label: "个人群", value: `${summary.group_message_count} 条 / ${summary.group_count} 个群` },
                { label: "个人消息", value: `${summary.personal_message_count} 条 / ${summary.sender_count} 位发送人` },
                { label: "硬过滤", value: filteredTotal },
                { label: "最新消息", value: summary.latest_message_time ? formatTime(summary.latest_message_time) : null },
              ]}
              evidence={dashboardBriefEvidence(overview, filteredTotal)}
              suggestedQuestions={[
                "今天最值得看的三个机会是什么？请给出证据、风险和下一步验证。",
                "总览里哪些信号可能只是噪音，哪些值得进入策略页深挖？",
                "相比普通行情看板，今天本地消息流给了哪些新增信息？",
              ]}
            />
          )}
          <button className="btn btn-sm" type="button" onClick={() => void refresh()} disabled={loading} title="刷新总览">
            <RefreshCw size={15} />
            刷新
          </button>
        </div>
      </div>
      {initialLoading && <PageLoadingState label="正在聚合总览、榜单和消息信号" variant="dashboard" />}
      {!initialLoading && (
        <>
      <div className="statbar metric-grid">
        <Metric label="总消息" value={summary?.total_count ?? 0} detail="全库" />
        <Metric label="个人群" value={summary?.group_message_count ?? 0} detail={`${summary?.group_count ?? 0} 个群`} />
        <Metric label="个人消息" value={summary?.personal_message_count ?? 0} detail={`${summary?.sender_count ?? 0} 位发送人`} />
        <Metric label="硬过滤" value={filteredTotal} detail="最近 20 次作业" />
      </div>
      {error && <p className="error-line">{error}</p>}
        </>
      )}
    </section>
  );
}

function dashboardBriefEvidence(overview: MessageOverview | null, filteredTotal: number): string[] {
  return [
    overview?.summary.latest_message_time ? `最新消息：${formatTime(overview.summary.latest_message_time)}` : "",
    overview?.summary.total_count ? `全库消息：${overview.summary.total_count} 条` : "",
    filteredTotal ? `最近作业硬过滤：${filteredTotal} 条` : "",
  ].filter((line): line is string => Boolean(line));
}

function Metric(props: {
  label: string;
  value: number | string;
  detail: string;
}) {
  return (
    <article className="stat metric-card">
      <p className="k">{props.label}</p>
      <strong className="v">{props.value}</strong>
      <span className="sub">{props.detail}</span>
    </article>
  );
}
