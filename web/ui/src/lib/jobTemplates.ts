import { Anchor, Bot, Database, Sparkles } from "lucide-react";

import type { IngestSource, MessageCategory } from "../types";
import type { JobTemplateKey } from "./jobRuns";

export const DEFAULT_CATEGORIES: MessageCategory[] = ["research", "recommendation", "industry"];

export const SOURCE_OPTIONS: Array<[IngestSource, string]> = [
  ["all", "全部"],
  ["personal_message", "个人消息"],
  ["group_message", "个人群"],
];

export const JOB_TEMPLATES = [
  { key: "ingest", title: "微信数据源", meta: "原始入库", icon: Database },
  { key: "classify", title: "消息分类", meta: "LLM 派生", icon: Bot },
  { key: "anchor", title: "Anchor 抽取", meta: "本地词库", icon: Anchor },
  { key: "refine", title: "聚合 Refine", meta: "LLM 聚合", icon: Sparkles },
] satisfies Array<{ key: JobTemplateKey; title: string; meta: string; icon: typeof Database }>;

export function configHints(kind: JobTemplateKey): string[] {
  if (kind === "ingest") {
    return ["分片 1h", "拉取并发 4", "写入 SQLite"];
  }
  if (kind === "classify") {
    return ["单批 16", "LLM 并发 10", "低置信阈值 0.65"];
  }
  if (kind === "anchor") {
    return ["默认 research/recommendation/industry", "置信阈值 0.7", "每条最多 7 个 anchor"];
  }
  return ["候选 50", "单批 5", "LLM 并发 10", "命中缓存则跳过"];
}
