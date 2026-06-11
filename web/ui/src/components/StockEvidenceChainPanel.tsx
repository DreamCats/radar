import { CheckCircle2, CircleAlert, MessageSquareText, Network, TrendingUp, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { formatTime } from "../lib/datetime";
import type { StockEvidenceChainDashboard, StockEvidenceChainItem } from "../types";
import { StockEvidenceDetailPanel } from "./StockEvidenceDetailPanel";
import { PanelTitle } from "./PanelTitle";

const STAGE_ORDER = ["线索期", "种子期", "论证期", "扩散期", "定价期", "拥挤期"];

type Props = {
  data: StockEvidenceChainDashboard | null;
  error: string | null;
  onSelectStock?: (stock: StockEvidenceChainItem) => void;
};

export function StockEvidenceChainPanel({ data, error, onSelectStock }: Props) {
  const items = data?.items ?? [];
  const [stage, setStage] = useState("全部");
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const filteredItems = stage === "全部" ? items : items.filter((item) => item.stage_label === stage);
  const selected = filteredItems.find((item) => item.ts_code === selectedCode) ?? filteredItems[0] ?? null;
  const stageTabs = useMemo(() => ["全部", ...STAGE_ORDER.filter((label) => data?.stage_counts[label])], [data?.stage_counts]);

  useEffect(() => {
    if (!selectedCode && items[0]) {
      setSelectedCode(items[0].ts_code);
    }
  }, [items, selectedCode]);

  useEffect(() => {
    if (stage !== "全部" && !data?.stage_counts[stage]) {
      setStage("全部");
    }
  }, [data?.stage_counts, stage]);

  return (
    <div className="stock-evidence-workbench">
      <div className="statbar metric-grid">
        <Metric label="候选股票" value={data?.item_count ?? 0} detail="最新证据链判断" />
        <Metric label="观察池" value={earlyCount(items)} detail="线索 / 种子 / 论证" />
        <Metric label="正在定价" value={stageCount(data, "定价期")} detail="需要结合价格风险" />
        <Metric label="拥挤风险" value={stageCount(data, "拥挤期")} detail="优先复盘不追高" />
      </div>
      {error && <p className="error-line">{error}</p>}
      {!error && !items.length && <p className="empty-line">暂无个股证据链判断。先在作业中心运行「个股证据链」。</p>}
      {!!items.length && (
        <section className="panel stock-evidence-panel">
          <PanelTitle title="个股证据链" meta={windowMeta(data)} titleExtra={<SortRuleHelp />} />
          <div className="stock-evidence-stage-tabs" role="tablist" aria-label="证据链阶段">
            {stageTabs.map((label) => (
              <button className={stage === label ? "active" : ""} type="button" key={label} onClick={() => setStage(label)}>
                {label}
                <span>{label === "全部" ? items.length : data?.stage_counts[label]}</span>
              </button>
            ))}
          </div>
          <div className="stock-evidence-layout">
            <div className="stock-evidence-list" aria-label="股票候选">
              {filteredItems.map((item) => (
                <StockEvidenceRow
                  item={item}
                  selected={item.ts_code === selected?.ts_code}
                  key={item.ts_code}
                  onClick={() => setSelectedCode(item.ts_code)}
                  onOpenChart={onSelectStock}
                />
              ))}
            </div>
            <StockEvidenceDetailPanel item={selected} onOpenChart={onSelectStock} />
          </div>
        </section>
      )}
    </div>
  );
}

function SortRuleHelp() {
  return (
    <span className="stock-evidence-sort-help">
      <button type="button" aria-label="查看排序规则">
        <CircleAlert size={14} />
      </button>
      <span className="stock-evidence-sort-tooltip" role="tooltip">
        <strong>默认按可行动优先级排序</strong>
        <span>先看阶段：种子 / 论证 / 线索 / 早扩散优先。</span>
        <span>再看证据：催化、调研、研报、推票、市场验证。</span>
        <span>然后看新增变化、多人多群扩散、置信度。</span>
        <span>涨幅过大或拥挤期会后置，主要用于复盘避坑。</span>
      </span>
    </span>
  );
}

function StockEvidenceRow({
  item,
  selected,
  onClick,
  onOpenChart,
}: {
  item: StockEvidenceChainItem;
  selected: boolean;
  onClick: () => void;
  onOpenChart?: (stock: StockEvidenceChainItem) => void;
}) {
  return (
    <article className={selected ? "stock-evidence-row selected" : "stock-evidence-row"}>
      <button type="button" onClick={onClick}>
        <div className="stock-evidence-row-head">
          <strong>{item.stock_name}</strong>
          <span>{item.ts_code}</span>
          <StagePill item={item} />
        </div>
        <p>{item.summary || "暂无一句话判断"}</p>
        <div className="stock-evidence-row-metrics">
          <span>
            <MessageSquareText size={13} />
            去重 {item.unique_trigger_count}
          </span>
          <span>
            <Users size={13} />
            {item.sender_count}人/{item.conversation_count}会话
          </span>
          <span>
            <CheckCircle2 size={13} />
            {formatConfidence(item.confidence)}
          </span>
          {item.primary_theme && (
            <span>
              <Network size={13} />
              {item.primary_theme.theme_name}
            </span>
          )}
        </div>
      </button>
      {onOpenChart && (
        <button className="stock-evidence-chart-btn" type="button" onClick={() => onOpenChart(item)}>
          <TrendingUp size={14} />
          K线
        </button>
      )}
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

function StagePill({ item }: { item: StockEvidenceChainItem }) {
  return <span className={`stock-evidence-stage stock-evidence-stage-${item.stage}`}>{item.stage_label}</span>;
}

function stageCount(data: StockEvidenceChainDashboard | null, label: string): number {
  return data?.stage_counts[label] ?? 0;
}

function earlyCount(items: StockEvidenceChainItem[]): number {
  return items.filter((item) => ["线索期", "种子期", "论证期"].includes(item.stage_label)).length;
}

function windowMeta(data: StockEvidenceChainDashboard | null): string {
  if (!data?.as_of_time) {
    return "暂无最新判断";
  }
  return `截至 ${formatTime(data.as_of_time)} · 证据回看 ${data.evidence_start_time ? formatTime(data.evidence_start_time) : "-"}`;
}

function formatConfidence(value?: number | null): string {
  return value === undefined || value === null ? "-" : `${(value * 100).toFixed(0)}%`;
}
