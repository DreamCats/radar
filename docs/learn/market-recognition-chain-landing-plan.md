# 市场认可链落地方案

本文专门回答一个问题：

```text
如果要优化个股证据链里的“市场认可”，到底靠什么数据和工程手段落地？
```

先说结论：

```text
不要一上来做大模型打标签。
第一版应该做“证据槽位 + 可解释规则 + 缺口提示”。
```

也就是说，radar 不应该假装已经知道机构认不认可。

它应该先把证据摆出来：

- 哪些证据已经有。
- 哪些证据缺失。
- 哪些只能叫 unknown。
- 哪些结论可以由规则保守判断。
- 哪些结论必须等后续数据源补齐。

## 当前个股证据链的真实瑕疵

当前个股证据链主要是：

```text
消息侧证据链
```

它能比较好地回答：

- 谁在讲这只股票。
- 讲的是什么类型的证据。
- 消息是否扩散。
- LLM 认为它处在哪个阶段。
- 证据窗口内股价有没有涨跌。

但它还不能稳定回答：

- 政策是否顺风。
- 它是不是当前市场主线。
- 机构有没有认可。
- 同板块核心票是不是更强。
- 价格是刚开始确认，还是已经涨完。
- 为什么市场不认。

所以优化目标不是再堆一个“认可度模型”。

优化目标应该是：

```text
把消息证据链扩展成“消息 + 政策 + 板块 + 资金 + 定价 + 反证”的多层证据链。
```

## 认可链的四个层次

### 1. 政策认可

问题：

```text
这条叙事是不是当前政策主航道？
```

第一版不能靠模型自动猜。

也不应该先靠人工维护政策主题词表。

第一版先把政策字段显示为 `unknown`，只保留可审计的候选主题；后续如果能接入稳定政策来源，再做自动映射。

示例：

| 政策主题 | 关键词 | 说明 |
| --- | --- | --- |
| 新质生产力 | 人工智能、机器人、集成电路、低空经济、未来能源、量子、6G | 当前政策高频方向 |
| 稳增长 | 基建、设备更新、城市更新、地产链 | 偏宏观托底和投资链 |
| 稳股市 | 券商、保险、宽基 ETF、长期资金 | 偏风险偏好和资本市场改革 |
| 反内卷 | 光伏、锂电、化工、钢铁、水泥等供给治理 | 不一定利好所有公司，重点看产能出清 |
| 自主可控 | 半导体设备、材料、工业软件、信创 | 重点看客户验证和订单 |

暂不落地：

```text
policy_theme_tags.yaml
```

先不要让 LLM 或人工文件直接决定政策顺风。

LLM 可以做候选建议，但最终字段必须来自可自动更新、可审计的数据源。

### 2. 产业认可

问题：

```text
政策支持的方向，能不能传导到这家公司利润表？
```

第一版可以从消息里抽证据，但要明确这是“产业证据”，不是市场认可。

可用证据：

- 订单。
- 中标。
- 涨价。
- 缺货。
- 产能利用率。
- 客户验证。
- 量产。
- 业绩上修。
- 毛利率修复。

当前 radar 已有 `matcher.py` 里的证据家族能力，可以继续复用：

- `catalyst`
- `roadshow`
- `research`
- `push`
- `price`

但建议新增更细的产业证据标签：

| 新标签 | 例子 | 价值 |
| --- | --- | --- |
| `order` | 订单、中标、锁单 | 最硬 |
| `price_up` | 涨价、提价、缺货 | 硬 |
| `capacity` | 满产、排产、扩产 | 中等 |
| `customer_validation` | 验证、导入、认证 | 中等 |
| `earnings_revision` | 业绩上修、利润弹性 | 最接近兑现 |
| `theme_only` | 只是在讲概念 | 最弱 |

### 3. 机构认可

问题：

```text
其他机构和资金有没有一起确认？
```

这层最难，也是当前最不能乱打标签的地方。

短期可以拆成两个部分：

```text
消息里的机构行为
市场里的资金行为
```

#### 消息里的机构行为

当前可以从微信消息里近似判断：

