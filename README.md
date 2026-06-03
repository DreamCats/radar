# radar

个人投研工作台。当前阶段先把微信个人消息 / 个人群数据源接入到独立 SQLite，提供 CLI 写入、查询、硬过滤和去重能力；Web 看板和信号雷达后续再迭代。

## 当前能力

- 从微信 API 拉取 `个人消息` / `个人群`。
- 按时间切片并发拉取，串行写入 SQLite。
- 用 `message_id` 去重，避免重复窗口写入重复消息。
- 用 `fetch_windows` 记录已处理窗口，并支持被更大窗口覆盖时跳过拉取。
- 入库前按群名黑名单过滤明显非投研群。
- 支持来源、群名、时间、关键词筛选和游标分页查询。

## 技术栈

- Python 3.10+
- uv
- click
- pydantic v2
- SQLite + FTS5
- FastAPI / React 预留，当前还未落 Web 实现

## 目录

```text
src/radar/
├── core/
│   ├── config.py              # config.yaml + secrets.yaml 加载
│   ├── fetch.py               # 微信 API 拉取和标准化
│   ├── filtering.py           # 硬过滤规则
│   ├── models.py              # pydantic 数据模型
│   ├── query.py               # SQLite 查询和分页
│   ├── store.py               # SQLite schema、去重、窗口缓存
│   └── usecases/
│       └── ingest_wechat.py   # 拉取窗口编排
└── cli/
    ├── main.py                # CLI 入口和命令注册
    ├── context.py             # CLI 公共配置/时间解析
    ├── ingest.py              # 写入命令
    └── query.py               # 查询命令
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
```

```yaml
# ~/.config/radar/secrets.yaml
wechat:
  endpoints:
    wechat_main:
      base_url: https://example.invalid/wechat
```

也可以临时覆盖：

```bash
RADAR_CONFIG_DIR=/path/to/config uv run radar doctor
RADAR_DATA_DIR=/path/to/data uv run radar query --limit 5
RADAR_WECHAT_BASE_URL=https://example.invalid/wechat uv run radar doctor
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

如果输出里带下一页游标，直接复制继续翻页：

```bash
uv run radar query --cursor-time "2026-06-03T10:00:00" --cursor-id "message-id" --limit 20
```

## 本地数据

默认数据库：

```text
~/.config/radar/data/radar.sqlite3
```

核心表：

- `messages`：标准化消息主表。
- `messages_fts`：FTS5 全文搜索表。
- `fetch_windows`：已处理拉取窗口缓存表。

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
