# 数据库和表清单

本文档记录当前系统保留的本地数据库、表及用途。默认路径以 `~/.config/radar/data/` 为准；如果配置里覆盖了 `storage.database`、`storage.reports_database` 或 `market.database`，以配置值为准。

## `radar.sqlite3`：消息和作业主库

| 表 | 用途 |
| --- | --- |
| `schema_migrations` | 消息主库 schema 版本记录。 |
| `messages` | 微信个人消息/个人群原始标准化消息。 |
| `messages_fts` | `messages.raw_content` 等字段的 FTS5 全文搜索索引。SQLite 会自动创建配套 shadow 表。 |
| `fetch_windows` | 微信拉取窗口缓存，用于判断时间窗是否已覆盖。 |
| `runs` | CLI/Web 后台作业执行审计和状态。 |
| `analysts` | 分析师别名归一后的主体。 |
| `analyst_aliases` | 分析师别名到主体的映射。 |
| `analyst_stock_mentions` | 分析师消息中识别出的股票提及样本。 |
| `analyst_stock_mention_windows` | 分析师提及后的 T+N 表现窗口。 |
| `job_schedules` | Web 定时任务配置。 |
| `job_schedule_ticks` | 每次定时触发、run-now 触发的记录。 |

## `market.sqlite3`：市场数据主库

| 表 | 用途 |
| --- | --- |
| `schema_migrations` | 市场库 schema 版本记录。 |
| `stocks` | A 股股票主数据表，保存 `ts_code`、6 位代码、名称、上市状态；由市场主数据全量刷新作业维护。 |
| `tushare_cache` | Tushare 非历史接口的短期 KV 缓存。股票代码/名称映射不再依赖此表。 |
| `tushare_history` | Tushare 一维时间序列接口的行级历史缓存，例如日线、指数日线等。 |

## `reports.sqlite3`：报告归档库

| 表 | 用途 |
| --- | --- |
| `schema_migrations` | 报告库 schema 版本记录。 |
| `catalyst_valuation_reports` | 催化估值线索报告归档，保存窗口、结构化 report JSON、渲染 HTML、本地 HTML 路径和发布 URL。 |
| `report_notifications` | 报告通知记录，例如手动 Bark 发送状态和错误信息。 |

## `chat/runs.sqlite3`：对话运行态库

| 表 | 用途 |
| --- | --- |
| `chat_runs` | Chat 流式运行记录、租约、取消状态和请求摘要。 |
| `chat_run_events` | Chat run 的流式事件日志，用于前端断线后恢复订阅。 |

## 其他本地数据

| 路径 | 用途 |
| --- | --- |
| `chat/sessions/<session_id>/session.json` | Chat session 元数据。 |
| `chat/sessions/<session_id>/events.jsonl` | Chat session 消息事件，append-only 文件。 |
| `industry_chains/` | 产业链知识文件和索引，不属于 SQLite 表。 |