- 是否有多个研究员/券商/分析师重复覆盖。
- 是否有路演、反路演、1v1、电话会。
- 是否有调研纪要密集出现。
- 是否有“强推”“继续推荐”“金股”等表达。
- 是否多会话、多发送人扩散。

这只能叫：

```text
机构讨论热度
```

不能直接叫：

```text
机构认可
```

#### 市场里的资金行为

当前 radar 代码里已经有一部分 Tushare 能力，但还没接入个股证据链：

| 能力 | 当前代码位置 | 用途 |
| --- | --- | --- |
| 个股日线 | `stock_evidence_chain/market.py` | 已接入，用于涨幅、回撤、成交额 |
| 个股资金流 | `core/tushare/market_data.py:get_stock_moneyflow` | 可用于主力净流入、资金强弱，但未接入证据链 |
| 板块资金流 | `core/tushare/market_data.py:get_sector_moneyflow` | 可用于主题/行业是否有资金流入，但未接入证据链 |
| 涨停池 | `core/tushare/market_data.py:get_limit_pool` | 可用于情绪强弱，但未接入证据链 |
| 龙虎榜 | `core/tushare/market_data.py:get_billboard_trading` | 可用于机构席位确认，但未接入证据链 |
| 指数日线 | `core/tushare/history.py:index_daily/sw_daily/ci_daily` | 可用于个股相对行业强弱，但未接入证据链 |
| 每日基本面 | `core/tushare/history.py:daily_basic` | 可用于换手率、估值、量能，但未接入证据链 |

所以 P0 不是“创造数据”，而是把已经存在的 Tushare 能力接进证据链。

### 4. 市场定价

问题：

```text
市场是否已经用价格表达认可？
```

当前已有个股日线，可以先做保守规则。

建议第一版字段：

| 字段 | 计算方式 |
| --- | --- |
| `return_5d` | 近 5 个交易日涨幅 |
| `return_20d` | 近 20 个交易日涨幅 |
| `amount_ratio_5d` | 当日成交额 / 过去 5 日均值 |
| `drawdown_from_20d_high` | 从 20 日高点回撤 |
| `relative_return_vs_index` | 个股涨幅 - 行业或主题指数涨幅 |
| `relative_rank_in_theme` | 在同主题股票里的强弱排序 |

第一版不需要预测涨跌。

只判断状态：

| 状态 | 规则示例 |
| --- | --- |
| 不认 | 消息强，但 5/20 日弱于板块，成交额没有放大 |
| 刚确认 | 放量上涨，且强于行业，但涨幅还不大 |
| 强确认 | 持续强于行业，成交额放大，多日趋势上行 |
| 已过热 | 短期涨幅过大，成交额极度放大，回撤风险高 |
| 定价后回撤 | 曾强确认，但从高点明显回撤 |

## P0 详细落地方案

P0 的目标不是“算准认可度”。

P0 的目标是：

```text
让用户少花时间去外面补证据。
```

### P0-1：先用 Tushare/market_anchors 做主题归属，不做自动主题模型

前面说“人工维护 `stock_theme_map.yaml`”，这个方案过保守，维护成本也高。

```text
第一优先级应该是复用 Tushare 概念/行业/题材主数据。
第一版不做人工维护文件，也不做人工作业纠偏。
```

当前 radar 其实已经有这条数据线：

| 数据 | 当前位置 | 说明 |
| --- | --- | --- |
| 市场 anchor | `market.sqlite3:market_anchors` | 概念、行业、题材锚点 |
| 股票成员 | `market.sqlite3:market_anchor_members` | 股票属于哪些概念/行业/题材 |
| 拉取代码 | `src/radar/core/market/anchors.py` | 刷新和兜底逻辑 |
| 数据源适配 | `src/radar/core/market/anchor_sources.py` | 当前接入东财概念、KPL、通达信概念 |

Tushare 侧也有可用接口：

- 东财概念列表和成分：`dc_concept`、`dc_concept_cons`。
- 同花顺概念和行业：`ths_index`、`ths_member`、`ths_daily`。
- 申万行业分类和成分：`index_classify`、`index_member_all`。
- 指数行情：`index_daily`、`sw_daily`、`ci_daily`。

