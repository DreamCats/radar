# radar

个人投研工作台。当前阶段先把微信个人消息 / 个人群数据源接入到独立 SQLite，提供 CLI 写入、查询、硬过滤、去重和最薄 Web dashboard 骨架；信号雷达后续再迭代。

## 当前能力

- 从微信 API 拉取 `个人消息` / `个人群`。
- 按时间切片并发拉取，串行写入 SQLite。
- 用 `message_id` 去重，避免重复窗口写入重复消息。
- 用 `fetch_windows` 记录已处理窗口，并支持被更大窗口覆盖时跳过拉取。
- 用 `schema_migrations` 记录 SQLite 版本，支持老库随代码升级补表/索引。
- 用 `runs` 记录 ingest 执行状态、数量摘要和错误摘要。
- 入库前按群名黑名单过滤明显非投研群。
- 支持来源、群名、时间、关键词筛选和游标分页查询。
- 预置 OpenAI-compatible / Anthropic Messages 两类 LLM 协议客户端，供后续分类和信号分析复用。
- 预置 Tushare Pro 核心客户端，支持 HTTP 调用、短期 KV 缓存、低风险历史行缓存和股票代码解析。
- 提供 `radar test` 烟测命令，方便在终端验证 core 能力是否跑通。
- 提供 `radar dashboard` 启动本地 Web API，前端骨架在 `web/ui`。

## 技术栈

- Python 3.10+
- uv
- click
- pydantic v2
- SQLite + FTS5
- FastAPI
- React 19 + Vite + TypeScript + Tailwind

## 目录

```text
src/radar/
├── cli/
│   ├── main.py                # CLI 入口和命令注册
│   ├── context.py             # CLI 公共配置/时间解析
│   ├── dashboard.py           # dashboard 后端启动命令
│   ├── ingest.py              # 写入命令
│   ├── query.py               # 查询命令
│   └── test.py                # core 能力烟测命令
├── core/
│   ├── config.py              # config.yaml + secrets.yaml 加载
│   ├── db.py                  # SQLite migration 和 schema 版本
│   ├── fetch.py               # 微信 API 拉取和标准化
│   ├── filtering.py           # 硬过滤规则
│   ├── llm/                   # LLM provider 解析和协议客户端
│   ├── messages/              # 消息和会话查询分页
│   ├── models.py              # pydantic 数据模型
│   ├── runs.py                # core 执行审计记录
│   ├── store.py               # SQLite schema、去重、窗口缓存
│   ├── tushare/               # Tushare provider、缓存、历史数据和股票解析
│   └── usecases/              # 跨模块编排，classification/ 放消息分类
└── web/server/
    ├── app.py                 # FastAPI app 创建
    ├── deps.py                # Web 依赖注入
    └── routers/               # health/messages/runs/ingest API

web/ui/
└── src/
    ├── api/                   # HTTP 调用封装
    ├── components/            # 纯展示和表单组件
    ├── lib/                   # 无业务依赖的小函数
    ├── pages/                 # 页面状态和交互
    ├── App.tsx                # 顶层页面切换
    ├── main.tsx               # React 挂载入口
    └── types.ts               # Web DTO 类型
```

## 配置

默认读取：

```text
~/.config/radar/config.yaml
~/.config/radar/secrets.yaml
```

`secrets.yaml` 放敏感信息，不提交到 git。微信 API 的 `base_url` 属于敏感入口，只能放在本机配置或环境变量里。

最小结构示例：

