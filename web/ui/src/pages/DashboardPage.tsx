import { useEffect, useState } from "react";
import { ArrowRight, RefreshCw } from "lucide-react";

import { fetchMessageOverview, fetchOrganizeClassifications, fetchRuns } from "../api/radarApi";
import { ClassificationDistributionChart } from "../components/ClassificationDistributionChart";
import { TopGroupsChart, TrendChart } from "../components/OverviewCharts";
import { formatTime } from "../lib/datetime";
import type { MessageOverview, OrganizeClassificationPage, RunItem } from "../types";

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

export function DashboardPage({ onOpenMessages }: { onOpenMessages: () => void }) {
  const [overview, setOverview] = useState<MessageOverview | null>(null);
  const [classificationPage, setClassificationPage] = useState<OrganizeClassificationPage>(emptyClassificationPage);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [overviewData, classificationData, runItems] = await Promise.all([
        fetchMessageOverview({ days: 14, top_limit: 8 }),
        fetchOrganizeClassifications({ evidence_limit: 0, low_confidence_threshold: 0.75 }),
        fetchRuns(),
      ]);
      setOverview(overviewData);
      setClassificationPage(classificationData);
      setRuns(runItems);
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

  return (
    <section className="dashboard-page">
      <div className="dashboard-actions">
        <p>{summary?.latest_message_time ? `最新消息 ${formatTime(summary.latest_message_time)}` : "暂无消息数据"}</p>
        <div>
          <button className="btn btn-sm" type="button" onClick={() => void refresh()} disabled={loading} title="刷新总览">
            <RefreshCw size={15} />
            刷新
          </button>
          <button className="btn btn-sm" type="button" onClick={onOpenMessages}>
            <ArrowRight size={16} />
            消息查询
          </button>
        </div>
      </div>
      <div className="statbar metric-grid">
        <Metric label="总消息" value={summary?.total_count ?? 0} detail="全库" />
        <Metric label="个人群" value={summary?.group_message_count ?? 0} detail={`${summary?.group_count ?? 0} 个群`} />
        <Metric label="个人消息" value={summary?.personal_message_count ?? 0} detail={`${summary?.sender_count ?? 0} 位发送人`} />
        <Metric label="硬过滤" value={filteredTotal} detail="最近 20 次作业" />
      </div>
      {error && <p className="error-line">{error}</p>}
      <div className="overview-chart-grid">
        <TrendChart overview={overview} />
        <TopGroupsChart data={overview?.top_groups ?? []} />
        <ClassificationDistributionChart
          clusters={classificationPage.clusters}
          totalCount={classificationPage.summary.total_count}
        />
      </div>
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
