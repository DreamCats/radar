import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type { ReactNode } from "react";

import { PanelTitle } from "./PanelTitle";
import type { MessageAnchorHeat, MessageOverview, MessageOverviewGroup, OrganizeAggregateTheme } from "../types";

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

export function AnchorHeatChart({ data }: { data: MessageAnchorHeat[] }) {
  const chartData = data.slice(0, 12).map((item) => ({
    ...item,
    label: shortLabel(item.name, 9),
  }));

  return (
    <ChartPanel title="Anchor 热力词" meta="最近窗口 · Top 命中" isEmpty={chartData.length === 0}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} layout="vertical" margin={{ top: 10, right: 34, bottom: 0, left: 22 }}>
          <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tick={{ fill: COLORS.text, fontSize: 12 }}
            interval={0}
            width={86}
          />
          <Tooltip content={<AnchorTooltip />} />
          <Bar dataKey="message_count" name="消息" fill={COLORS.personal} radius={[0, 5, 5, 0]}>
            <LabelList dataKey="message_count" position="right" fill={COLORS.text} fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
}

export function ThemePriorityBubbleChart({ themes }: { themes: OrganizeAggregateTheme[] }) {
  const chartData = themes.slice(0, 20).map((theme) => ({
    ...theme,
    x: Math.round(theme.priority_score),
    y: Math.round(theme.actionability_score),
    evidenceCount: Math.max(theme.evidence_message_ids.length, 1),
    confidencePercent: Math.round(theme.confidence * 100),
  }));

  return (
    <ChartPanel title="聚合主题图" meta="优先级 x 行动分 · Top 20" isEmpty={chartData.length === 0}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 16, right: 18, bottom: 4, left: -10 }}>
          <CartesianGrid stroke={COLORS.grid} strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="x"
            name="优先级"
            domain={[0, 100]}
            tickLine={false}
            axisLine={false}
            tick={{ fill: COLORS.text, fontSize: 12 }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="行动分"
            domain={[0, 100]}
            tickLine={false}
            axisLine={false}
            tick={{ fill: COLORS.text, fontSize: 12 }}
          />
          <ZAxis type="number" dataKey="evidenceCount" range={[72, 420]} />
          <Tooltip content={<ThemeTooltip />} cursor={{ stroke: COLORS.grid, strokeDasharray: "3 3" }} />
          <Scatter data={chartData} name="主题">
            {chartData.map((item) => (
              <Cell key={`${item.theme_index}-${item.theme_name}`} fill={themeColor(item.confidencePercent)} />
            ))}
          </Scatter>
        </ScatterChart>
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

function AnchorTooltip(props: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!props.active || !props.payload?.length) {
    return null;
  }
  const item = props.payload[0]?.payload as MessageAnchorHeat | undefined;
  if (!item) {
    return null;
  }
  return (
    <div className="chart-tooltip">
      <p>{item.name}</p>
      <span>类型: {anchorTypeLabel(item.anchor_type)}</span>
      <span>消息: {item.message_count}</span>
      <span>高价值: {item.high_value_count}</span>
      <span>置信: {Math.round(item.average_confidence * 100)}%</span>
    </div>
  );
}

function ThemeTooltip(props: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!props.active || !props.payload?.length) {
    return null;
  }
  const item = props.payload[0]?.payload as
    | (OrganizeAggregateTheme & { x: number; y: number; evidenceCount: number; confidencePercent: number })
    | undefined;
  if (!item) {
    return null;
  }
  return (
    <div className="chart-tooltip theme-tooltip">
      <p>{item.theme_name}</p>
      <span>优先级: {item.x}</span>
      <span>行动分: {item.y}</span>
      <span>置信: {item.confidencePercent}%</span>
      <span>证据: {item.evidenceCount}</span>
      {item.related_stocks.length > 0 && <span>标的: {item.related_stocks.slice(0, 3).map((stock) => stock.name).join(" / ")}</span>}
    </div>
  );
}

function shortLabel(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength)}...`;
}

function anchorTypeLabel(value: MessageAnchorHeat["anchor_type"]): string {
  return {
    concept: "概念",
    industry: "行业",
    theme: "主题",
    stock: "个股",
  }[value];
}

function themeColor(confidencePercent: number): string {
  if (confidencePercent >= 80) {
    return "var(--color-market-up)";
  }
  if (confidencePercent >= 65) {
    return "var(--color-primary-hover)";
  }
  return "var(--color-signal-hot)";
}