所以 P0-1 应该改成：

```text
Tushare/market_anchors 自动归属
-> 多源合并
-> 覆盖率检查
-> 缺失和歧义只进入报告，不要求人工维护
```

为什么先不做人工纠偏：

- 人工维护成本会随着主题和股票数量持续上升。
- 当前目标是先降低外部找证据的时间，不是保证每个主题语义完美。
- 自动数据源能覆盖多数股票，缺失和歧义应该先变成产品报告。
- 主叙事和角色先用多源数量、持续天数、最新交易日做保守自动判断，不把它伪装成确定结论。

第一版验收不应该是“人工覆盖 50 个案例”，而应该是：

```text
自动主题覆盖率 >= 80%
缺失股票进入待补数据列表
多主题股票能展示所有候选主题
主叙事只在自动高置信时给候选，否则显示 unknown
```

### P0-2：接入主题内相对强弱

有了 `market_anchor_members` 的自动主题归属后，才能算：

```text
这只股票在同主题里强不强？
```

计算方式：

1. 对每个主题取同组股票。
2. 拉每只股票近 5/20 日日线。
3. 计算涨幅、成交额放大、回撤。
4. 给出主题内排名。

输出字段：

```text
theme_return_rank_5d
theme_return_rank_20d
theme_amount_rank_5d
is_theme_leader
is_theme_laggard
```

这样可以解释：

```text
消息很多，但它不是主题里最强的票。
```

这比单看个股涨幅更接近机构视角。

### P0-3：接入行业/指数相对强弱

当前 `history.py` 已支持：

- `index_daily`
- `sw_daily`
- `ci_daily`

但证据链没有用。

落地方式：

1. 先给主题手工绑定一个基准指数。
2. 没有精确指数时，用宽基或主题内等权组合作为近似。
3. 计算个股相对指数收益。

输出字段：

```text
benchmark_code
relative_return_5d
relative_return_20d
relative_amount_signal
```

这能回答：

```text
它涨，是因为全板块都涨，还是它自己更强？
```

### P0-4：接入资金和情绪证据

优先级从低风险到高风险：

| 优先级 | 数据 | 作用 | 风险 |
| --- | --- | --- | --- |
| 1 | 成交额放大 | 判断市场是否开始关注 | 已有，最稳 |
| 2 | 个股资金流 | 看主力资金强弱 | 字段口径要核对 |
| 3 | 板块资金流 | 看主题是否被资金认可 | 主题归属要先做好 |
| 4 | 涨停池 | 看短线情绪 | 容易偏游资，不等于机构 |
| 5 | 龙虎榜机构席位 | 看是否有机构席位参与 | 只覆盖上榜股票，样本偏 |

第一版建议只把 1 和 2 做进评分。

3、4、5 先只展示，不参与强结论。

### P0-5：规则引擎，不是模型

第一版用规则生成状态。

不要叫 `score_model`。

可以叫：

```text
recognition_rules_v1
```

示例规则：

```text
market_confirmation = just_confirmed
if:
  return_5d > 5%
  and amount_ratio_5d > 1.5
  and relative_return_5d > 3%
  and drawdown_from_20d_high > -8%
```

```text
market_rejection_reason includes "消息强但市场不认"
if:
  unique_trigger_count >= 7
  and return_20d < 0
  and relative_return_20d < 0
```

```text
priced_risk = high
if:
  return_20d > 30%
  or return_since_first_evidence > 50%
```

```text
institution_confirmation = unknown
if:
  no moneyflow
  and no sector_moneyflow
  and no top_inst
```

最重要的是：

```text
缺数据时输出 unknown，不要脑补。
```

### P0-6：详情页改成证据缺口面板

不要只展示一句：

```text
机构认可度：弱
```

应该展示：

| 维度 | 状态 | 证据 | 缺口 |
| --- | --- | --- | --- |
| 政策顺风 | unknown | 暂无自动政策映射 | 等稳定政策数据源 |
| 产业兑现 | 中 | 有调研和催化，但订单证据弱 | 缺订单/业绩 |
| 机构讨论 | 强 | 多研报、多路演、多会话扩散 | 缺买方确认 |
| 市场确认 | 弱 | 成交未放大，弱于主题 | 等量能 |
| 定价风险 | 低 | 涨幅不大 | 等价格确认 |

