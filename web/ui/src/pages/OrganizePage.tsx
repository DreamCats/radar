import { useEffect, useMemo, useRef, useState, type UIEvent } from "react";
import { CalendarDays, RefreshCw, Search, Sparkles, Tags } from "lucide-react";

import { fetchOrganizeClassifications, fetchOrganizeEvidence } from "../api/radarApi";
import { DateField, SelectField } from "../components/FormFields";
import { PanelTitle } from "../components/PanelTitle";
import { formatTime, toIso } from "../lib/datetime";
import { buildPresetRange, rangeLabel, RANGE_PRESETS, toLocalIso, type LocalRange, type RangePreset } from "../lib/timeRange";
import type { OrganizeClassificationCluster, OrganizeClassificationPage, OrganizeEvidenceMessage, SourceKey } from "../types";

type SourceFilter = "all" | SourceKey;
const EVIDENCE_PAGE_SIZE = 30;

const emptyPage: OrganizeClassificationPage = {
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

export function OrganizePage() {
  const [source, setSource] = useState<SourceFilter>("all");
  const [keyword, setKeyword] = useState("");
  const [submittedKeyword, setSubmittedKeyword] = useState("");
  const [range, setRange] = useState<LocalRange>(() => buildPresetRange("today"));
  const [preset, setPreset] = useState<RangePreset>("today");
  const [page, setPage] = useState<OrganizeClassificationPage>(emptyPage);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMoreCategory, setLoadingMoreCategory] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const evidenceListRef = useRef<HTMLDivElement | null>(null);
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
        evidence_limit: EVIDENCE_PAGE_SIZE,
        low_confidence_threshold: 0.75,
      });
      setPage(data);
      setEvidenceError(null);
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
  const recommendationCount = countByCategory(page.clusters, "recommendation");
  const researchCount = countByCategory(page.clusters, "research");
  const hasMoreEvidence = selected ? selected.evidence.length < selected.count : false;
  const loadingMore = Boolean(selected && loadingMoreCategory === selected.category);

  useEffect(() => {
    setEvidenceError(null);
    evidenceListRef.current?.scrollTo({ top: 0 });
  }, [selectedCategory]);

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

  async function loadMoreEvidence() {
    if (!selected || !hasMoreEvidence || loading || loadingMoreCategory) {
      return;
    }
    const last = selected.evidence[selected.evidence.length - 1];
    if (!last) {
      return;
    }
    const category = selected.category;
    setLoadingMoreCategory(category);
    setEvidenceError(null);
    try {
      const data = await fetchOrganizeEvidence({
        category,
        source: source === "all" ? undefined : source,
        keyword: submittedKeyword,
        start_time: startValue,
        end_time: endValue,
        cursor_time: last.message_time,
        cursor_id: last.message_id,
        limit: EVIDENCE_PAGE_SIZE,
        low_confidence_threshold: 0.75,
      });
      setPage((current) => ({
        ...current,
        clusters: current.clusters.map((cluster) => {
          if (cluster.category !== category) {
            return cluster;
          }
          const currentLast = cluster.evidence[cluster.evidence.length - 1];
          if (currentLast?.message_id !== last.message_id) {
            return cluster;
          }
          return { ...cluster, evidence: mergeEvidence(cluster.evidence, data.items) };
        }),
      }));
    } catch (err) {
      setEvidenceError(err instanceof Error ? err.message : "证据消息加载失败");
    } finally {
      setLoadingMoreCategory(null);
    }
  }

  function handleEvidenceScroll(event: UIEvent<HTMLDivElement>) {
    const target = event.currentTarget;
    if (target.scrollHeight - target.scrollTop - target.clientHeight < 120) {
      void loadMoreEvidence();
    }
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
        <Metric label="有效消息" value={page.summary.total_count} detail="高置信" />
        <Metric label="投资推荐" value={recommendationCount} detail="可行动" />
        <Metric label="研究观点" value={researchCount} detail="可阅读" />
        <Metric label="已收起" value={page.summary.hidden_count} detail="低置信 闲聊" />
      </div>

      <div className="organize-workspace">
        <section className="content-panel organize-cluster-panel">
          <PanelTitle title="有效分类" meta={loading ? "加载中" : `${page.clusters.length} 个分类`} />
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
                <span>平均置信 {Math.round(selected.average_confidence * 100)}%</span>
                <span>已加载 {selected.evidence.length} 条</span>
              </div>
              <div className="evidence-list" ref={evidenceListRef} onScroll={handleEvidenceScroll}>
                {selected.evidence.map((item) => (
                  <EvidenceItem item={item} key={item.message_id} />
                ))}
                <div className="evidence-footer">
                  {evidenceError || (loadingMore ? "加载中" : hasMoreEvidence ? "还有更多" : "已全部加载")}
                </div>
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
        <em>{props.cluster.category} · 高置信</em>
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

function countByCategory(clusters: OrganizeClassificationCluster[], category: string): number {
  return clusters.find((cluster) => cluster.category === category)?.count ?? 0;
}

function mergeEvidence(
  current: OrganizeEvidenceMessage[],
  next: OrganizeEvidenceMessage[],
): OrganizeEvidenceMessage[] {
  const seen = new Set(current.map((item) => item.message_id));
  const merged = [...current];
  for (const item of next) {
    if (!seen.has(item.message_id)) {
      seen.add(item.message_id);
      merged.push(item);
    }
  }
  return merged;
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
