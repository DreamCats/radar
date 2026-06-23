import {
  Anchor,
  Bot,
  Database,
  GitBranch,
  ListTree,
  UserRoundCheck,
} from "lucide-react";

import type { IngestSource } from "../types";
import type { JobTemplateKey } from "./jobRuns";

export const SOURCE_OPTIONS: Array<[IngestSource, string]> = [
  ["all", "全部"],
  ["personal_message", "个人消息"],
  ["group_message", "个人群"],
];

const ALL_JOB_TEMPLATES = [
  { key: "ingest", title: "微信数据源", meta: "原始入库", serves: "服务于全站数据底座", icon: Database },
  { key: "classify", title: "消息分类", meta: "LLM 派生", serves: "服务于整理 / 策略", icon: Bot },
  { key: "anchor", title: "Anchor 更新", meta: "市场词库", serves: "更新股票 / 概念 / 行业 / 主题", icon: Anchor },
  {
    key: "analystBacktest",
    title: "分析师回测",
    meta: "离线回测",
    serves: "追踪分析师提及后表现",
    icon: UserRoundCheck,
  },
  { key: "stockEvidenceChain", title: "个股证据链", meta: "策略离线", serves: "服务于早期筛选 / 阶段判断", icon: GitBranch },
  { key: "lifecycleDigest", title: "机会生命周期摘要", meta: "LLM 旁路", serves: "服务于阶段梳理 / 复盘", icon: ListTree },
] satisfies Array<{ key: JobTemplateKey; title: string; meta: string; serves: string; icon: typeof Database }>;

export const JOB_TEMPLATES = ALL_JOB_TEMPLATES;

export const JOB_TEMPLATE_GROUPS = [
  {
    title: "基础作业",
    items: JOB_TEMPLATES.filter((item) =>
      ["ingest", "classify", "anchor", "analystBacktest"].includes(item.key),
    ),
  },
  {
    title: "策略作业",
    items: JOB_TEMPLATES.filter((item) => ["stockEvidenceChain", "lifecycleDigest"].includes(item.key)),
  },
].filter((group) => group.items.length > 0);

export function configHints(kind: JobTemplateKey): string[] {
  if (kind === "ingest") {
    return ["分片 1h", "拉取并发 4", "写入 SQLite"];
  }
  if (kind === "classify") {
    return ["单批 16", "LLM 并发 10", "低置信阈值 0.65"];
  }
  if (kind === "anchor") {
    return ["按交易日更新", "同步主题归一化", "不扫描消息库"];
  }
  if (kind === "analystBacktest") {
    return ["近 40 天分析师提及", "T+1/T+3/T+5", "默认远程补行情", "summary 默认排除 broad_list"];
  }
  if (kind === "stockEvidenceChain") {
    return ["默认证据回看 40 天", "候选最多 120 只", "LLM 并发 16", "相同证据自动复用判断"];
  }
  if (kind === "lifecycleDigest") {
    return ["读取最新个股证据链", "候选最多 120 只", "LLM 并发 16", "证据未变自动跳过"];
  }
  return [];
}
