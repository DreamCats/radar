import { useEffect, useMemo, useState } from "react";
import { CalendarDays, RefreshCw, Search, Sparkles, Tags } from "lucide-react";

import { fetchOrganizeClassifications } from "../api/radarApi";
import { DateField, SelectField } from "../components/FormFields";
import { PanelTitle } from "../components/PanelTitle";
import { formatTime, toIso } from "../lib/datetime";
import { buildPresetRange, rangeLabel, RANGE_PRESETS, toLocalIso, type LocalRange, type RangePreset } from "../lib/timeRange";
import type { OrganizeClassificationCluster, OrganizeClassificationPage, OrganizeEvidenceMessage, SourceKey } from "../types";

type SourceFilter = "all" | SourceKey;

const emptyPage: OrganizeClassificationPage = {
  summary: {
    total_count: 0,
    cluster_count: 0,
    low_confidence_count: 0,
    average_confidence: 0,
  },
  clusters: [],
};

export function OrganizePage() {
  const [source, setSource] = useState<SourceFilter>("all");
  const [keyword, setKeyword] = useState("");
  const [submittedKeyword, setSubmittedKeyword] = useState("");
  const [range, setRange] = useState<LocalRange>(() => buildPresetRange("today"));
  const [preset, setPreset] = useState<RangePreset>("today");
  const [page, setPage] = useState<OrganizeClassificationPage>(emptyPage);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const startValue = toLocalIso(range.startDate, range.startTime);
  const endValue = toLocalIso(range.endDate, range.endTime);
  const canSubmit = Boolean(startValue && endValue) && startValue <= endValue;

  async function load() {
    if (!canSubmit) {
      setError("请选择有效的开始和结束时间。");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOrganizeClassifications({
        source: source === "all" ? undefined : source,
        keyword: submittedKeyword,
        start_time: startValue,
        end_time: endValue,
        evidence_limit: 12,
        low_confidence_threshold: 0.65,
      });
      setPage(data);
      setSelectedCategory((current) => {
        if (current && data.clusters.some((cluster) => cluster.category === current)) {
          return current;
        }
        return data.clusters[0]?.category ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "整理结果加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [source, submittedKeyword, startValue, endValue]);

  const selected = useMemo(
    () => page.clusters.find((cluster) => cluster.category === selectedCategory) ?? page.clusters[0] ?? null,
    [page.clusters, selectedCategory],
  );

  function applyPreset(value: RangePreset) {
    setPreset(value);
    setRange(buildPresetRange(value));
  }

  function updateDateTime(target: "start" | "end", value: string) {
    const nextValue = toIso(value);
    const [date, time = ""] = nextValue.split("T");
    const dateKey = target === "start" ? "startDate" : "endDate";
    const timeKey = target === "start" ? "startTime" : "endTime";
    setPreset("custom");
    setRange((current) => ({ ...current, [dateKey]: date ?? "", [timeKey]: time.slice(0, 5) }));
  }

  return (
    <section className="organize-page">
      <div className="organize-header">
        <PanelTitle title="整理" />
        <div className="organize-mode-tabs" aria-label="整理模式">
          <button className="active" type="button">
            分类
          </button>
          <button type="button" disabled>
            聚类
          </button>
        </div>
        <div className="organize-window">
          <CalendarDays size={15} />
          {rangeLabel(range)}
        </div>
      </div>

      <div className="range-presets organize-presets" aria-label="快捷时间窗口">
        {RANGE_PRESETS.map(([value, label]) => (
          <button
            className={preset === value ? "preset-button active" : "preset-button"}
            key={value}
            type="button"
            onClick={() => applyPreset(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <form
        className="organize-toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          setSubmittedKeyword(keyword.trim());
        }}
      >
        <div className="organize-search">
          <Search size={15} />
          <input
            aria-label="搜索整理结果"
            placeholder="搜分类理由、原文、发送人"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
        </div>
        <DateField
          label="开始"
          value={startValue}
          onChange={(value) => updateDateTime("start", value)}
        />
        <DateField
          label="结束"
          value={endValue}
          onChange={(value) => updateDateTime("end", value)}
        />
        <SelectField
          label="来源"
          value={source}
          onChange={(value) => setSource(value as SourceFilter)}
          options={[
            ["all", "全部来源"],
            ["group_message", "个人群"],
            ["personal_message", "个人消息"],
          ]}
        />
        <button className="btn btn-primary btn-sm organize-refresh" type="submit" disabled={loading || !canSubmit}>
          {loading ? <RefreshCw size={14} /> : <Search size={14} />}
          查询
        </button>
      </form>

      {error && <p className="error-line">{error}</p>}

      <div className="organize-metrics">
        <Metric label="分类簇" value={page.summary.cluster_count} detail="category" />
        <Metric label="覆盖消息" value={page.summary.total_count} detail="已分类" />
        <Metric label="平均置信" value={`${Math.round(page.summary.average_confidence * 100)}%`} detail="LLM 输出" />
        <Metric label="待复核" value={page.summary.low_confidence_count} detail="低置信" />
      </div>

      <div className="organize-workspace">
        <section className="content-panel organize-cluster-panel">
          <PanelTitle title="分类簇" meta={loading ? "加载中" : `${page.clusters.length} 个分类`} />
          <div className="cluster-list">
            {page.clusters.map((cluster) => (
              <ClusterRow
                cluster={cluster}
                key={cluster.category}
                selected={cluster.category === selected?.category}
                onSelect={() => setSelectedCategory(cluster.category)}
              />
            ))}
            {!loading && page.clusters.length === 0 && <p className="empty-line">暂无分类结果。先在作业页执行消息分类。</p>}
          </div>
        </section>

        <section className="content-panel organize-evidence-panel">
          {selected ? (
            <>
              <PanelTitle title={selected.label} meta={`${selected.count} 条消息 · 最近 ${formatTime(selected.latest_time)}`}>
                <span className={`organize-score ${scoreTone(selected.average_confidence)}`}>
                  {Math.round(selected.average_confidence * 100)}%
                </span>
              </PanelTitle>
              <div className="organize-tags">
                <span>
                  <Tags size={13} />
                  {selected.category}
                </span>
                <span>{selected.low_confidence_count} 条待复核</span>
                <span>{selected.evidence.length} 条证据</span>
              </div>
              <div className="evidence-list">
                {selected.evidence.map((item) => (
                  <EvidenceItem item={item} key={item.message_id} />
                ))}
              </div>
            </>
          ) : (
            <p className="empty-line">选择一个分类查看证据消息。</p>
          )}
        </section>

      </div>
    </section>
  );
}

function ClusterRow(props: { cluster: OrganizeClassificationCluster; selected: boolean; onSelect: () => void }) {
  const latest = props.cluster.evidence[0];
  return (
    <button className={props.selected ? "cluster-row active" : "cluster-row"} type="button" onClick={props.onSelect}>
      <span className={`cluster-hotness ${scoreTone(props.cluster.average_confidence)}`} />
      <span className="cluster-main">
        <strong>{props.cluster.label}</strong>
        <em>{props.cluster.category} · {props.cluster.low_confidence_count} 待复核</em>
        <span>{latest?.reason ?? "暂无分类理由"}</span>
      </span>
      <span className="cluster-side">
        <strong>{props.cluster.count}</strong>
        <em>{Math.round(props.cluster.average_confidence * 100)}%</em>
      </span>
    </button>
  );
}

function EvidenceItem(props: { item: OrganizeEvidenceMessage }) {
  return (
    <article className="evidence-item">
      <div className="evidence-avatar">{shortName(props.item.sender)}</div>
      <div className="evidence-body">
        <div className="evidence-meta">
          <strong>{props.item.sender}</strong>
          <span>{props.item.group_name || props.item.source}</span>
          <time>{formatTime(props.item.message_time)}</time>
        </div>
        <p>{props.item.raw_content}</p>
        <div className="evidence-reason">
          <Sparkles size={13} />
          {props.item.reason}
        </div>
      </div>
    </article>
  );
}

function Metric(props: { label: string; value: number | string; detail: string }) {
  return (
    <div className="organize-metric">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      <em>{props.detail}</em>
    </div>
  );
}

function scoreTone(value: number): "high" | "medium" | "low" {
  if (value >= 0.75) {
    return "high";
  }
  if (value >= 0.65) {
    return "medium";
  }
  return "low";
}

function shortName(name: string): string {
  const cleaned = name.trim();
  if (/^[a-z0-9]/i.test(cleaned)) {
    return cleaned.slice(0, 2).toUpperCase();
  }
  return cleaned.slice(0, 2);
}
