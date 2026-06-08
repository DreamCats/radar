import { Clock3, GitBranch, Radar, Users } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";

import { formatTime } from "../lib/datetime";
import type { SourceRadarSignal, SourceRadarSignalStatus, SourceRadarSnapshot } from "../types";
import { ChatLauncher } from "./ChatLauncher";
import { PanelTitle } from "./PanelTitle";

type SourceRadarFilter = SourceRadarSignalStatus | "all";

const STATUS_FILTERS: { key: SourceRadarFilter; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "source_seed", label: "源头初现" },
  { key: "spreading_watch", label: "扩散观察" },
  { key: "mapped", label: "个股绑定" },
  { key: "old_theme", label: "旧主题" },
];

export function SourceRadarPanel(props: {
  snapshot: SourceRadarSnapshot | null;
  selectedAsOfTime: string;
  onAsOfTimeChange: (value: string) => void;
}) {
  const { snapshot, selectedAsOfTime, onAsOfTimeChange } = props;
  const [activeFilter, setActiveFilter] = useState<SourceRadarFilter>("all");
  const items = snapshot?.items ?? [];
  const filteredItems = activeFilter === "all" ? items : items.filter((item) => item.status === activeFilter);
  const sourceSeedCount = items.filter((item) => item.status === "source_seed").length;
  const spreadingCount = items.filter((item) => item.status === "spreading_watch").length;
  const mappedCount = items.filter((item) => item.status === "mapped").length;
  const statusCounts = new Map<SourceRadarFilter, number>([
    ["all", items.length],
    ["source_seed", sourceSeedCount],
    ["spreading_watch", spreadingCount],
    ["mapped", mappedCount],
    ["old_theme", items.filter((item) => item.status === "old_theme").length],
  ]);

  return (
    <>
      <div className="statbar metric-grid">
        <Metric label="早期信号" value={sourceSeedCount} detail="新概念初现" />
        <Metric label="扩散观察" value={spreadingCount} detail="多人/多群接力" />
        <Metric label="个股绑定" value={mappedCount} detail="已映射相关股票" />
        <Metric label="快照条数" value={snapshot?.item_count ?? 0} detail="最新 Top 信号" />
      </div>
      <section className="panel source-radar-panel">
        <PanelTitle
          title="源头雷达"
          meta={snapshot?.as_of_time ? `最新快照 ${formatTime(snapshot.as_of_time)} · 早期概念雷达` : "等待源头雷达快照"}
        />
        <div className="source-radar-toolbar">
          <label>
            <span>快照时间</span>
            <select value={selectedAsOfTime} onChange={(event) => onAsOfTimeChange(event.target.value)}>
              <option value="">最新快照</option>
              {(snapshot?.available_as_of_times ?? []).map((time) => (
                <option value={time} key={time}>
                  {formatTime(time)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="source-radar-tabs" role="tablist" aria-label="源头雷达榜单">
          {STATUS_FILTERS.map((filter) => (
            <button
              className={activeFilter === filter.key ? "active" : ""}
              type="button"
              role="tab"
              aria-selected={activeFilter === filter.key}
              onClick={() => setActiveFilter(filter.key)}
              key={filter.key}
            >
              <span>{filter.label}</span>
              <strong>{statusCounts.get(filter.key) ?? 0}</strong>
            </button>
          ))}
        </div>
        <div className="source-radar-list">
          {filteredItems.length ? (
            filteredItems.map((item) => <SourceRadarCard item={item} key={item.snapshot_id} />)
          ) : (
            <p className="empty-line">{items.length ? "当前榜单暂无信号。" : "暂无源头雷达快照。先在作业页运行“源头雷达快照”。"}</p>
          )}
        </div>
      </section>
    </>
  );
}

function SourceRadarCard({ item }: { item: SourceRadarSignal }) {
  return (
    <article className="source-radar-card">
      <div className="source-radar-head">
        <div>
          <span className={`source-radar-status source-radar-status-${item.status}`}>{statusText(item.status)}</span>
          <h2>{signalTitle(item)}</h2>
        </div>
        <div className="strategy-score">
          <strong>{item.score.toFixed(0)}</strong>
          <span>信号分</span>
        </div>
      </div>
      <p className="strategy-reason">{item.ask_question || item.first_snippet}</p>
      <div className="strategy-signal-grid">
        <Signal label="首现" value={formatTime(item.first_seen_time).slice(5, 16)} icon={<Clock3 size={15} />} />
        <Signal label="扩散" value={`${item.asof_senders}人/${item.asof_groups}群`} icon={<Users size={15} />} />
        <Signal label="新鲜度" value={item.novelty_strength.toFixed(2)} icon={<Radar size={15} />} />
        <Signal label="接力" value={`${item.followup_senders}人/${item.followup_groups}群`} icon={<GitBranch size={15} />} />
      </div>
      <div className="strategy-tag-row">
        {[item.modifier_span, item.anchor_span, item.novel_span].filter(Boolean).map((term) => (
          <span className="strategy-chip positive" key={term}>
            {term}
          </span>
        ))}
        {item.mapped_stocks.slice(0, 6).map((stock) => (
          <span className="strategy-chip" key={stock}>
            {stock}
          </span>
        ))}
      </div>
      <div className="source-radar-meta">
        <span>首提 {item.first_sender || "-"}</span>
        <span>{item.first_group_name || "个人消息"}</span>
        <span>历史精确 {item.prior_exact_mentions} 次</span>
        <span>组合历史 {item.prior_combo_mentions} 次</span>
      </div>
      {item.evidence.length > 0 && (
        <ul className="source-radar-evidence">
          {item.evidence.slice(0, 4).map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      )}
      <div className="chat-card-action-row">
        <ChatLauncher
          title={signalTitle(item)}
          subtitle={item.ask_question || item.first_snippet}
          surface="源头雷达"
          entityId={item.signal_id}
          buttonLabel="问这个信号"
          buttonClassName="btn btn-sm chat-inline-action"
          context={[
            { label: "状态", value: statusText(item.status) },
            { label: "信号分", value: item.score.toFixed(0) },
            { label: "首现", value: formatTime(item.first_seen_time) },
            { label: "首提", value: item.first_sender || "-" },
            { label: "来源", value: item.first_group_name || "个人消息" },
            { label: "扩散", value: `${item.asof_senders}人/${item.asof_groups}群` },
            { label: "接力", value: `${item.followup_senders}人/${item.followup_groups}群` },
            { label: "映射股票", value: item.mapped_stocks.slice(0, 6).join(" / ") || "-" },
          ]}
          evidence={[item.first_snippet, ...item.evidence].filter(Boolean)}
          suggestedQuestions={[
            "这个信号为什么值得看？请区分证据、数据和推断。",
            "帮我找这个信号的反证和风险点。",
            "如果继续跟踪，下一步应该验证哪些消息、来源和标的？",
          ]}
        />
      </div>
    </article>
  );
}

function Metric(props: { label: string; value: number | string; detail: string }) {
  return (
    <article className="stat metric-card">
      <p className="k">{props.label}</p>
      <strong className="v">{props.value}</strong>
      <span className="sub">{props.detail}</span>
    </article>
  );
}

function Signal(props: { label: string; value: string; icon: ReactNode }) {
  return (
    <div className="strategy-signal">
      <span>
        {props.icon}
        {props.label}
      </span>
      <strong>{props.value}</strong>
    </div>
  );
}

function signalTitle(item: SourceRadarSignal): string {
  const relation = [item.modifier_span, item.anchor_span].filter(Boolean).join("");
  return relation || item.novel_span || item.anchor_span || item.signal_id;
}

function statusText(status: SourceRadarSignalStatus): string {
  if (status === "spreading_watch") {
    return "扩散观察";
  }
  if (status === "mapped") {
    return "个股绑定";
  }
  if (status === "old_theme") {
    return "旧主题";
  }
  return "源头初现";
}
