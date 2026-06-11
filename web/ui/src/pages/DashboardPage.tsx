import { useEffect, useMemo, useState } from "react";
import { BriefcaseBusiness, Clock3, Database, RefreshCw, Sparkles } from "lucide-react";

import { fetchMessageOverview, fetchRuns } from "../api/radarApi";
import { OverviewChatWorkspace } from "../components/OverviewChatWorkspace";
import { PageLoadingState, PageRefreshProgress } from "../components/PageLoadingState";
import { useChatController } from "../components/useChatController";
import { formatTime } from "../lib/datetime";
import type { MessageOverview, RunItem } from "../types";

const SUGGESTED_QUESTIONS = [
  { label: "今日简报", prompt: "站在投资研究视角生成今日简报：只列 3 个证据最清楚的方向，给出原文证据、行情确认、风险和下一步验证。" },
  { label: "优先跟踪", prompt: "从本地消息流里按证据完整度和跟踪优先级，找出 3 条值得继续研究的线索，说明为什么现在值得看。" },
  { label: "查证据链", prompt: "围绕当前线索补一遍证据链：原文出处、关键催化、行情/资金验证、反证和缺口。" },
  { label: "资金/K线", prompt: "把当前提到的股票拉一遍资金流和 K 线，判断是发酵、兑现、分歧还是过热。" },
  { label: "策略线索", prompt: "从当前策略信号里筛出 5 只适合继续跟踪的股票，按证据强度排序，说明所属线索、为什么值得研究、需要验证什么、哪些风险条件下暂缓跟踪。" },
  { label: "风险排雷", prompt: "站在投资研究视角排雷：哪些是旧题材、利好兑现、资金不配合或过热风险，哪些可以暂时只复盘。" },
];

export function DashboardPage() {
  const [overview, setOverview] = useState<MessageOverview | null>(null);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contextRailOpen, setContextRailOpen] = useState(false);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [messageOverview, recentRuns] = await Promise.all([
        fetchMessageOverview({ days: 14, top_limit: 8 }),
        fetchRuns({ limit: 20 }),
      ]);
      setOverview(messageOverview);
      setRuns(recentRuns);
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
  const subtitle = summary?.latest_message_time ? `最新消息 ${formatTime(summary.latest_message_time)}` : "本地消息洞察";
  const chatContext = useMemo(
    () => [
      { label: "总消息", value: summary?.total_count ?? null },
      { label: "个人群", value: summary ? `${summary.group_message_count} 条 / ${summary.group_count} 个群` : null },
      { label: "个人消息", value: summary ? `${summary.personal_message_count} 条 / ${summary.sender_count} 位发送人` : null },
      { label: "硬过滤", value: filteredTotal || null },
      { label: "最新消息", value: summary?.latest_message_time ? formatTime(summary.latest_message_time) : null },
    ],
    [filteredTotal, summary],
  );
  const evidence = useMemo(() => dashboardBriefEvidence(overview, filteredTotal), [overview, filteredTotal]);
  const controller = useChatController(
    {
      title: "洞察 Agent",
      subtitle,
      surface: "洞察",
      entityId: summary?.latest_message_time ?? "dashboard",
      context: chatContext,
      evidence,
      suggestedQuestions: SUGGESTED_QUESTIONS.map((item) => item.prompt),
    },
    true,
  );

  return (
    <section className="dashboard-page dashboard-agent-page">
      {initialLoading ? <PageLoadingState label="正在读取本地消息概览" variant="dashboard" /> : null}
      <OverviewChatWorkspace
        controller={controller}
        title="洞察 Agent"
        subtitle={subtitle}
        surface="洞察"
        evidence={evidence}
        composerPlaceholder="输入股票、产业链、消息线索，或让 radar 生成今日简报"
        quickPrompts={SUGGESTED_QUESTIONS}
        intro={
          controller.messages.length === 0 ? (
            <OverviewIntro
              loading={loading}
              onRefresh={() => void refresh()}
            />
          ) : undefined
        }
        rightRail={contextRail(summary, runs, filteredTotal, loading, error)}
        rightRailOpen={contextRailOpen}
        onToggleRightRail={() => setContextRailOpen((value) => !value)}
      />
    </section>
  );
}

function OverviewIntro(props: {
  loading: boolean;
  onRefresh: () => void;
}) {
  return (
    <div className="overview-agent-intro">
      <div>
        <span className="overview-agent-kicker">
          <Sparkles size={14} />
          洞察上下文
        </span>
        <h1>从本地消息流开始</h1>
        <p>下面输入框负责发送问题；左下快捷入口可以快速填入常用问题。</p>
      </div>
      <div className="overview-agent-tools">
        {props.loading ? <PageRefreshProgress label="正在刷新洞察" /> : null}
        <button className="btn btn-sm" type="button" onClick={props.onRefresh} disabled={props.loading} title="刷新洞察">
          <RefreshCw size={15} />
          刷新
        </button>
      </div>
    </div>
  );
}

function contextRail(summary: MessageOverview["summary"] | undefined, runs: RunItem[], filteredTotal: number, loading: boolean, error: string | null) {
  const recentRuns = runs.slice(0, 3);
  return (
    <>
      <section className="overview-rail-card">
        <div className="overview-rail-title">
          <Database size={15} />
          <strong>可用数据</strong>
        </div>
        <dl className="overview-rail-metrics">
          <div>
            <dt>总消息</dt>
            <dd>{formatCompact(summary?.total_count)}</dd>
          </div>
          <div>
            <dt>个人群</dt>
            <dd>{formatCompact(summary?.group_message_count)}</dd>
          </div>
          <div>
            <dt>个人消息</dt>
            <dd>{formatCompact(summary?.personal_message_count)}</dd>
          </div>
          <div>
            <dt>硬过滤</dt>
            <dd>{formatCompact(filteredTotal)}</dd>
          </div>
        </dl>
      </section>
      <section className="overview-rail-card">
        <div className="overview-rail-title">
          <Clock3 size={15} />
          <strong>当前上下文</strong>
        </div>
        <p>{summary?.latest_message_time ? `最新消息 ${formatTime(summary.latest_message_time)}` : "暂无消息数据"}</p>
        <p>{loading ? "正在刷新本地洞察。" : "上下文栏只展示系统状态，不解析模型回答。"}</p>
        {error ? <p className="overview-rail-error">{error}</p> : null}
      </section>
      <section className="overview-rail-card">
        <div className="overview-rail-title">
          <BriefcaseBusiness size={15} />
          <strong>最近任务</strong>
        </div>
        {recentRuns.length > 0 ? (
          <ul className="overview-run-list">
            {recentRuns.map((run) => (
              <li key={run.run_id}>
                <span className={`status ${run.status}`}>{run.status}</span>
                <strong>{run.kind}</strong>
                <em>{run.finished_at ? formatTime(run.finished_at) : "进行中"}</em>
              </li>
            ))}
          </ul>
        ) : (
          <p>暂无最近作业。</p>
        )}
      </section>
    </>
  );
}

function dashboardBriefEvidence(overview: MessageOverview | null, filteredTotal: number): string[] {
  return [
    overview?.summary.latest_message_time ? `最新消息：${formatTime(overview.summary.latest_message_time)}` : "",
    overview?.summary.total_count ? `全库消息：${overview.summary.total_count} 条` : "",
    filteredTotal ? `最近作业硬过滤：${filteredTotal} 条` : "",
  ].filter((line): line is string => Boolean(line));
}

function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "--";
  }
  return new Intl.NumberFormat("zh-CN").format(value);
}
