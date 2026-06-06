import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

import {
  fetchDashboardSummary,
} from "../api/radarApi";
import { ClassificationDistributionChart } from "../components/ClassificationDistributionChart";
import { LeaderboardAlphaChart } from "../components/LeaderboardAlphaChart";
import { AnchorHeatChart, ThemePriorityBubbleChart, TopGroupsChart, TrendChart } from "../components/OverviewCharts";
import { PageLoadingState, PageRefreshProgress } from "../components/PageLoadingState";
import { StrategyTopSummary } from "../components/StrategyTopSummary";
import { formatTime } from "../lib/datetime";
import type {
  MessageOverview,
  OrganizeAggregatePage,
  OrganizeClassificationPage,
  RecommendationBacktestSummary,
  RunItem,
  StrategyDashboard,
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

export function DashboardPage({ onOpenStrategy }: { onOpenStrategy: () => void }) {
  const [overview, setOverview] = useState<MessageOverview | null>(null);
  const [classificationPage, setClassificationPage] = useState<OrganizeClassificationPage>(emptyClassificationPage);
  const [aggregatePage, setAggregatePage] = useState<OrganizeAggregatePage>(emptyAggregatePage);
  const [backtestSummary, setBacktestSummary] = useState<RecommendationBacktestSummary>(emptyBacktestSummary);
  const [strategyData, setStrategyData] = useState<StrategyDashboard | null>(null);
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
      setStrategyData(summary.strategy);
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
          <button className="btn btn-sm" type="button" onClick={() => void refresh()} disabled={loading} title="刷新总览">
            <RefreshCw size={15} />
            刷新
          </button>
        </div>
      </div>
      {initialLoading && <PageLoadingState label="正在聚合总览、榜单和策略信号" variant="dashboard" />}
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
        <StrategyTopSummary data={strategyData} onOpenStrategy={onOpenStrategy} />
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
