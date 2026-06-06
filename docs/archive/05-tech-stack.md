# 05 · 技术选型与设计方向（定稿）

> 对应开放问题 Q1（形态）/ Q6（技术栈）。本文为**已决策**结论。
> 决策日期：2026-06-03

## 决策摘要

| 层 | 选型 | 来源 / 理由 |
|---|---|---|
| 语言 / 工具链 | **Python 3.10+ / uv** | 与 stock-news 一致；数据源逻辑直接复用 |
| CLI | **click** | 同 stock-news |
| 数据模型 | **pydantic v2** | 同 stock-news |
| Web 后端 | **FastAPI + uvicorn** | 复用 live-content-flow 范式；与 pydantic 一体 |
| Web 前端 | **React 19 + Vite + TypeScript + Tailwind** | 复用 live-content-flow 范式 |
| 存储 | **SQLite** | 本人已拍板；SQL 筛选爽，零运维 |
| 设计系统 | **DESIGN.md（待选风格，见下）** | 借鉴 live-content-flow + awesome-design-md |

## 整体架构：共享数据核 + 双门面

```
radar (Python / uv)
├── core/          数据核（CLI 和 Web 共享，逻辑只写一遍）
│   ├── fetch      微信 API 拉取（复用 stock-news 逻辑）
│   ├── store      SQLite 落盘 + 去重 + 窗口缓存
│   ├── messages   消息/会话分页查询
│   ├── usecases   ingest / classification 等业务编排
│   └── models     pydantic
├── cli/           click —— radar fetch / list / stats ...
└── web/
    ├── server/    FastAPI（读 core，提供 JSON API）
    └── ui/        React 19 + Vite + TS + Tailwind
```

**核心约束：CLI 和 Web 都只是 core 的门面，数据处理逻辑绝不重复写两套。**
后期加信号雷达，只在 core 加逻辑，CLI 和 Web 自动都能用。

## 为什么前端用 React 而不是 htmx（决策记录）

立项时评估过 htmx，最终放弃。记录依据，避免以后重复纠结。

### htmx 是什么
一个 JS 库（非 HTML 新标准），用 HTML 属性直接发请求、服务端返回 HTML 片段局部刷新。
2020 年发布（前身 intercooler.js 2013）。**不是新东西**。

### 真实数据（2025 State of JS，2026-02 发布；非拥护者文章）
| 指标 | htmx | React |
|---|---|---|
| 实际使用率 | ~7% | ~80–83.6% |
| npm 周下载 | ~9.4万 | ~5300万–9600万（约 1000x）|
| 全球招聘岗位 | ~2,000 | ~847,000 |
| 前端市场份额 | 小众 | 68% |

### 结论
- "2026 htmx 流行"是**标题党/圈层热度**，不是行业事实。中立来源原话：
  "momentum isn't adoption"——讨论度高，实际生产使用远落后。
- htmx 是**特定场景**（服务端渲染 + 中等交互 CRUD）的合理替代，**不是 React 通用替代**。
- **对 radar：放弃 htmx。** 理由：(1) 已有 live-content-flow 的 React 范式可直接复用，心智零迁移；
  (2) 后期信号雷达看板要图表/热力图/可能实时流，React 生态最稳；
  (3) htmx 的"极简"优势不值得为它新学一套。

> htmx 仅作为「评估过但不选」的备选留档。

## 可复用的现成范式（live-content-flow）

`~/Work/tools/bytedance/live-content-flow` 提供可直接抄的脚手架：
- **前端组织**：feature-based —— `app/ components/ features/ lib/{api,types} styles/`
- **api 层**：每个后端资源一个文件（projects.ts / sessions.ts / stream.ts ...）
- **前后端联调**：Vite dev proxy 转发到 FastAPI（localhost:8000）
- **流式**：已有 `stream.ts`（SSE）——后期实时告警可借鉴
- **Tailwind 配置**：可直接搬

## 设计方向：DESIGN.md

### 概念
`DESIGN.md`（Google Stitch 提出）= 纯文本设计系统文档，AI agent 读它生成风格一致的 UI。
- `AGENTS.md` 管「怎么建」，`DESIGN.md` 管「长什么样」。
- 参考库：`~/Work/github/awesome-design-md`（66 个知名网站范本 + preview.html）。

### 候选风格（适合投研/数据看板气质）
| 范本 | 气质 | 适配点 |
|---|---|---|
| **Catppuccin**（live-content-flow 现成）| 柔和分层、护眼、长阅读友好 | 已有现成 DESIGN.md，心智零迁移 ⭐ |
| **Linear** | 极简、精准、紫色点缀 | 工作台标杆，信息密度高 |
| **Sentry** | 暗色仪表盘、数据密集 | 天生为「看数据流」设计 |
| **Kraken** | 紫调暗色、数据密集仪表盘 | 金融/交易气质 |
| **ClickHouse** | 黄色点缀、技术文档风 | 分析型、数据驱动 |

### 倾向（待本人最终确认）
- 默认倾向**直接复用 live-content-flow 的 Catppuccin DESIGN.md**：已成型、护眼、适合每天长时间看。
- 若想更「数据看板/交易台」气质，可参考 Sentry / Kraken，从 awesome-design-md 取范本融合。

**待确认**：radar 用 Catppuccin（复用）还是另选一个数据看板风格？

## 仍待确认（不影响起步）
- Q3 关注面（订阅哪些群 / 赛道 / 个股）
- Q4 是否引入 Tushare 行情回测
- Q7 radar 数据目录路径（建议 `~/.config/radar/`）

_最后更新：2026-06-03_