```yaml
# ~/.config/radar/config.yaml
storage:
  data_dir: ~/.config/radar/data
  # 可选；不配置时默认是 ~/.config/radar/data/reports.sqlite3。
  reports_database: ~/.config/radar/data/reports.sqlite3
  # 可选；不配置时默认是 ~/.config/radar/data/valuation.sqlite3。
  valuation_database: ~/.config/radar/data/valuation.sqlite3

wechat:
  timeout: 30
  sources:
    personal_message:
      name: 个人消息
      endpoint: wechat_main
    group_message:
      name: 个人群
      endpoint: wechat_main

filters:
  group_blacklist_patterns:
    - 小学
    - 作业

market:
  provider: tushare
  secret_ref: tushare_main
  api_url: http://api.tushare.pro
  timeout: 30
  database: ~/.config/radar/data/market.sqlite3

chat:
  skills:
    enabled: true
    # 仓库内置 src/radar/core/skills 会始终加载；用户目录适合本机草稿。
    # 默认用户目录是 ~/.config/radar/skills；只有显式配置时才会扫描其他目录。
    paths:
      - skills
    max_active: 3
  shell:
    enabled: true
    shell_path: /bin/zsh
    # shell 工具会用 zsh -lic 执行命令，默认加载用户 .zshrc 环境。
    default_cwd: ~/Work/invest/projects/radar
    timeout_seconds: 30
    max_output_chars: 12000

web:
  auth:
    # 个人部署时开启；未开启时 dashboard 保持免登录。
    enabled: true
```

`market.api_url` 可以填 Tushare 直连地址，也可以填远端代理地址；兼容旧配置名 `market.tushare_api_url`。

Chat skills 默认从 `~/.config/radar/skills/*/SKILL.md` 读取。每轮只把 `name + description` 作为轻量目录注入 prompt；需要完整说明时，模型会调用 `radar_load_skill` 读取对应 `SKILL.md` 正文。全局 `~/.agents/skills` 不会默认加载，如需复用必须显式加入 `chat.skills.paths`。

```markdown
---
name: market_research
description: 股票行情研究
---
如果用户没有提供股票名，先追问具体标的。
```

如果 skill 目录下还有 `references/` 或其他辅助文档，`radar_load_skill` 会返回可读文件清单；模型需要细节时再用 `radar_read_skill_reference` 按相对路径读取，避免一次性把长文档塞进上下文。

内置 shell 工具名是 `radar_run_shell`。它会在本机执行命令，并默认通过 `zsh -lic` 注入 `.zshrc` 里的环境变量，供需要本地 CLI 的 skill 使用。

```yaml
# ~/.config/radar/secrets.yaml
wechat:
  endpoints:
    wechat_main:
      base_url: https://example.invalid/wechat
market:
  tushare_main:
    token: YOUR_TUSHARE_TOKEN
web:
  auth:
    token: CHANGE_ME
```

也可以临时覆盖：

```bash
RADAR_CONFIG_DIR=/path/to/config uv run radar doctor
RADAR_DATA_DIR=/path/to/data uv run radar query --limit 5
RADAR_WECHAT_BASE_URL=https://example.invalid/wechat uv run radar doctor
RADAR_TUSHARE_TOKEN=YOUR_TUSHARE_TOKEN uv run radar doctor
RADAR_WEB_AUTH_TOKEN=CHANGE_ME uv run radar dashboard
RADAR_REPORTS_DATABASE=/path/to/reports.sqlite3 uv run radar dashboard
```

## 常用命令

检查 CLI：

```bash
uv run radar doctor
```

拉取并写入一天数据：

```bash
uv run radar ingest wechat --source all --start "2026-06-03" --end "2026-06-04"
```

默认行为：

- `--source all` 会依次处理 `personal_message` 和 `group_message`。
- `--chunk-hours 1`：按 1 小时切片。
- `--concurrency 4`：每个 source 最多 4 个窗口并发拉取。
- SQLite 写入仍是串行，避免并发写锁。
- 已处理窗口会跳过；如果已有整天窗口，也会覆盖命中小时切片。
- 输出中的 `run_id` 可用于定位本次执行在 `runs` 表里的审计记录。

更温和地拉取：

```bash
uv run radar ingest wechat \
  --source all \
  --start "2026-06-03" \
  --end "2026-06-04" \
  --chunk-hours 2 \
  --concurrency 2
```

查询消息：

```bash
uv run radar query --source group_message --start "2026-06-03" --end "2026-06-04" --limit 20
uv run radar query --keyword "固态" --limit 20
uv run radar query --keyword "固态" --format json --limit 5
```

测试 core 能力：

```bash
uv run radar test market
uv run radar test market --date 20260603 --no-cache
uv run radar test llm
```

启动 Web dashboard：

```bash
uv run radar dashboard
```

