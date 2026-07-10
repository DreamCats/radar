import { ExternalLink, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { fetchValuationMeasurementOpportunities } from "../api/radarApi";
import { formatTime } from "../lib/datetime";
import { useEscapeToClose } from "../lib/useEscapeToClose";
import type { ValuationMeasurementOpportunity, ValuationMeasurementOpportunitySnapshot } from "../types";
import { PageLoadingState } from "./PageLoadingState";

type OpportunityFilter = "all" | "notify" | "conditional" | "storage";

type Props = {
  refreshKey: number;
  onOpenReport: (reportId: string) => void;
  onOpenSession: (snapshot: ValuationMeasurementOpportunitySnapshot) => void;
};

export function ValuationOpportunitiesView(props: Props) {
  const [items, setItems] = useState<ValuationMeasurementOpportunity[]>([]);
  const [filter, setFilter] = useState<OpportunityFilter>("all");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const summary = useMemo(() => summarizeOpportunities(items), [items]);
  const filteredItems = useMemo(() => filterOpportunities(items, filter), [items, filter]);
  const selected = useMemo(
    () => filteredItems.find((item) => item.stock_key === selectedKey) ?? filteredItems[0] ?? null,
    [filteredItems, selectedKey],
  );
  useEscapeToClose(() => setDetailOpen(false), { enabled: detailOpen });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetchValuationMeasurementOpportunities({ limit: 120, history_limit: 5 })
      .then((next) => {
        if (cancelled) {
          return;
        }
        setItems(next);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "测算结果加载失败");
          setItems([]);
          setSelectedKey(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [props.refreshKey]);

  useEffect(() => {
    setSelectedKey((current) =>
      current && filteredItems.some((item) => item.stock_key === current) ? current : (filteredItems[0]?.stock_key ?? null),
    );
    if (filteredItems.length === 0) {
      setDetailOpen(false);
    }
  }, [filteredItems]);

  if (loading && items.length === 0) {
    return <PageLoadingState label="读取测算结果" variant="strategy" />;
  }

  return (
    <div className={loading ? "valuation-opportunities-view is-refreshing" : "valuation-opportunities-view"}>
      {error && <p className="valuation-error">{error}</p>}
      <div className="valuation-opportunity-summary">
        <OpportunityMetric
          active={filter === "notify"}
          value={summary.notify}
          label="可通知"
          tone="notify"
          onClick={() => setFilter((current) => (current === "notify" ? "all" : "notify"))}
        />
        <OpportunityMetric
          active={filter === "conditional"}
          value={summary.conditional}
          label="条件触发"
          tone="conditional"
          onClick={() => setFilter((current) => (current === "conditional" ? "all" : "conditional"))}
        />
        <OpportunityMetric
          active={filter === "storage"}
          value={summary.storageOnly}
          label="仅入库"
          onClick={() => setFilter((current) => (current === "storage" ? "all" : "storage"))}
        />
        <OpportunityMetric value={summary.today} label="今日测算" />
      </div>
      <OpportunityFilters filter={filter} summary={summary} onChange={setFilter} total={items.length} />
      {items.length === 0 && !loading ? (
        <p className="valuation-empty">暂无估值测算结果</p>
      ) : (
        <div className="valuation-opportunity-layout">
          <div className="valuation-opportunity-list" role="list">
            <div className="valuation-opportunity-head" aria-hidden="true">
              <span>股票</span>
              <span>空间测算</span>
              <span>状态</span>
              <span>锚类型</span>
              <span>证据等级</span>
              <span>缺口原因</span>
              <span>最新测算</span>
              <span>来源</span>
              <span>操作</span>
            </div>
            {filteredItems.map((item) => (
              <OpportunityRow
                active={item.stock_key === selected?.stock_key}
                item={item}
                key={item.stock_key}
                onOpenReport={props.onOpenReport}
                onOpenSession={props.onOpenSession}
                onSelect={() => {
                  setSelectedKey(item.stock_key);
                  setDetailOpen(true);
                }}
              />
            ))}
            {!loading && filteredItems.length === 0 && <p className="valuation-empty">当前筛选无测算结果</p>}
          </div>
          <OpportunityDetail item={selected} onOpenReport={props.onOpenReport} onOpenSession={props.onOpenSession} />
          {detailOpen && selected ? (
            <div
              className="valuation-opportunity-detail-backdrop"
              role="presentation"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) {
                  setDetailOpen(false);
                }
              }}
            >
              <OpportunityDetail
                item={selected}
                onClose={() => setDetailOpen(false)}
                onOpenReport={props.onOpenReport}
                onOpenSession={props.onOpenSession}
              />
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function OpportunityMetric(props: {
  active?: boolean;
  value: number;
  label: string;
  tone?: "notify" | "conditional";
  onClick?: () => void;
}) {
  const className = [
    "valuation-opportunity-metric",
    props.tone,
    props.active ? "active" : "",
    props.onClick ? "clickable" : "",
  ]
    .filter(Boolean)
    .join(" ");
  if (props.onClick) {
    return (
      <button className={className} type="button" onClick={props.onClick}>
        <strong>{props.value}</strong>
        <em>{props.label}</em>
      </button>
    );
  }
  return (
    <span className={className}>
      <strong>{props.value}</strong>
      <em>{props.label}</em>
    </span>
  );
}

function OpportunityFilters(props: {
  filter: OpportunityFilter;
  summary: ReturnType<typeof summarizeOpportunities>;
  total: number;
  onChange: (filter: OpportunityFilter) => void;
}) {
  return (
    <div className="valuation-opportunity-filters" aria-label="通知等级筛选">
      <FilterButton active={props.filter === "all"} count={props.total} label="全部" onClick={() => props.onChange("all")} />
      <FilterButton
        active={props.filter === "notify"}
        count={props.summary.notify}
        label="可通知"
        onClick={() => props.onChange("notify")}
      />
      <FilterButton
        active={props.filter === "conditional"}
        count={props.summary.conditional}
        label="条件触发"
        onClick={() => props.onChange("conditional")}
      />
      <FilterButton
        active={props.filter === "storage"}
        count={props.summary.storageOnly}
        label="仅入库"
        onClick={() => props.onChange("storage")}
      />
    </div>
  );
}

function FilterButton(props: { active: boolean; count: number; label: string; onClick: () => void }) {
  return (
    <button className={props.active ? "active" : ""} type="button" onClick={props.onClick}>
      <span>{props.label}</span>
      <strong>{props.count}</strong>
    </button>
  );
}

function OpportunityRow(props: {
  active: boolean;
  item: ValuationMeasurementOpportunity;
  onOpenReport: (reportId: string) => void;
  onOpenSession: (snapshot: ValuationMeasurementOpportunitySnapshot) => void;
  onSelect: () => void;
}) {
  const latest = props.item.latest;
  return (
    <article
      className={props.active ? "valuation-opportunity-row active" : "valuation-opportunity-row"}
      onClick={props.onSelect}
      role="listitem"
    >
      <span className="valuation-opportunity-stock">
        <strong>{props.item.name}</strong>
        <em>{props.item.ts_code ?? props.item.stock_key}</em>
      </span>
      <strong className={latest.is_positive ? "valuation-opportunity-upside positive" : "valuation-opportunity-upside"}>
        {latest.upside_text || "未给出"}
      </strong>
      <NotificationBadge snapshot={latest} />
      <span>{latest.anchor_type || "-"}</span>
      <span>{latest.evidence_level || "-"}</span>
      <span title={latest.gap_reason || undefined}>{clipInline(latest.gap_reason || "-")}</span>
      <span>{compactDateTime(latest.measured_at)}</span>
      <span>{compactSourceTime(latest.source_generated_at)}</span>
      <span className="valuation-opportunity-actions">
        <button type="button" onClick={(event) => {
          event.stopPropagation();
          props.onSelect();
        }}>
          详情
        </button>
        <button type="button" onClick={(event) => {
          event.stopPropagation();
          props.onOpenSession(latest);
        }}>
          Session
        </button>
        <button type="button" onClick={(event) => {
          event.stopPropagation();
          props.onOpenReport(latest.report_id);
        }}>
          来源
        </button>
      </span>
    </article>
  );
}

function OpportunityDetail(props: {
  item: ValuationMeasurementOpportunity | null;
  onClose?: () => void;
  onOpenReport: (reportId: string) => void;
  onOpenSession: (snapshot: ValuationMeasurementOpportunitySnapshot) => void;
}) {
  if (!props.item) {
    return <aside className="valuation-opportunity-detail empty">选择一条测算结果</aside>;
  }
  const latest = props.item.latest;
  return (
    <aside className="valuation-opportunity-detail">
      <header>
        <div>
          <h3>{props.item.name}</h3>
          <span>{props.item.ts_code ?? props.item.stock_key}</span>
        </div>
        <NotificationBadge snapshot={latest} />
        {props.onClose ? (
          <button className="valuation-opportunity-detail-close" type="button" aria-label="关闭详情" onClick={props.onClose}>
            <X size={16} />
          </button>
        ) : null}
      </header>
      <div className="valuation-opportunity-detail-grid">
        <DetailItem label="剩余空间" value={latest.upside_text || "未给出"} highlight={latest.is_positive} />
        <DetailItem label="状态" value={latest.valuation_status || "-"} />
        <DetailItem label="锚类型" value={latest.anchor_type || "-"} />
        <DetailItem label="证据等级" value={latest.evidence_level || "-"} />
        <DetailItem label="当前市值" value={latest.current_mv_text || "-"} />
        <DetailItem label="目标市值" value={latest.target_mv_text || "-"} />
      </div>
      <section className="valuation-opportunity-note">
        <span>缺口原因</span>
        <p>{latest.gap_reason || "未标记"}</p>
      </section>
      <section className="valuation-opportunity-note">
        <span>关键验证</span>
        <p>{latest.key_validation || "未标记"}</p>
      </section>
      <section className="valuation-opportunity-history">
        <h4>测算历史</h4>
        {props.item.history.map((snapshot) => (
          <button
            className="valuation-opportunity-history-row"
            key={`${snapshot.measurement_id}-${snapshot.item_id}`}
            type="button"
            onClick={() => props.onOpenSession(snapshot)}
          >
            <span>{compactDateTime(snapshot.measured_at)}</span>
            <strong>{snapshot.upside_text || "未给出"}</strong>
            <NotificationBadge snapshot={snapshot} />
          </button>
        ))}
      </section>
      <div className="valuation-opportunity-detail-actions">
        <button type="button" onClick={() => props.onOpenReport(latest.report_id)}>
          来源报告
        </button>
        <button type="button" onClick={() => props.onOpenSession(latest)}>
          Session
        </button>
        {latest.published_url ? (
          <a href={latest.published_url} target="_blank" rel="noreferrer">
            测算页
            <ExternalLink size={13} />
          </a>
        ) : null}
      </div>
    </aside>
  );
}

function DetailItem(props: { label: string; value: string; highlight?: boolean }) {
  return (
    <span className={props.highlight ? "valuation-opportunity-detail-item highlight" : "valuation-opportunity-detail-item"}>
      <em>{props.label}</em>
      <strong>{props.value}</strong>
    </span>
  );
}

function NotificationBadge({ snapshot }: { snapshot: ValuationMeasurementOpportunitySnapshot }) {
  return <span className={`valuation-notification-badge ${notificationClass(snapshot)}`}>{notificationText(snapshot)}</span>;
}

function summarizeOpportunities(items: ValuationMeasurementOpportunity[]) {
  const today = formatTime(new Date().toISOString()).slice(0, 10);
  const notify = items.filter((item) => isNotify(item.latest)).length;
  const conditional = items.filter((item) => item.latest.notification_level === "条件触发").length;
  const todayCount = items.reduce(
    (count, item) => count + item.history.filter((snapshot) => formatTime(snapshot.measured_at).slice(0, 10) === today).length,
    0,
  );
  return {
    notify,
    conditional,
    storageOnly: Math.max(items.length - notify - conditional, 0),
    today: todayCount,
  };
}

function filterOpportunities(items: ValuationMeasurementOpportunity[], filter: OpportunityFilter) {
  if (filter === "all") {
    return items;
  }
  if (filter === "notify") {
    return items.filter((item) => isNotify(item.latest));
  }
  if (filter === "conditional") {
    return items.filter((item) => item.latest.notification_level === "条件触发");
  }
  return items.filter((item) => !isNotify(item.latest) && item.latest.notification_level !== "条件触发");
}

function notificationText(snapshot: ValuationMeasurementOpportunitySnapshot): string {
  if (isNotify(snapshot)) {
    return "可通知";
  }
  if (snapshot.notification_level === "条件触发") {
    return "条件触发";
  }
  return snapshot.notification_level || "仅入库";
}

function notificationClass(snapshot: ValuationMeasurementOpportunitySnapshot): string {
  if (isNotify(snapshot)) {
    return "level-notify";
  }
  if (snapshot.notification_level === "条件触发") {
    return "level-conditional";
  }
  return "level-storage";
}

function isNotify(snapshot: ValuationMeasurementOpportunitySnapshot): boolean {
  return snapshot.notification_level === "可通知" || snapshot.is_positive;
}

function compactDateTime(value: string): string {
  return formatTime(value).slice(5, 16);
}

function compactSourceTime(value?: string | null): string {
  return value ? formatTime(value).slice(5, 16) : "-";
}

function clipInline(value: string): string {
  return value.length > 18 ? `${value.slice(0, 18)}...` : value;
}