这能让用户一眼知道：

```text
不是故事不行，而是缺哪一块证据。
```

## 数据表建议

### `theme_nodes`

自动主题节点。

| 字段 | 含义 |
| --- | --- |
| `theme_id` | 自动生成的稳定主题 ID |
| `theme_name` | 主题名 |
| `theme_type` | theme / concept / industry |
| `aliases_json` | 多源名称别名 |
| `policy_strength` | strong / medium / weak |
| `source` | manual / doc / imported |
| `updated_at` | 更新时间 |

### `stock_theme_members`

维护股票和主题关系。

| 字段 | 含义 |
| --- | --- |
| `ts_code` | 股票代码 |
| `stock_name` | 股票名 |
| `theme_id` | 主题 ID |
| `role` | core / elastic / follower / noise / old_consensus |
| `confidence` | 0-1 |
| `source` | manual / llm_candidate / imported |
| `updated_at` | 更新时间 |

### `stock_recognition_snapshots`

每天保存认可链快照。

| 字段 | 含义 |
| --- | --- |
| `as_of_time` | 快照时间 |
| `ts_code` | 股票代码 |
| `theme_id` | 主题 ID |
| `policy_alignment` | strong / medium / weak / unknown |
| `industry_confirmation` | none / weak / medium / strong / unknown |
| `institution_discussion` | none / weak / medium / strong |
| `market_confirmation` | rejected / early / confirmed / overheated / pullback / unknown |
| `pricing_state` | underpriced / pricing / priced / crowded / unknown |
| `rejection_reasons_json` | 市场不认原因 |
| `missing_evidence_json` | 缺口 |
| `features_json` | 计算特征 |
| `rules_version` | 规则版本 |
| `created_at` | 创建时间 |

## API 建议

新增接口：

```text
GET /api/strategy/stocks/{ts_code}/recognition
GET /api/strategy/themes/{theme_id}/recognition
GET /api/strategy/recognition/snapshots/latest
```

前端先不做复杂页面。

先在个股抽屉里加一个“市场认可链”区块。

## UI 建议

第一版只做一个紧凑面板：

```text
市场认可链

政策顺风：强
主题角色：AI 算力 / 光通信 / 核心
产业兑现：中，缺订单和业绩
机构讨论：强，多研报和路演
市场确认：刚确认，5 日强于主题，成交额 1.8x
定价风险：中，20 日涨幅 18%
主要缺口：缺买方资金确认、缺订单兑现
```

这个面板的目标是：

```text
减少用户去外面查证据的时间。
```

不是替用户做买卖结论。

## 分阶段实施

### 第 1 阶段：零新增外部数据

第一阶段不建议做成独立大项目。

它更像一个基础特征层，可以并到第二阶段一起做。

原因：

```text
当前个股证据链已经有日线、成交额、涨幅、回撤。
但还没有把这些产出成“市场确认/不认/过热/回撤”的结构化快照。
```

所以第一阶段的真实产出不是新数据源，而是：

```text
stock_recognition_features_v0
```

它只做三件事：

- 从现有日线和成交额计算基础市场特征。
- 用规则判断市场确认状态。
- 把缺失证据明确标成 unknown。

只用现有数据：

- 微信消息。
- 消息分类。
- 股票提及。
- LLM 阶段。
- 个股日线。
- 成交额。

能做：

- 市场确认初筛。
- 定价程度。
- 消息强但市场不认。
- 定价后回撤。
- 证据缺口面板。

不能做：

- 真正机构认可。
- 板块资金确认。
- 主题内强弱。
- 政策顺风自动判断。

### 第 2 阶段：自动主题主数据，不做人工纠偏

第二阶段才是“主题归属”真正开始有用的地方。

新增：

- 复用 `market_anchors`。
- 复用 `market_anchor_members`。
- 增加主题归一化表。
- 增加覆盖率和歧义报告。

能做：

