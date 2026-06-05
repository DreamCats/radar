import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ReactNode } from "react";

import { PanelTitle } from "./PanelTitle";
import type { MessageOverview, MessageOverviewGroup, MessageOverviewHour, MessageOverviewSource, RunItem } from "../types";

const COLORS = {
  primary: "var(--color-primary)",
  primaryHover: "var(--color-primary-hover)",
  group: "var(--color-primary)",
  personal: "var(--color-market-up)",
  warn: "var(--color-signal-hot)",
  down: "var(--color-market-down)",
  grid: "var(--color-hairline)",
  text: "var(--color-ink-subtle)",
};

const PIE_COLORS = [COLORS.group, COLORS.personal, COLORS.warn, COLORS.down];

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

export function SourceBreakdownChart({ data }: { data: MessageOverviewSource[] }) {
  return (
    <ChartPanel title="来源构成" meta="全库消息" isEmpty={data.length === 0}>
      <div className="donut-layout">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Tooltip content={<ChartTooltip />} />
            <Pie data={data} dataKey="count" nameKey="source" innerRadius={50} outerRadius={76} paddingAngle={2}>
              {data.map((item, index) => (
                <Cell key={item.source} fill={PIE_COLORS[index % PIE_COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="chart-legend">
          {data.map((item, index) => (
            <span key={item.source}>
              <i style={{ background: PIE_COLORS[index % PIE_COLORS.length] }} />
              {item.source} {item.count}
            </span>
          ))}
        </div>
      </div>
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

export function HourlyActivityChart({ data }: { data: MessageOverviewHour[] }) {
  const chartData = data.map((item) => ({
    ...item,
    label: `${String(item.hour).padStart(2, "0")}:00`,
  }));

  return (
    <ChartPanel title="时段分布" meta="24 小时 · 全库" isEmpty={chartData.every((item) => item.count === 0)}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 12, right: 12, bottom: 0, left: -20 }}>
          <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="label"
            interval={3}
            tickLine={false}
            axisLine={false}
            tick={{ fill: COLORS.text, fontSize: 12 }}
          />
          <YAxis tickLine={false} axisLine={false} tick={{ fill: COLORS.text, fontSize: 12 }} allowDecimals={false} />
          <Tooltip content={<ChartTooltip />} />
          <Bar dataKey="count" name="消息" fill={COLORS.warn} radius={[5, 5, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
}

export function RunTotalsChart({ runs }: { runs: RunItem[] }) {
  const data = runs
    .slice(0, 8)
    .reverse()
    .map((run) => ({
      label: run.started_at.slice(5, 16).replace("T", " "),
      raw_count: run.raw_count,
      stored_count: run.stored_count,
      filtered_count: run.filtered_count,
    }));

  return (
    <ChartPanel title="近期作业" meta="最近 8 次 · raw / stored / filtered" isEmpty={data.length === 0}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 12, right: 12, bottom: 0, left: -20 }}>
          <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: COLORS.text, fontSize: 11 }} />
          <YAxis tickLine={false} axisLine={false} tick={{ fill: COLORS.text, fontSize: 12 }} allowDecimals={false} />
          <Tooltip content={<ChartTooltip />} />
          <Bar dataKey="raw_count" name="raw" fill={COLORS.primaryHover} radius={[4, 4, 0, 0]} />
          <Bar dataKey="stored_count" name="stored" fill={COLORS.personal} radius={[4, 4, 0, 0]} />
          <Bar dataKey="filtered_count" name="filtered" fill={COLORS.down} radius={[4, 4, 0, 0]} />
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
