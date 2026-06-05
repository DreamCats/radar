import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ReactNode } from "react";

import { PanelTitle } from "./PanelTitle";
import type { MessageOverview, MessageOverviewGroup } from "../types";

const COLORS = {
  primary: "var(--color-primary)",
  primaryHover: "var(--color-primary-hover)",
  group: "var(--color-primary)",
  personal: "var(--color-market-up)",
  grid: "var(--color-hairline)",
  text: "var(--color-ink-subtle)",
};

export function TrendChart({ overview }: { overview: MessageOverview | null }) {
  const data = overview?.date_buckets.map((item) => ({
    ...item,
    label: item.date.slice(5),
  })) ?? [];

  return (
    <ChartPanel title="消息趋势" meta="最近窗口 · 按天聚合" isEmpty={data.length === 0}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 14, right: 12, bottom: 0, left: -18 }}>
          <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: COLORS.text, fontSize: 12 }} />
          <YAxis tickLine={false} axisLine={false} tick={{ fill: COLORS.text, fontSize: 12 }} allowDecimals={false} />
          <Tooltip content={<ChartTooltip />} />
          <Area
            type="monotone"
            dataKey="group_message_count"
            name="个人群"
            stackId="messages"
            stroke={COLORS.group}
            fill={COLORS.group}
            fillOpacity={0.3}
          />
          <Area
            type="monotone"
            dataKey="personal_message_count"
            name="个人消息"
            stackId="messages"
            stroke={COLORS.personal}
            fill={COLORS.personal}
            fillOpacity={0.22}
          />
        </AreaChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
}

export function TopGroupsChart({ data }: { data: MessageOverviewGroup[] }) {
  const chartData = data.map((item) => ({
    ...item,
    label: shortLabel(item.group_name, 8),
  }));

  return (
    <ChartPanel title="活跃群组" meta="Top 群 · 全库" isEmpty={chartData.length === 0}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} layout="vertical" margin={{ top: 10, right: 16, bottom: 0, left: 18 }}>
          <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tick={{ fill: COLORS.text, fontSize: 12 }}
            width={74}
          />
          <Tooltip content={<ChartTooltip labelKey="group_name" />} />
          <Bar dataKey="count" name="消息" fill={COLORS.primaryHover} radius={[0, 5, 5, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
}

function ChartPanel(props: { title: string; meta: string; children: ReactNode; isEmpty: boolean }) {
  return (
    <section className="content-panel panel chart-panel">
      <PanelTitle title={props.title} meta={props.meta} />
      <div className="chart-canvas">{props.isEmpty ? <p className="empty-line chart-empty">暂无数据</p> : props.children}</div>
    </section>
  );
}

type TooltipPayload = {
  color?: string;
  name?: string;
  value?: number | string;
  payload?: Record<string, unknown>;
};

function ChartTooltip(props: {
  active?: boolean;
  label?: string | number;
  payload?: TooltipPayload[];
  labelKey?: string;
}) {
  if (!props.active || !props.payload?.length) {
    return null;
  }
  const payloadLabel = props.labelKey ? props.payload[0]?.payload?.[props.labelKey] : undefined;
  return (
    <div className="chart-tooltip">
      <p>{String(payloadLabel ?? props.label ?? "")}</p>
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
