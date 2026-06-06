# 02 · 老项目调研：stock-news (sn)

> 给老板做的项目。仓库：`~/Work/tools/cli/stock-news`（GitHub: DreamCats/stock-news）
> 定位：投研信息流 CLI，从微信消息采集 → LLM 分类/抽取 → 观点链归并 → 行情回测 → 盘中策略快报。
> **人和 Agent 都能用。**

调研目的：搞清楚老项目做了什么、做得好不好，决定 radar 哪些复用、哪些避坑、哪些做差异化。

## 技术栈

- **语言/工具链**：Python 3.10+ / `uv` / `hatchling` 打包
- **CLI**：`click` 8.x，入口 `sn`
- **数据校验**：`pydantic` 2.x
- **HTTP**：`httpx`
- **LLM**：`openai`（任意 OpenAI 兼容接口，支持按任务路由 provider）
- **行情**：`tushare` + `efinance`，SQLite 本地缓存
- **配置**：`pyyaml`
- **质量**：`ruff` + `mypy --strict` + `pytest`

## 目录结构

```
src/stock_news/
├── cli.py                  # 入口
├── models.py               # RawMessage / ClassifiedMessage / Recommendation 等核心模型
├── common/
│   ├── config.py           # 配置加载（高频被调用的核心）
│   ├── wechat_api.py       # 微信 API 客户端（数据源入口）
│   ├── storage.py          # 消息落盘/加载
│   ├── llm/                # LLM 封装 + 多 provider 路由
│   ├── delivery/           # 投递（飞书 / 企业微信 webhook）
│   ├── market/             # 行情（tushare/efinance + SQLite 缓存）
│   └── scheduler/          # launchd 定时调度（10min tick）
├── source/                 # 「源头雷达」——本项目的精华，见下
│   ├── seeds.py            # as-of 源头种子扫描（成熟锚点+陌生组合）
│   ├── models.py           # SourceSeedCandidate 等评分模型
│   └── storage.py
└── commands/               # 各子命令：fetch/analyze/strategy/workflow/...
```

## 全链路能力（命令一览）

```
fetch        微信消息采集（按 source/时间窗增量）
backfill     历史补齐，按日 fetch→classify→extract→opinion
data         查询/统计/去重
analyze      classify(分类) / extract(推荐抽取) / opinion(观点链归并) / backtest(回测)
strategy     盘中策略快报（json + md + xlsx）
source       源头雷达：extract(结构抽取) + scan(as-of 冷启动扫描)
workflow     盘中编排：fetch→classify→extract→opinion→backtest→strategy→delivery
delivery     投递渠道（飞书 / 企业微信群机器人 webhook）
llm          多 provider 管理 + 按任务路由
market       行情数据（tushare token / 股票列表 / 日线）
config       配置管理
schedule     launchd 定时（10min tick + job 日志）
```

数据沉淀目录：`~/.config/stock-news/data/<date>/{raw,classified,extracted,opinions,strategy,backtest,source_extract,source_scan,workflow}/`

## 精华：source/ 源头雷达

老项目最有「思想」的部分，**很可能正是个人版最想要的**。

核心思路（来自 `source/seeds.py` + `models.py`）：
- **「成熟锚点 + 陌生组合」**：识别一个已知概念（anchor）被一个新修饰/新方向（novel）组合，
  如 `A化B` / `prefix-anchor` / `modifier-anchor` / `anchor-extension`。
- **as-of 证据计算**（0 token，纯本地历史索引）：
  - 这个组合在历史里冷不冷（`prior_*_mentions`）
  - 现在是不是还早（`earliness_score`）
  - 截至 as_of，是否已经在多个群/多个发送人接力（`asof_groups/senders`、`followup_*`）
  - 是否已映射到具体个股（`mapped_stocks`）
- **多维打分**：`novelty_strength` / `earliness_score` / `askability_score` / `trade_potential_score`
- 两阶段：`extract`（低频，调 LLM 切结构）+ `scan`（0 token，本地 as-of 计算）

> 这套「抢早、抢新概念」的逻辑对个人投资者价值很高——但实现偏重。radar 可以借鉴**思想**，
> 用更轻的方式实现，或者直接作为差异化重点打磨。

## 借鉴 vs 避坑（对 radar 的判断）

### ✅ 可直接复用 / 借鉴
- 微信 API 拉取逻辑（极简）
- RawMessage 数据模型与 message_id 去重
- 「源头雷达」的核心思想（成熟锚点+陌生组合、as-of 早期信号）
- LLM 多 provider + 按任务路由的设计
- 投递（飞书/企业微信 webhook）如果个人版要推送

### ⚠️ 对个人版可能过重 / 不必照搬
- 全链路 pipeline（backfill / workflow 编排 / launchd 调度）——个人版按需即可
- 回测 + Tushare 行情体系——除非个人版要做胜率复盘，否则是大工程
- 策略快报 xlsx 投递——面向「发给别人看」的场景，个人自用未必需要
- 「人+Agent 通用」的通用性负担——个人版可以更专、更硬编码我的偏好

### 🚫 必须避免
- **不要直接 fork 改名** → 只会得到一个更烂的 stock-news
- **不要共用数据目录** → radar 独立落盘，与公司项目隔离
- **不要追求大而全** → 个人版的核心竞争力是「专」和「降噪」

## 待与本人确认的判断
- radar 是否要复用「源头雷达」作为核心卖点？
- 是否需要行情/回测？（决定要不要引入 Tushare 这一大块）
- 是否需要推送投递？还是只要一个本地看板？

_最后更新：2026-06-03_
