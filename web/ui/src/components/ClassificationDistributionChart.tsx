import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PanelTitle } from "./PanelTitle";
import type { OrganizeClassificationCluster } from "../types";

const COLORS = {
  stable: "var(--color-primary-hover)",
  review: "var(--color-signal-hot)",
  grid: "var(--color-hairline)",
  text: "var(--color-ink-subtle)",
};

type ChartRow = {
  category: string;
  label: string;
  count: number;
  stable_count: number;
  low_confidence_count: number;
  average_confidence: number;
};

export function ClassificationDistributionChart(props: {
  clusters: OrganizeClassificationCluster[];
  totalCount: number;
}) {
  const data = props.clusters.slice(0, 8).map((cluster) => ({
    category: cluster.category,
    label: shortLabel(cluster.label, 10),
    count: cluster.count,
    stable_count: Math.max(cluster.count - cluster.low_confidence_count, 0),
    low_confidence_count: cluster.low_confidence_count,
    average_confidence: cluster.average_confidence,
  }));

  return (
    <section className="content-panel panel chart-panel">
      <PanelTitle title="分类分布" meta={`${props.totalCount} 条消息 · ${props.clusters.length} 个分类`} />
      <div className="chart-canvas">
        {data.length === 0 ? (
          <p className="empty-line chart-empty">暂无分类结果。先在作业页执行消息分类。</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 4, right: 18, bottom: 0, left: 10 }}>
              <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="label"
                tickLine={false}
                axisLine={false}
                tick={{ fill: COLORS.text, fontSize: 12 }}
                width={82}
              />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="stable_count" name="高置信" stackId="count" fill={COLORS.stable} radius={[0, 0, 0, 0]} />
              <Bar dataKey="low_confidence_count" name="待复核" stackId="count" fill={COLORS.review} radius={[0, 5, 5, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}

type TooltipPayload = {
  color?: string;
  name?: string;
  value?: number | string;
  payload?: ChartRow;
};

function ChartTooltip(props: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!props.active || !props.payload?.length) {
    return null;
  }
  const row = props.payload[0]?.payload;
  if (!row) {
    return null;
  }

  return (
    <div className="chart-tooltip">
      <p>{row.label}</p>
      <span>总量: {row.count}</span>
      <span>平均置信: {Math.round(row.average_confidence * 100)}%</span>
      {props.payload.map((item) => (
        <span key={`${item.name}-${item.value}`}>
          <i style={{ background: item.color }} />
          {item.name}: {item.value}
        </span>
      ))}
    </div>
  );
}

function shortLabel(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength)}...`;
}
