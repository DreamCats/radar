import { useEffect, useState } from "react";
import { ArrowRight, Play, RefreshCw } from "lucide-react";

import { fetchMessages, fetchRuns, ingestWechat } from "../api/radarApi";
import { DateField, SelectField } from "../components/FormFields";
import { MessageRow } from "../components/MessageRow";
import { PanelTitle } from "../components/PanelTitle";
import { RunRow } from "../components/RunRow";
import { toIso } from "../lib/datetime";
import type { IngestResultItem, IngestSource, MessagePage, RunItem } from "../types";

export function DashboardPage({ onOpenMessages }: { onOpenMessages: () => void }) {
  const [messages, setMessages] = useState<MessagePage>({ items: [] });
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [messagePage, runItems] = await Promise.all([
        fetchMessages({ source: "group_message", limit: 12 }),
        fetchRuns(),
      ]);
      setMessages(messagePage);
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

  const latestRun = runs[0];
  const storedTotal = runs.reduce((sum, run) => sum + run.stored_count, 0);
  const filteredTotal = runs.reduce((sum, run) => sum + run.filtered_count, 0);

  return (
    <section className="dashboard-page">
      <div className="statbar metric-grid">
        <Metric label="当前页消息" value={messages.items.length} detail="个人群" />
        <Metric label="最近运行" value={latestRun?.status ?? "-"} detail={latestRun?.kind ?? "暂无"} tone={latestRun?.status} />
        <Metric label="近期入库" value={storedTotal} detail="最近 20 次" />
        <Metric label="硬过滤" value={filteredTotal} detail="最近 20 次" />
      </div>
      {error && <p className="error-line">{error}</p>}
      <div className="dashboard-grid">
        <section className="content-panel panel message-workbench">
          <PanelTitle title="消息流" meta={loading ? "加载中" : `${messages.items.length} 条`}>
            <button className="btn btn-sm" type="button" onClick={onOpenMessages}>
              <ArrowRight size={16} />
              查询
            </button>
          </PanelTitle>
          <div className="message-list compact">
            {messages.items.map((item) => (
              <MessageRow key={item.message_id} item={item} />
            ))}
            {!loading && messages.items.length === 0 && <p className="empty-line">暂无数据</p>}
          </div>
        </section>
        <aside className="right-rail">
          <RunSummary runs={runs.slice(0, 3)} onRefresh={() => void refresh()} />
          <QuickIngest />
          <ModulePreview />
        </aside>
      </div>
    </section>
  );
}

function Metric(props: {
  label: string;
  value: number | string;
  detail: string;
  tone?: RunItem["status"];
}) {
  return (
    <article className={`stat metric-card ${props.tone ?? ""}`}>
      <p className="k">{props.label}</p>
      <strong className="v">{props.value}</strong>
      <span className="sub">{props.detail}</span>
    </article>
  );
}

function RunSummary(props: { runs: RunItem[]; onRefresh: () => void }) {
  return (
    <section className="content-panel panel rail-panel">
      <PanelTitle title="运行" meta={`${props.runs.length} 条`}>
        <button className="btn btn-sm" type="button" onClick={props.onRefresh} title="刷新">
          <RefreshCw size={15} />
        </button>
      </PanelTitle>
      <div className="run-list compact">
        {props.runs.map((run) => (
          <RunRow key={run.run_id} run={run} />
        ))}
        {props.runs.length === 0 && <p className="empty-line">暂无运行记录</p>}
      </div>
    </section>
  );
}

function QuickIngest() {
  const [source, setSource] = useState<IngestSource>("group_message");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [result, setResult] = useState<IngestResultItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit() {
    setLoading(true);
    setError(null);
    try {
      setResult(
        await ingestWechat({
          source,
          start_time: toIso(start),
          end_time: toIso(end),
          force: false,
          chunk_hours: 1,
          concurrency: 4,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "拉取失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="content-panel panel rail-panel">
      <PanelTitle title="拉取" meta="窗口" />
      <div className="quick-ingest">
        <SelectField
          label="来源"
          value={source}
          onChange={(value) => setSource(value as IngestSource)}
          options={[
            ["personal_message", "个人消息"],
            ["group_message", "个人群"],
            ["all", "全部"],
          ]}
        />
        <DateField label="开始" value={start} onChange={setStart} />
        <DateField label="结束" value={end} onChange={setEnd} />
        <button className="btn btn-primary btn-sm" type="button" disabled={loading || !start || !end} onClick={submit}>
          <Play size={16} />
          开始
        </button>
      </div>
      {error && <p className="error-line">{error}</p>}
      {result.map((item) => (
        <p className="result-line compact" key={`${item.source_key}-${item.run_id}`}>
          {item.source} raw={item.raw_count} stored={item.stored_count}
        </p>
      ))}
    </section>
  );
}

function ModulePreview() {
  return (
    <section className="content-panel panel rail-panel module-preview">
      <PanelTitle title="模块" meta="预留" />
      <div className="module-row">
        <span className="module-dot hot" />
        信号雷达
      </div>
      <div className="module-row">
        <span className="module-dot market" />
        行情缓存
      </div>
      <div className="module-row">
        <span className="module-dot muted" />
        策略表
      </div>
    </section>
  );
}
