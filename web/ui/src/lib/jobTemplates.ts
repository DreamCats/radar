import { Anchor, Bot, ChartNoAxesCombined, Database, GitBranch, Sparkles } from "lucide-react";

import type { IngestSource, MessageCategory } from "../types";
import type { JobTemplateKey } from "./jobRuns";

export const DEFAULT_CATEGORIES: MessageCategory[] = ["research", "recommendation", "industry"];

export const SOURCE_OPTIONS: Array<[IngestSource, string]> = [
  ["all", "全部"],
  ["personal_message", "个人消息"],
  ["group_message", "个人群"],
];

const ALL_JOB_TEMPLATES = [
  { key: "ingest", title: "微信数据源", meta: "原始入库", serves: "服务于全站数据底座", icon: Database },
  { key: "classify", title: "消息分类", meta: "LLM 派生", serves: "服务于整理 / 榜单 / 策略", icon: Bot },
  { key: "anchor", title: "Anchor 更新", meta: "市场词库", serves: "更新股票 / 概念 / 行业 / 主题", icon: Anchor },
  { key: "refine", title: "聚合 Refine", meta: "LLM 聚合", serves: "服务于总览 / 整理", icon: Sparkles },
  { key: "backtest", title: "推荐回测补齐", meta: "T+N 补齐", serves: "服务于榜单胜率回测", icon: ChartNoAxesCombined },
  { key: "stockEvidenceChain", title: "个股证据链", meta: "策略离线", serves: "服务于早期筛选 / 阶段判断", icon: GitBranch },
] satisfies Array<{ key: JobTemplateKey; title: string; meta: string; serves: string; icon: typeof Database }>;

export const JOB_TEMPLATES = ALL_JOB_TEMPLATES;

export const JOB_TEMPLATE_GROUPS = [
  {
    title: "基础作业",
    items: JOB_TEMPLATES.filter((item) => ["ingest", "classify", "anchor", "refine", "backtest"].includes(item.key)),
  },
  {
    title: "策略作业",
    items: JOB_TEMPLATES.filter((item) => item.key === "stockEvidenceChain"),
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
    return ["按交易日更新", "只写 market_anchors", "不扫描消息库"];
  }
  if (kind === "backtest") {
    return ["默认近 30 天", "补齐 T+1/T+2/T+3/T+5", "已完成窗口自动跳过", "未成熟下次继续补"];
  }
  if (kind === "stockEvidenceChain") {
    return ["默认证据回看 40 天", "候选最多 120 只", "LLM 并发 16", "相同证据自动复用判断"];
  }
  return ["候选 50", "单批 5", "LLM 并发 10", "命中缓存则跳过"];
}
