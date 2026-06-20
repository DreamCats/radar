# 产业链内容库

这里存放 `产业链` Tab 的内容资产，不放在 `docs/` 下。

定位：

- `plan.md`：产业链 Tab 的产品和内容规划。
- `chains/`：单个产业链学习页，一条产业链一个 Markdown 文件。
- `chains/*.json`：对应产业链的结构化图谱数据，供前端画图和工具读取。
- `index.json`：产业链目录索引，供列表页读取。
- `templates/`：新增产业链页面时使用的模板。

当前约定：

- 文件内容先由 Codex 调研、整理和维护。
- 先追求少数高质量产业链页面，不做自动批量生成。
- 每个产业页尽量保持统一结构，方便后续接入 Web 页面或结构化解析。
- 公司映射必须保留证据状态，不把概念相关直接写成确定受益。

后续如果需要更强结构化，可以在当前 JSON 基础上继续拆分 `meta`、`nodes`、`edges`、`companies` 等数据文件。

## 当前目录结构

```text
data/industry-chains/
  README.md
  plan.md
  index.json
  chains/
    ai-liquid-cooling.md
    ai-liquid-cooling.json
  templates/
    chain-page-template.md
```

## 内容生产流程

新增一条产业链时，按这个顺序做：

1. 复制 `templates/chain-page-template.md`，写成 `chains/{chain_id}.md`。
2. 在同目录补 `chains/{chain_id}.json`，至少包含 `quick_read`、`learning_steps`、`evidence_policy`、`nodes`、`edges`、`concept_diagrams`、`companies`、`catalysts`。
3. 在 `index.json` 增加目录项。
4. 公司映射先保守标注证据状态，不把概念相关直接写成确定受益。

## 结构化数据最小字段

`chains/{chain_id}.json` 先保持统一，不追求自动化生成，但每个产业都要让小白按固定路径读懂：

- `chain_id`：产业链 ID，和文件名保持一致。
- `quick_read`：3 分钟看懂，包含 `headline`、`summary`、`logic_chain`、`takeaways`。
- `learning_steps`：认知路径，回答“先看什么、再看什么、最后验证什么”。
- `evidence_policy`：证据等级说明，统一解释 `supported`、`weakly_supported`、`candidate`、`unsupported`。
- `nodes`：图谱节点，包含 `id`、`label`、`layer`、`beginner_explanation`、`bottleneck_strength`、`evidence_status`，并补 `teach` 教学卡。
- `edges`：图谱关系，包含 `source`、`target`、`relation_type`、`label`、`description`、`evidence_status`。
- `concept_diagrams`：术语图解，用少量图卡解释新手不熟的核心概念，并绑定相关节点。
- `companies`：A 股公司映射，包含 `name`、`ts_code`、`nodes`、`role`、`tier`、`current_view`、`evidence_status`、`next_checks`，并补 `why_watch`、`evidence_basis`、`verification_focus`、`risks`。
- `catalysts`：市场催化，分短期、中期、兑现等维度解释关注度如何传导。
- `financial_translations`：财务转译，解释节点最终要看财报和公告里的哪些指标。
- `common_misreads`：常见误区。
- `tracking_metrics`：后续跟踪指标。
- `sources`：资料来源。

证据状态统一使用：

- `supported`：已有较强公开证据支持。
- `weakly_supported`：有公开线索，但还需要一手证据补强。
- `candidate`：候选关系，不能作为确定受益结论。
- `unsupported`：已发现证据不足或需要降级。
