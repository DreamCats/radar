# radar · 个人投研工作台 — 文档索引

> 私人投研工作台。同源于给老板做的 `stock-news`（微信投研信息流 CLI），
> 但 radar 是给**个人投资者（我自己）**用的专属工作台。

本目录沉淀立项前的调研与需求，方便后续追溯「为什么这样设计」。

## 文档清单

| 文档 | 内容 | 状态 |
|---|---|---|
| [01-data-source.md](./01-data-source.md) | 数据源调研：微信群消息 raw 数据结构、API、噪音特征 | ✅ 已调研 |
| [02-prior-art-stock-news.md](./02-prior-art-stock-news.md) | 老项目 stock-news 全链路调研：架构 / 能力 / 可借鉴可避坑 | ✅ 已调研 |
| [03-requirements.md](./03-requirements.md) | radar 的需求与定位（待和本人逐条确认） | 🟡 待确认 |
| [04-open-questions.md](./04-open-questions.md) | 待决策的开放问题 | 🟡 进行中 |
| [05-tech-stack.md](./05-tech-stack.md) | 技术选型 + 设计方向（Q1/Q6 已决策） | ✅ 已定稿 |
| [06-design-eval.md](./06-design-eval.md) | 设计风格评估（Q8 已决策：Linear + 涨跌色） | ✅ 已定稿 |
| `../DESIGN.md` | 落地的设计系统（Linear 基底 + radar 金融扩展） | ✅ 已生成 |

## 一句话定位（草案，待确认）

> stock-news 是给老板做的「大而全、人+Agent 通用」投研信息流 CLI；
> radar 是给我自己做的「小而专、个性化降噪」的私人投研工作台，
> **复用同一个微信数据源**，但只服务我一个人的关注面和决策习惯。

## 核心原则（草案）

1. **不重写轮子** — 老项目那套 `fetch→classify→extract→opinion→strategy→backtest` 已经完整，
   照抄只会得到一个更烂的 stock-news。radar 的价值在老项目「没做好/不个性化」的地方。
2. **私人优先** — 白名单关注群/赛道/个股，狠狠降噪（生活群、作业群直接滤掉）。
3. **先理需求再动手** — 本轮只做调研沉淀，不写业务代码。

_最后更新：2026-06-03_
