import { useEffect, useRef, type UIEvent } from "react";
import { Tags } from "lucide-react";

import { formatTime } from "../lib/datetime";
import type { OrganizeClassificationCluster, OrganizeClassificationPage } from "../types";
import { OrganizeEvidenceItem } from "./OrganizeEvidenceItem";
import { PanelTitle } from "./PanelTitle";

export function OrganizeClassificationView(props: {
  page: OrganizeClassificationPage;
  selected: OrganizeClassificationCluster | null;
  loading: boolean;
  evidenceError: string | null;
  loadingMore: boolean;
  hasMoreEvidence: boolean;
  onSelect: (category: string) => void;
  onEvidenceScroll: (event: UIEvent<HTMLDivElement>) => void;
}) {
  const evidenceListRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    evidenceListRef.current?.scrollTo({ top: 0 });
  }, [props.selected?.category]);

  return (
    <div className="organize-workspace">
      <section className="content-panel organize-cluster-panel">
        <PanelTitle title="有效分类" meta={props.loading ? "加载中" : `${props.page.clusters.length} 个分类`} />
        <div className="cluster-list">
          {props.page.clusters.map((cluster) => (
            <ClusterRow
              cluster={cluster}
              key={cluster.category}
              selected={cluster.category === props.selected?.category}
              onSelect={() => props.onSelect(cluster.category)}
            />
          ))}
          {!props.loading && props.page.clusters.length === 0 && (
            <p className="empty-line">暂无分类结果。先在作业页执行消息分类。</p>
          )}
        </div>
      </section>

      <section className="content-panel organize-evidence-panel">
        {props.selected ? (
          <>
            <PanelTitle title={props.selected.label} meta={`${props.selected.count} 条消息`}>
              <span className={`organize-score ${scoreTone(props.selected.average_confidence)}`}>
                {Math.round(props.selected.average_confidence * 100)}%
              </span>
            </PanelTitle>
            <div className="organize-tags">
              <span>
                <Tags size={13} />
                {props.selected.category}
              </span>
              <span>最近 {formatTime(props.selected.latest_time)}</span>
              <span>平均置信 {Math.round(props.selected.average_confidence * 100)}%</span>
              <span>已加载 {props.selected.evidence.length} 条</span>
            </div>
            <div className="evidence-list" ref={evidenceListRef} onScroll={props.onEvidenceScroll}>
              {props.selected.evidence.map((item) => (
                <OrganizeEvidenceItem item={item} key={item.message_id} />
              ))}
              <div className="evidence-footer">
                {props.evidenceError || (props.loadingMore ? "加载中" : props.hasMoreEvidence ? "还有更多" : "已全部加载")}
              </div>
            </div>
          </>
        ) : (
          <p className="empty-line">选择一个分类查看证据消息。</p>
        )}
      </section>
    </div>
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

export function scoreTone(value: number): "high" | "medium" | "low" {
  if (value >= 0.75) {
    return "high";
  }
  if (value >= 0.65) {
    return "medium";
  }
  return "low";
}
