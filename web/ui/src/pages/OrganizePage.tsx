import { useEffect, useMemo, useState, type UIEvent } from "react";
import { CalendarDays, RefreshCw, Search } from "lucide-react";

import {
  fetchOrganizeAggregateEvidence,
  fetchOrganizeAggregates,
  fetchOrganizeClassifications,
  fetchOrganizeEvidence,
} from "../api/radarApi";
import { DateField, SelectField } from "../components/FormFields";
import { OrganizeAggregateView } from "../components/OrganizeAggregateView";
import { OrganizeClassificationView } from "../components/OrganizeClassificationView";
import { PanelTitle } from "../components/PanelTitle";
import { toIso } from "../lib/datetime";
import { buildPresetRange, rangeLabel, RANGE_PRESETS, toLocalIso, type LocalRange, type RangePreset } from "../lib/timeRange";
import type {
  OrganizeAggregatePage,
  OrganizeClassificationCluster,
  OrganizeClassificationPage,
  OrganizeEvidenceMessage,
  SourceKey,
} from "../types";

type SourceFilter = "all" | SourceKey;
type OrganizeMode = "classification" | "aggregate";
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

const emptyAggregatePage: OrganizeAggregatePage = {
  result: null,
  themes: [],
};

export function OrganizePage() {
  const [mode, setMode] = useState<OrganizeMode>("classification");
  const [source, setSource] = useState<SourceFilter>("all");
  const [keyword, setKeyword] = useState("");
  const [submittedKeyword, setSubmittedKeyword] = useState("");
  const [range, setRange] = useState<LocalRange>(() => buildPresetRange("today"));
  const [preset, setPreset] = useState<RangePreset>("today");
  const [page, setPage] = useState<OrganizeClassificationPage>(emptyPage);
  const [aggregatePage, setAggregatePage] = useState<OrganizeAggregatePage>(emptyAggregatePage);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedThemeIndex, setSelectedThemeIndex] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMoreCategory, setLoadingMoreCategory] = useState<string | null>(null);
  const [loadingMoreTheme, setLoadingMoreTheme] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [aggregateEvidenceError, setAggregateEvidenceError] = useState<string | null>(null);
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
      const query = {
        source: source === "all" ? undefined : source,
        keyword: submittedKeyword,
        start_time: startValue,
        end_time: endValue,
        evidence_limit: EVIDENCE_PAGE_SIZE,
      };
      if (mode === "aggregate") {
        const data = await fetchOrganizeAggregates(query);
        setAggregatePage(data);
        setAggregateEvidenceError(null);
        setSelectedThemeIndex((current) => {
          if (current !== null && data.themes.some((theme) => theme.theme_index === current)) {
            return current;
          }
          return data.themes[0]?.theme_index ?? null;
        });
        return;
      }

      const data = await fetchOrganizeClassifications({
        ...query,
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
  }, [mode, source, submittedKeyword, startValue, endValue]);

  const selected = useMemo(
    () => page.clusters.find((cluster) => cluster.category === selectedCategory) ?? page.clusters[0] ?? null,
    [page.clusters, selectedCategory],
  );
  const selectedTheme = useMemo(
    () => aggregatePage.themes.find((theme) => theme.theme_index === selectedThemeIndex) ?? aggregatePage.themes[0] ?? null,
    [aggregatePage.themes, selectedThemeIndex],
  );
  const recommendationCount = countByCategory(page.clusters, "recommendation");
  const researchCount = countByCategory(page.clusters, "research");
  const hasMoreEvidence = selected ? selected.evidence.length < selected.count : false;
  const loadingMore = Boolean(selected && loadingMoreCategory === selected.category);
  const hasMoreAggregateEvidence = selectedTheme ? selectedTheme.evidence.length < selectedTheme.evidence_message_ids.length : false;
  const loadingMoreAggregate = selectedTheme ? loadingMoreTheme === selectedTheme.theme_index : false;
  const metrics =
    mode === "aggregate" && aggregatePage.result
      ? [
          ["主题数", aggregatePage.result.theme_count, "可阅读"],
          ["候选簇", aggregatePage.result.candidate_count, "本地聚合"],
          ["证据消息", aggregatePage.result.evidence_message_count, "已覆盖"],
          ["失败批次", aggregatePage.result.failed_llm_batches, "LLM refine"],
        ]
      : [
          ["有效消息", page.summary.total_count, "高置信"],
          ["投资推荐", recommendationCount, "可行动"],
          ["研究观点", researchCount, "可阅读"],
          ["已收起", page.summary.hidden_count, "低置信 闲聊"],
        ];

  useEffect(() => {
    setEvidenceError(null);
  }, [selectedCategory]);

  useEffect(() => {
    setAggregateEvidenceError(null);
  }, [selectedThemeIndex]);

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

  async function loadMoreAggregateEvidence() {
    if (!selectedTheme || !aggregatePage.result || !hasMoreAggregateEvidence || loading || loadingMoreTheme !== null) {
      return;
    }
    const last = selectedTheme.evidence[selectedTheme.evidence.length - 1];
    if (!last) {
      return;
    }
    const themeIndex = selectedTheme.theme_index;
    setLoadingMoreTheme(themeIndex);
    setAggregateEvidenceError(null);
    try {
      const data = await fetchOrganizeAggregateEvidence({
        run_id: aggregatePage.result.run_id,
        theme_index: themeIndex,
        source: source === "all" ? undefined : source,
        keyword: submittedKeyword,
        cursor_time: last.message_time,
        cursor_id: last.message_id,
        limit: EVIDENCE_PAGE_SIZE,
      });
      setAggregatePage((current) => ({
        ...current,
        themes: current.themes.map((theme) => {
          if (theme.theme_index !== themeIndex) {
            return theme;
          }
          const currentLast = theme.evidence[theme.evidence.length - 1];
          if (currentLast?.message_id !== last.message_id) {
            return theme;
          }
          return { ...theme, evidence: mergeEvidence(theme.evidence, data.items) };
        }),
      }));
    } catch (err) {
      setAggregateEvidenceError(err instanceof Error ? err.message : "聚类证据加载失败");
    } finally {
      setLoadingMoreTheme(null);
    }
  }

  function handleEvidenceScroll(event: UIEvent<HTMLDivElement>) {
    const target = event.currentTarget;
    if (target.scrollHeight - target.scrollTop - target.clientHeight < 120) {
      void loadMoreEvidence();
    }
  }

  function handleAggregateEvidenceScroll(event: UIEvent<HTMLDivElement>) {
    const target = event.currentTarget;
    if (target.scrollHeight - target.scrollTop - target.clientHeight < 120) {
      void loadMoreAggregateEvidence();
    }
  }

  return (
    <section className="organize-page">
      <div className="organize-header">
        <PanelTitle title="整理" />
        <div className="organize-mode-tabs" aria-label="整理模式">
          <button className={mode === "classification" ? "active" : ""} type="button" onClick={() => setMode("classification")}>
            分类
          </button>
          <button className={mode === "aggregate" ? "active" : ""} type="button" onClick={() => setMode("aggregate")}>
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
            placeholder={mode === "aggregate" ? "搜主题、逻辑、标的、证据" : "搜分类理由、原文、发送人"}
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
        </div>
        <DateField label="开始" value={startValue} onChange={(value) => updateDateTime("start", value)} />
        <DateField label="结束" value={endValue} onChange={(value) => updateDateTime("end", value)} />
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
        {metrics.map(([label, value, detail]) => (
          <Metric detail={String(detail)} key={String(label)} label={String(label)} value={value} />
        ))}
      </div>

      {mode === "classification" ? (
        <OrganizeClassificationView
          evidenceError={evidenceError}
          hasMoreEvidence={hasMoreEvidence}
          loading={loading}
          loadingMore={loadingMore}
          page={page}
          selected={selected}
          onEvidenceScroll={handleEvidenceScroll}
          onSelect={setSelectedCategory}
        />
      ) : (
        <OrganizeAggregateView
          evidenceError={aggregateEvidenceError}
          hasMoreEvidence={hasMoreAggregateEvidence}
          loading={loading}
          loadingMore={loadingMoreAggregate}
          page={aggregatePage}
          selected={selectedTheme}
          onEvidenceScroll={handleAggregateEvidenceScroll}
          onSelect={setSelectedThemeIndex}
        />
      )}
    </section>
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
