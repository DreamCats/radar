import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import { fetchDashboardSummary } from "../api/radarApi";
import { ChatLauncher } from "../components/ChatLauncher";
import { ClassificationDistributionChart } from "../components/ClassificationDistributionChart";
import { LeaderboardAlphaChart } from "../components/LeaderboardAlphaChart";
import { AnchorHeatChart, ThemePriorityBubbleChart, TopGroupsChart, TrendChart } from "../components/OverviewCharts";
import { PageLoadingState, PageRefreshProgress } from "../components/PageLoadingState";
import { formatTime } from "../lib/datetime";
import type {
  MessageOverview,
  OrganizeAggregatePage,
  OrganizeClassificationPage,
  RecommendationBacktestSummary,
  RunItem,
} from "../types";

const emptyClassificationPage: OrganizeClassificationPage = {
  summary: {
    classified_count: 0,
    total_count: 0,
    cluster_count: 0,
    low_confidence_count: 0,
    noise_count: 0,
    hidden_count: 0,
    average_confidence: 0,
  },
  clusters: [],
};

const emptyAggregatePage: OrganizeAggregatePage = {
  result: null,
  themes: [],
};

const emptyBacktestSummary: RecommendationBacktestSummary = {
  start_time: "",
  end_time: "",
  group_by: "analyst_sector",
  windows: [1, 2, 3, 5],
  row_count: 0,
  rows: [],
};

export function DashboardPage() {
  const [overview, setOverview] = useState<MessageOverview | null>(null);
  const [classificationPage, setClassificationPage] = useState<OrganizeClassificationPage>(emptyClassificationPage);
  const [aggregatePage, setAggregatePage] = useState<OrganizeAggregatePage>(emptyAggregatePage);
  const [backtestSummary, setBacktestSummary] = useState<RecommendationBacktestSummary>(emptyBacktestSummary);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const summary = await fetchDashboardSummary();
      setOverview(summary.overview);
      setClassificationPage(summary.classifications);
      setAggregatePage(summary.aggregates);
      setBacktestSummary(summary.backtest);
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
                { label: "有效分类", value: classificationPage.summary.total_count },
                { label: "聚类主题", value: aggregatePage.themes.length },
                { label: "最新消息", value: summary.latest_message_time ? formatTime(summary.latest_message_time) : null },
              ]}
              evidence={dashboardBriefEvidence(overview, classificationPage, aggregatePage, backtestSummary)}
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
      <div className="overview-chart-grid">
        <LeaderboardAlphaChart rows={backtestSummary.rows} dimension={backtestSummary.group_by} />
        <ThemePriorityBubbleChart themes={aggregatePage.themes} />
        <AnchorHeatChart data={overview?.anchor_heat ?? []} />
        <TrendChart overview={overview} />
        <TopGroupsChart data={overview?.top_groups ?? []} />
        <ClassificationDistributionChart
          clusters={classificationPage.clusters}
          totalCount={classificationPage.summary.total_count}
        />
      </div>
        </>
      )}
    </section>
  );
}

function dashboardBriefEvidence(
  overview: MessageOverview | null,
  classificationPage: OrganizeClassificationPage,
  aggregatePage: OrganizeAggregatePage,
  backtestSummary: RecommendationBacktestSummary,
): string[] {
  return [
    overview?.top_groups.length
      ? `活跃群：${overview.top_groups.slice(0, 5).map((item) => `${item.group_name} ${item.count}`).join(" / ")}`
      : "",
    overview?.anchor_heat.length
      ? `热锚点：${overview.anchor_heat.slice(0, 5).map((item) => `${item.name} ${item.high_value_count}/${item.message_count}`).join(" / ")}`
      : "",
    classificationPage.clusters.length
      ? `有效分类：${classificationPage.clusters.slice(0, 5).map((item) => `${item.label} ${item.count}`).join(" / ")}`
      : "",
    aggregatePage.themes.length
      ? `主题：${aggregatePage.themes.slice(0, 5).map((item) => `${item.theme_name} ${Math.round(item.priority_score)}`).join(" / ")}`
      : "",
    backtestSummary.rows.length
      ? `回测榜：${backtestSummary.rows.slice(0, 5).map((item) => `${item.key} ${item.event_count}事件`).join(" / ")}`
      : "",
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
