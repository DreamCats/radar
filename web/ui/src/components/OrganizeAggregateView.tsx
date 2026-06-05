import { useEffect, useRef, type ReactNode, type UIEvent } from "react";
import { AlertTriangle, CircleAlert, GitMerge, Sparkles, Tags } from "lucide-react";

import { formatTime } from "../lib/datetime";
import type { OrganizeAggregatePage, OrganizeAggregateTheme } from "../types";
import { OrganizeEvidenceItem } from "./OrganizeEvidenceItem";
import { PanelTitle } from "./PanelTitle";
import { scoreTone } from "./OrganizeClassificationView";

const SORT_RULE_TITLE =
  "排序规则：优先级分 = 行动分40% + 置信度20% + 证据数15% + 新鲜度15% + 最近消息10%。证据数按10条封顶，最近消息按当前时间窗口内越新越高。";

export function OrganizeAggregateView(props: {
  page: OrganizeAggregatePage;
  selected: OrganizeAggregateTheme | null;
  loading: boolean;
  evidenceError: string | null;
  loadingMore: boolean;
  hasMoreEvidence: boolean;
  onSelect: (themeIndex: number) => void;
  onEvidenceScroll: (event: UIEvent<HTMLDivElement>) => void;
}) {
  const evidenceListRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    evidenceListRef.current?.scrollTo({ top: 0 });
  }, [props.selected?.theme_index]);

  if (!props.loading && !props.page.result) {
    return (
      <div className="content-panel aggregate-empty">
        <PanelTitle title="聚类结果" meta="暂无产物" />
        <p>当前时间窗口没有可用聚合结果。先在作业页执行聚合 Refine，完成后回到这里查看主题。</p>
      </div>
    );
  }

  return (
    <div className="organize-workspace">
      <section className="content-panel organize-cluster-panel">
        <PanelTitle title="投资主题" meta={props.loading ? "加载中" : `${props.page.themes.length} 个主题`}>
          <button className="aggregate-sort-help" type="button" aria-label="查看聚类排序规则" title={SORT_RULE_TITLE}>
            <CircleAlert size={15} />
          </button>
        </PanelTitle>
        <div className="cluster-list aggregate-theme-list">
          {props.page.themes.map((theme) => (
            <ThemeRow
              key={`${props.page.result?.input_hash}-${theme.theme_index}`}
              selected={theme.theme_index === props.selected?.theme_index}
              theme={theme}
              onSelect={() => props.onSelect(theme.theme_index)}
            />
          ))}
          {!props.loading && props.page.themes.length === 0 && (
            <p className="empty-line">暂无匹配主题。可以清空搜索词或扩大时间窗口。</p>
          )}
        </div>
      </section>

      <section className="content-panel organize-evidence-panel aggregate-detail-panel">
        {props.selected ? (
          <>
            <PanelTitle title={props.selected.theme_name} meta={`${props.selected.evidence_message_ids.length} 条证据`}>
              <span className={`organize-score ${scoreTone(props.selected.confidence)}`}>
                {Math.round(props.selected.confidence * 100)}%
              </span>
            </PanelTitle>
            <div className="organize-tags">
              <span>
                <Sparkles size={13} />
                优先级 {Math.round(priorityScore(props.selected))}
              </span>
              <span>
                <Sparkles size={13} />
                行动分 {Math.round(props.selected.actionability_score)}
              </span>
              <span>新鲜度 {props.selected.novelty}</span>
              <span>已加载 {props.selected.evidence.length} 条</span>
              {props.page.result && <span>{formatTime(props.page.result.start_time)} - {formatTime(props.page.result.end_time)}</span>}
            </div>
            <div className="aggregate-detail-scroll" ref={evidenceListRef} onScroll={props.onEvidenceScroll}>
              <ThemeBrief theme={props.selected} />
              <div className="aggregate-evidence-title">证据消息</div>
              {props.selected.evidence.map((item) => (
                <OrganizeEvidenceItem item={item} key={item.message_id} />
              ))}
              <div className="evidence-footer">
                {props.evidenceError || (props.loadingMore ? "加载中" : props.hasMoreEvidence ? "还有更多" : "已全部加载")}
              </div>
            </div>
          </>
        ) : (
          <p className="empty-line">选择一个主题查看投资逻辑和证据消息。</p>
        )}
      </section>
    </div>
  );
}

function ThemeRow(props: { theme: OrganizeAggregateTheme; selected: boolean; onSelect: () => void }) {
  return (
    <button className={props.selected ? "cluster-row aggregate-theme-row active" : "cluster-row aggregate-theme-row"} type="button" onClick={props.onSelect}>
      <span className={`cluster-hotness ${scoreTone(props.theme.confidence)}`} />
      <span className="cluster-main">
        <strong>{props.theme.theme_name}</strong>
        <em>{props.theme.related_stocks.slice(0, 3).map((stock) => String(stock.name)).join(" / ") || "暂无标的"}</em>
        <span>{props.theme.summary || props.theme.investment_logic || "暂无摘要"}</span>
      </span>
      <span className="cluster-side">
        <strong>{Math.round(priorityScore(props.theme))}</strong>
      </span>
    </button>
  );
}

function priorityScore(theme: OrganizeAggregateTheme) {
  return Number.isFinite(theme.priority_score) ? theme.priority_score : theme.actionability_score;
}

function ThemeBrief(props: { theme: OrganizeAggregateTheme }) {
  return (
    <div className="aggregate-brief">
      <section>
        <h3>投资逻辑</h3>
        <p>{props.theme.investment_logic || props.theme.summary || "暂无投资逻辑。"}</p>
      </section>
      <section>
        <h3>催化</h3>
        <TagList icon={<Tags size={13} />} items={props.theme.catalysts} empty="暂无催化" />
      </section>
      <section>
        <h3>相关标的</h3>
        <div className="aggregate-stock-list">
          {props.theme.related_stocks.length === 0 && <span className="muted-chip">暂无标的</span>}
          {props.theme.related_stocks.map((stock) => (
            <article key={`${props.theme.theme_index}-${String(stock.name)}`}>
              <strong>{String(stock.name)}</strong>
              <p>{String(stock.reason || "暂无原因")}</p>
              <em>{Math.round(Number(stock.confidence || 0) * 100)}%</em>
            </article>
          ))}
        </div>
      </section>
      <section>
        <h3>风险</h3>
        <TagList icon={<AlertTriangle size={13} />} items={props.theme.risk_notes} empty="暂无风险备注" />
      </section>
      {props.theme.merge_from_candidate_ids.length > 0 && (
        <section>
          <h3>合并来源</h3>
          <TagList icon={<GitMerge size={13} />} items={props.theme.merge_from_candidate_ids} empty="暂无来源" />
        </section>
      )}
    </div>
  );
}

function TagList(props: { icon: ReactNode; items: string[]; empty: string }) {
  if (props.items.length === 0) {
    return <span className="muted-chip">{props.empty}</span>;
  }
  return (
    <div className="aggregate-chip-list">
      {props.items.map((item) => (
        <span key={item}>
          {props.icon}
          {item}
        </span>
      ))}
    </div>
  );
}