该命令会在同一个终端里启动 FastAPI 和 Vite。页面默认打开 `http://127.0.0.1:5173`，API 默认监听 `http://127.0.0.1:8000`。停止时直接按 `Ctrl+C`，命令会同时停止两个子进程。

后台管理 dashboard：

```bash
scripts/dashboard start
scripts/dashboard status
scripts/dashboard restart
scripts/dashboard stop
```

脚本会把 PID 和日志写到 `.runtime/dashboard/`。如需改端口，把参数透传给 `radar dashboard`：

```bash
scripts/dashboard start -- --port 8001 --ui-port 5174
```

如需改端口：

```bash
uv run radar dashboard --port 8001 --ui-port 5174
```

催化估值线索报告会归档到独立 `reports.sqlite3`，dashboard 的“估值线索”tab 可回看每次生成的结构化数据和 HTML，并可手动发送 Bark。默认定时流程只归档、发布 HTML 并触发异步空间测算，不再发送第一阶段报告简报 Bark；空间测算 chat run 完成后会投影到独立 `valuation.sqlite3`，有正向空间标的时会先发布一份包含结构化表格和完整 session Markdown 的估值测算 HTML，再按定时任务的“测算 Bark”开关发送结构化 Bark，Bark 点击 URL 指向这份测算报告。开启 `web.auth.enabled` 后，外部 API 也使用同一个固定 token：

```bash
curl -H "Authorization: Bearer $RADAR_WEB_AUTH_TOKEN" \
  "http://127.0.0.1:8000/api/external/catalyst-valuation-reports?granularity_minutes=60&limit=20"
```

详情接口返回 `report` 结构化数据、`rendered_html` 和上传后的 `published_url`：

```bash
curl -H "Authorization: Bearer $RADAR_WEB_AUTH_TOKEN" \
  "http://127.0.0.1:8000/api/external/catalyst-valuation-reports/<report_id>"
```

如果输出里带下一页游标，直接复制继续翻页：

```bash
uv run radar query --cursor-time "2026-06-03T10:00:00" --cursor-id "message-id" --limit 20
```

## 本地数据

默认数据库：

```text
~/.config/radar/data/radar.sqlite3
~/.config/radar/data/market.sqlite3
~/.config/radar/data/reports.sqlite3
~/.config/radar/data/valuation.sqlite3
```

消息库 `radar.sqlite3`：

- `schema_migrations`：消息库 schema 版本记录。
- `messages`：标准化消息主表。
- `messages_fts`：FTS5 全文搜索表。
- `fetch_windows`：已处理拉取窗口缓存表。
- `runs`：ingest 执行审计表。

行情库 `market.sqlite3`：

- `schema_migrations`：行情库 schema 版本记录。
- `tushare_cache`：Tushare 短期 KV 缓存表。
- `tushare_history`：Tushare 低风险历史行缓存表。

报告库 `reports.sqlite3`：

- `schema_migrations`：报告库 schema 版本记录。
- `catalyst_valuation_reports`：催化估值线索报告归档，包含窗口、HTML、上传 URL 和结构化 report JSON。
- `report_notifications`：手动 Bark 等报告通知记录。

估值测算库 `valuation.sqlite3`：

- `schema_migrations`：估值测算库 schema 版本记录。
- `valuation_measurements`：异步空间测算完成后的结构化投影，保存来源 report/run/session、解析状态、正向标的数量、测算 HTML 发布 URL 和结构化 Bark 通知状态。
- `valuation_measurement_items`：空间测算总表的逐标的结构化行。

`stored=0` 不一定表示没有拉到数据；它通常表示拉回来的消息已经按 `message_id` 去重存在。`skipped>0` 才表示窗口缓存命中，没有请求 API。

## 开发验证

```bash
uv run --with pytest pytest -q
uv run --with ruff ruff check .
```

`.venv/` 是 uv 项目虚拟环境，保留在本地即可，已被 `.gitignore` 忽略。

## 相关文档

- [docs/00-README.md](docs/00-README.md)
- [docs/01-data-source.md](docs/01-data-source.md)
- [docs/05-tech-stack.md](docs/05-tech-stack.md)
- [docs/07-data-volume-constraints.md](docs/07-data-volume-constraints.md)
- [AGENTS.md](AGENTS.md)