- 政策顺风度。
- 主题角色。
- 主题内相对强弱。
- 更清楚地解释“不是主线核心”。

不能做：

- 自动发现新主题。
- 自动判断政策变化。
- 自动判断股票在叙事里的真实地位。

#### 第二阶段产出是什么

第二阶段至少产出 4 个东西。

| 产出 | 作用 |
| --- | --- |
| 主题归一化表 | 把东财、KPL、通达信、同花顺、申万里的同义主题合并成稳定 ID |
| 原始主题到归一主题映射 | 保留“这个主题来自哪个数据源、原始名称是什么、原始代码是什么” |
| 股票-主题归属表 | 让每只股票能查到属于哪些归一主题 |
| 覆盖率和歧义报告 | 告诉我们哪些股票没有主题、哪些股票主题太多、哪些只能显示 unknown |

一句话：

```text
第二阶段不是做模型，而是把“股票属于什么主题”这件事做成稳定、可查询、可回放的自动主数据。
```

#### 为什么要做主题归一化

现在 `market_anchors` 是原始市场 anchor。

它的问题是：

- 同一个主题，多个源叫法不同。
- 同一个概念，每个交易日都会有一份快照。
- 同一只股票可能挂在很多概念下面，用户不知道哪个是当前主叙事。
- 原始概念不等于政策主题，例如“AI硬件”需要归到“人工智能+ / 新质生产力”。
- 主题内强弱必须先有稳定分组，否则无法比较。

举例：

```text
KPL: AI硬件
东财: CPO 概念
同花顺: 光通信
通达信: 算力概念
```

这些可能都跟同一条市场主线有关：

```text
AI 算力 / 光通信
```

如果不归一化，系统会把它们当成几条孤立主题。

结果就是：

```text
天孚通信在 AI硬件里很强；
但系统不知道它也是光通信/算力主线的一部分。
```

归一化后才能回答：

```text
这只股票是不是主题核心？
同主题里谁更强？
它涨是自己强，还是整个主题强？
```

#### 表会不会变大

会增加表，但不会失控。

当前原始表已经比较大：

```text
market_anchors: 约 4.1 万行
market_anchor_members: 约 22.4 万行
单日 market_anchor_members: 约 5 千到 6 千行
```

第二阶段新增的是“归一化层”，不是把原始数据复制很多遍。

推荐结构：

```text
原始每日快照：market_anchors / market_anchor_members
稳定主题维表：theme_nodes
原始主题映射：theme_source_links
股票主题关系：stock_theme_memberships
```

数据量预估：

| 表 | 量级 | 是否会快速变大 |
| --- | --- | --- |
| `theme_nodes` | 几百到几千行 | 不会 |
| `theme_source_links` | 几千到几万行 | 慢增长 |
| `stock_theme_memberships` | 几万到几十万行 | 可控 |
| 原始 `market_anchor_members` | 每年百万级 | 已经存在，属于原始快照 |

关键设计是：

```text
归一化层尽量用 first_seen_date / last_seen_date，不每天复制一遍。
```

只有后续需要复盘“某一天主题成分变化”时，才单独做 daily snapshot。

#### 建议表结构

`theme_nodes`：稳定主题表。

