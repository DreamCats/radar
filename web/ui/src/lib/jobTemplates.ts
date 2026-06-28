import { Database, RefreshCw, UserRoundCheck, Zap } from "lucide-react";

import type { IngestSource } from "../types";
import type { JobTemplateKey } from "./jobRuns";

export const SOURCE_OPTIONS: Array<[IngestSource, string]> = [
  ["all", "全部"],
  ["personal_message", "个人消息"],
  ["group_message", "个人群"],
];

const ALL_JOB_TEMPLATES = [
  { key: "ingest", title: "微信数据源", meta: "原始入库", serves: "服务于全站数据底座", icon: Database },
  {
    key: "marketStockRefresh",
    title: "市场主数据",
    meta: "全量刷新",
    serves: "股票代码 / 名称映射",
    icon: RefreshCw,
  },
  {
    key: "analystBacktest",
    title: "分析师回测",
    meta: "离线回测",
    serves: "追踪分析师提及后表现",
    icon: UserRoundCheck,
  },
  {
    key: "catalystStrategy",
    title: "催化策略报告",
    meta: "近窗推演",
    serves: "生成并上传 HTML",
    icon: Zap,
  },
] satisfies Array<{ key: JobTemplateKey; title: string; meta: string; serves: string; icon: typeof Database }>;

export const JOB_TEMPLATES = ALL_JOB_TEMPLATES;

export const JOB_TEMPLATE_GROUPS = [
  {
    title: "基础作业",
    items: JOB_TEMPLATES.filter((item) => ["ingest", "marketStockRefresh", "analystBacktest", "catalystStrategy"].includes(item.key)),
  },
].filter((group) => group.items.length > 0);

export function configHints(kind: JobTemplateKey): string[] {
  if (kind === "ingest") {
    return ["分片 1h", "拉取并发 4", "写入 SQLite"];
  }
  if (kind === "analystBacktest") {
    return ["近 40 天分析师提及", "T+1/T+3/T+5", "默认远程补行情", "summary 默认排除 broad_list"];
  }
  if (kind === "marketStockRefresh") {
    return ["刷新 stocks 主数据表", "Tushare stock_basic", "L/D/P 全量替换"];
  }
  if (kind === "catalystStrategy") {
    return ["催化词筛选", "按标的聚合", "上传 Aly", "发 Bark"];
  }
  return [];
}