```sql
CREATE TABLE theme_nodes (
  theme_id TEXT PRIMARY KEY,
  theme_name TEXT NOT NULL,
  theme_type TEXT NOT NULL,       -- theme / concept / industry
  parent_theme_id TEXT,
  aliases_json TEXT NOT NULL DEFAULT '[]',
  policy_tags_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

例子：

| theme_id | theme_name | theme_type | parent_theme_id | policy_tags_json |
| --- | --- | --- | --- | --- |
| `theme:auto:...` | AI硬件 | theme |  | `[]` |
| `theme:auto:...` | CPO概念 | concept |  | `[]` |
| `theme:auto:...` | 光通信设备 | industry |  | `[]` |

`theme_source_links`：原始主题到归一主题的映射。

```sql
CREATE TABLE theme_source_links (
  theme_id TEXT NOT NULL,
  source TEXT NOT NULL,
  source_code TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_anchor_type TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  first_seen_date TEXT NOT NULL,
  last_seen_date TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (source, source_code, source_anchor_type, theme_id)
);
```

例子：

| theme_id | source | source_code | source_name | confidence |
| --- | --- | --- | --- | --- |
| `theme:auto:...` | `kpl_list` | `AI硬件` | AI硬件 | 1.0 |
| `theme:auto:...` | `dc_concept` | `BKxxxx` | CPO 概念 | 1.0 |
| `theme:auto:...` | `dc_concept_cons` | `通信设备` | 通信设备 | 1.0 |

`stock_theme_memberships`：股票和归一主题关系。

```sql
CREATE TABLE stock_theme_memberships (
  theme_id TEXT NOT NULL,
  ts_code TEXT NOT NULL,
  stock_name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'unknown',  -- core / elastic / unknown
  confidence REAL NOT NULL DEFAULT 0.5,
  source_count INTEGER NOT NULL DEFAULT 0,
  sources_json TEXT NOT NULL DEFAULT '[]',
  reasons_json TEXT NOT NULL DEFAULT '[]',
  first_seen_date TEXT NOT NULL,
  last_seen_date TEXT NOT NULL,
  latest_trade_date TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (theme_id, ts_code)
);
```

例子：

| theme_id | ts_code | stock_name | role | source_count | reasons_json |
| --- | --- | --- | --- | ---: | --- |
| `theme:auto:...` | `300394.SZ` | 天孚通信 | elastic | 2 | `["dc_concept:CPO概念: 光模块", "kpl_list:AI硬件"]` |
| `theme:auto:...` | `002812.SZ` | 恩捷股份 | unknown | 1 | `["dc_concept:锂电池"]` |

#### 第二阶段的最小验收

第一版不要追求全市场完美。

验收标准可以这样定：

1. 50 个案例里，自动主题覆盖率达到 80% 以上。
2. 未覆盖的股票进入“待补数据列表”。
3. 一只股票能展示所有主题候选，而不是只展示一个标签。
4. 只能在自动高置信时给当前主叙事候选，否则明确显示 unknown。
5. 能按主题拉出成员股，计算主题内 5 日 / 20 日强弱。
6. 个股详情页能解释：

```text
这只股票属于哪些主题；
当前主叙事是哪条；
它在主题里强不强；
主题归属来自哪个数据源；
自动置信度和缺口是什么。
```

### 第 3 阶段：接入资金和行业数据

接入当前已有但未产品化的 Tushare 能力：

- 个股资金流。
- 板块资金流。
- 行业/指数日线。
- 每日基本面。
- 涨停池。
- 龙虎榜。

能做：

- 市场认可更强验证。
- 行业共振。
- 机构席位辅助判断。
- 资金流反证。

仍然不能做：

- 确定机构真实持仓意图。
- 预测后续一定上涨。

### 第 4 阶段：再考虑模型

模型只能做三件事：

1. 从原始消息中抽候选主题。
2. 解释证据缺口。
3. 生成可读摘要。

模型不应该直接决定：

- 政策是否顺风。
- 机构是否认可。
- 是否可以买。

这些必须由结构化证据和规则支撑。

## 验收标准

P0 完成不看“模型准不准”，看这几件事：

1. 每只股票详情页能显示“消息证据”和“市场认可证据”的区别。
2. 缺数据时明确显示 unknown，不编结论。
3. 对 50 个案例能自动标出至少三类：
   - 消息强但市场不认。
   - 市场刚确认。
   - 已充分定价或定价后回撤。
4. 对已有自动主题归属的股票，能显示主题内强弱。
5. 用户看到一只股票后，至少少查 3 类外部资料：
   - 同板块谁更强。
   - 成交额有没有放大。
   - 价格是不是已经涨完。

## 最后结论

当前不是“缺一个更聪明的模型”。

当前缺的是：

```text
把认可这件事拆成可验证的数据槽位。
```

第一版要保守：

```text
有证据就说有。
没证据就说 unknown。
证据冲突就说冲突。
```

这样 radar 才能真正提高效率，而不是把一个更漂亮但不可靠的结论展示给用户。
