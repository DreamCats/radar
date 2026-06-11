# AGENTS.md

本文件约束 coding agent 在 radar 仓库内的工作方式。优先保证代码分层清楚、实现简单、可验证，不追求一次性做完整平台。

## 1. 项目快照

- radar 是个人投研工作台，复用微信个人消息/个人群数据源，但服务个人关注面。
- 当前仓库仍处于早期阶段；core/CLI 骨架已建立，Web dashboard 已有最薄 API/UI 骨架。
- 已定技术栈：Python 3.10+、uv、click、pydantic v2、SQLite、FastAPI + uvicorn、React 19 + Vite + TypeScript + Tailwind。
- 第一阶段先做原数据看板和硬降噪：拉取、标准化、去重、入库、窗口缓存、查询、筛选。
- `core/llm/` 只提供 OpenAI-compatible / Anthropic Messages 协议客户端；LLM 分类、信号雷达、行情回测、推送都属于后续阶段，未明确要求时不要提前实现。
- `core/tushare/` 只提供 Tushare Pro 协议客户端、缓存、低风险历史行缓存和股票代码解析；行情分析、策略、回测仍属于后续 usecase。
- `core/market/` 放市场 anchor、来源适配和主题归一化规则；它消费 `core/tushare/` 能力，但不承载策略回测或消息 usecase。

## 2. 开始前先读

按需阅读这些文件，不要凭空设计：

- `docs/archive/05-tech-stack.md`：技术栈和“共享数据核 + 双门面”架构。
- `docs/archive/01-data-source.md`：微信 API、原始字段、RawMessage 结构、去重要求。
- `docs/archive/07-data-volume-constraints.md`：单日 3000+ 消息、分页、虚拟滚动、FTS5 约束。
- `docs/archive/04-open-questions.md`：已决策和待决策范围。
- `docs/strategy/README.md`：机会信号策略的目标、问题、思路和后续策略讨论原则。
- `DESIGN.md`：Web UI 视觉规范。
- `demo/`：静态布局参考，不是业务实现。

## 3. 目标架构

坚持“共享 core + 双门面”：

```text
src/radar/
├── core/          业务核心，CLI 和 Web 共用
│   ├── models.py     pydantic 数据模型
│   ├── fetch.py      微信 API 拉取和原始字段标准化
│   ├── filtering.py  硬过滤规则
│   ├── storage/      SQLite migration、写入、执行审计、视图缓存
│   ├── messages/     消息筛选、分页、搜索、会话列表
│   ├── llm/          LLM provider 解析和协议客户端
│   ├── tushare/      Tushare provider、HTTP、缓存、历史行存、股票解析
│   ├── market/       市场 anchor、来源适配、主题归一化
│   ├── config.py     本地配置和数据目录
│   └── usecases/     跨 fetch/storage/filtering 的业务编排
├── cli/           click 命令，只调用 core/usecases
└── web/server/    FastAPI 接口，只调用 core

web/ui/            React/Vite 前端，只调用 Web API
```

如果实际落地目录与上面不同，先更新本文件或相关文档，再继续扩展。

## 4. 分层规则

- `core/` 是唯一业务真相来源；CLI 和 Web 后端都只能编排 core，不允许复制业务逻辑。
- `core/` 不依赖 click、FastAPI、React、浏览器概念。
- `core/usecases/` 放跨模块编排，例如分片拉取、过滤、写库、窗口记录；底层 SQL 仍留在 `core/storage/`。
- `core/usecases/classification/` 放消息分类 usecase、范围编排和 prompt；不要放进 `core/llm/`。
- `core/messages/` 放消息和会话的分页查询模型；CLI/Web 从这里取查询能力。
- `core/llm/` 只放 provider 解析、协议请求、JSON 解析等通用能力；prompt、任务语义和分类规则应放在后续 usecase。
- `core/tushare/` 不依赖 tushare-cli 的独立配置、click、formatter 或安装脚本；配置统一走 radar 的 `market` 和 `secrets.market`。
- `core/market/` 只放市场 anchor、来源适配、主题归一化规则和派生表刷新；策略解释、信号排序、review 仍留在对应 usecase。
- Tushare API 地址使用 `market.api_url`；为兼容 stock-news 旧配置，可接受 `market.tushare_api_url` 作为别名。
- Tushare 历史行缓存只纳入一维时间序列接口；有额外维度且主键无法表达的接口先走短期 KV，避免本地缓存覆盖。
- CLI 只负责参数解析、输出格式、退出码，不直接写 SQL、不直接请求微信 API。
- CLI 子命令按职责拆到 `src/radar/cli/` 独立模块，`main.py` 只保留入口和注册。
- Web 后端只负责 HTTP 入参/出参、错误码、调用 core，不直接拼业务查询。
- Web 前端不保存业务规则，只做展示、筛选控件、分页加载、交互状态。
- Web 前端按 `api/`、`pages/`、`components/`、`lib/`、`types.ts` 分层；页面负责状态和交互，组件负责展示，API 层负责 HTTP。
- 新增 Web 功能时先判断放在哪一层，不要继续往 `main.tsx` 或单个大页面里堆逻辑。
- SQLite 表结构、索引、FTS5、去重逻辑集中在 `core/storage/` 和 `core/messages/`，不散落到接口层。
- SQLite schema 变更必须通过 `core/storage/db.py` migration 追加版本，不直接改已落地表结构。
- `core/storage/runs.py` 只记录执行审计摘要和脱敏 metadata，不存真实消息内容或敏感 token。

## 5. 数据和隐私边界

- 不要污染或依赖 `~/.config/stock-news/data` 作为 radar 的运行数据目录；只能作为只读调研参考。
- radar 必须使用独立数据目录，默认倾向 `~/.config/radar/`，除非用户另行指定。
- 消息库和行情库必须分开：默认 `radar.sqlite3` 放消息，`market.sqlite3` 放 Tushare/market 缓存。
- 消息库可保存消息 ingest 相关执行审计；market 执行审计后续按需要再落到 market 或独立 ops 库。
- 微信 API 的 `base_url` 等入口信息视为敏感配置，不写入代码、文档、测试快照或 git。
- 原始消息属于个人数据；不要把真实全量内容写进 fixtures、日志、截图或提交说明。
- 日志只记录必要摘要，例如数量、时间窗、来源类型、错误类型。

## 6. 数据量约束

- 单日个人消息 + 个人群可能有 3000+ 条；历史可能几十万到百万级。
- API 查询必须分页或游标化，不能默认返回全量。
- 微信拉取允许按时间切片并发 fetch，但 SQLite 写入保持串行，避免写锁竞争。
- `fetch_windows` 是拉取窗口缓存；判断重复时要支持“已有大窗口覆盖小窗口”，不能只看完全相同 start/end。
- Web 列表必须按分页/虚拟滚动设计，不能一次渲染全量。
- SQLite 至少考虑这些索引：`message_id` 唯一、`message_time`、`group_name`、`source`。
- 全文搜索优先用 SQLite FTS5；不要用 Python 遍历全库做搜索。

## 7. 代码约束

- 单个源文件不允许超过 500 行；超过 400 行时先评估拆分。
- 每个模块保持单一职责；不要创建“万能 util”或大杂烩 service。
- 优先写直白代码，不要为了未来功能抽象复杂框架。
- 只在真实重复、真实复杂度出现后再抽象。
- 函数应该短小，入参和返回值清晰，避免隐藏全局状态。
- 新增配置必须有默认值或清晰错误信息。
- 错误处理要可定位：包含时间窗、source、group_name、message_id 等安全上下文。

## 8. 中文注释和命名

- 关键业务注释使用中文，尤其是数据标准化、去重、分页、FTS5、白名单过滤。
- 注释解释“为什么这样做”，不要写“把 A 赋给 B”这种无效注释。
- Python 变量、函数、类名仍使用英文，保持生态一致。
- 面向用户的 CLI/Web 文案优先中文，短句、直接、可操作。

## 9. 阶段边界

阶段一只做硬能力：

- 微信数据拉取。
- 中文字段标准化为 pydantic 模型。
- message_id 去重。
- SQLite 入库和查询。
- 群/来源/时间/关键词筛选。
- CLI 验证命令。
- 最薄 Web API 和原数据看板。

阶段一不要做：

- LLM 分类。
- 源头雷达评分。
- 行情回测。
- 自动推送。
- 多用户权限系统。
- 复杂任务编排和调度平台。

## 10. 常见改动路径

- 改数据模型：先看 `docs/archive/01-data-source.md`，再改 `src/radar/core/models.py`，同步 storage/messages 和测试。
- 改拉取逻辑：先改 `src/radar/core/fetch.py`，CLI/Web 不应直接变化。
- 改入库或索引：改 `src/radar/core/storage/store.py`；改 schema 时同步 `src/radar/core/storage/db.py` 并说明迁移策略。
- 改查询筛选：改 `src/radar/core/messages/query.py` 或 `src/radar/core/messages/conversations.py`，同时覆盖 CLI 输出和 Web API。
- 加 CLI 命令：在 `src/radar/cli/` 添加薄封装，复用 core。
- 加 Web API：在 `src/radar/web/server/` 添加路由，复用 core 查询模型。
- 改 UI：先读 `DESIGN.md` 和 `demo/`，保持暗色、信息密度、分页/虚拟滚动约束。

## 11. 命令规范

- 本机 shell 命令默认使用 `rtk` 前缀，例如 `rtk git status --short`。
- 轻量发现优先：`rtk rg`、`rtk find`、`rtk sed -n`、`rtk git status --short`。
- 不要在未说明原因时运行安装、构建、全量测试、长时间回填或网络拉取。
- 不要清理 `.venv/`；它是 uv 项目虚拟环境，已由 `.gitignore` 忽略。测试后只清 `.pytest_cache` 和 `__pycache__`。
- 不要执行破坏性 git 命令，例如 `git reset --hard`、`git checkout --`、强制清理文件。
- 任何会真实拉取个人消息、写入大量本地数据、发送通知的命令，都需要用户明确确认。

## 12. 验证要求

- 小改动优先跑最小相关验证；没有测试时至少运行 import/CLI smoke 或静态检查。
- 涉及 SQLite schema、查询、分页、去重时，必须用小样本覆盖关键路径。
- 涉及 Web 前端时，默认不要启动本地服务或做浏览器验证；优先用类型检查、构建、lint 或局部单测验证。只有用户明确要求浏览器验证，或改动涉及高风险首屏布局/复杂交互且已先说明收益与耗时，才允许使用浏览器。
- 不要声称测试通过，除非实际运行过对应命令。
- 如果跳过测试/构建，在最终回复中明确说明原因。

## 13. Market anchor 后续 TODO

- `market_anchor_current_members` 和 `market_anchor_member_spans` 当前允许全量重建；当前本机 22 万级 `market_anchor_members` 实测约 5 秒，不要为了提前优化牺牲正确性。
- 当派生表重建超过 30 秒，或 `market_anchor_members` 超过 100 万行时，优先把全量重建改成正确的增量刷新。
- 正确增量必须在替换某个交易日/source 的 raw 数据前后分别收集受影响的 `(anchor_key, member_source, ts_code)`，用旧 key 和新 key 的并集删除并重算派生行，避免成员删除、force 刷新、补历史数据时留下旧关系。
- 增量刷新必须补小样本测试，至少覆盖新增成员、删除成员、主题热度/reason 更新、历史日回填和 skipped raw 但重建派生表的场景。
- 主题归一化规则只作为“主线识别辅助”，不是业务真相；新增规则必须保守，宁可保留“补主题”，不要把弱关联包装成主线。
- 新增或放宽主题规则时，必须固定当前最新个股证据链样本做 before/after：至少记录 `primary_theme_missing`、`theme_missing`、`mainline_confirmed`，并人工抽看 Top 20 和变更样本。
- 主题规则不能只看关键词命中；尤其是 `AI硬件`、`半导体`、`芯片`、`涨价概念`、`专用设备`、`通用设备` 这类泛标签要默认降权，只有 reason 中出现足够具体的投资叙事时才允许派生更细主题。
- 如果指标变好但样本出现明显错归类，例如把公司边缘业务、客户描述或单句 reason 强行映射成主线，应优先收紧规则并补回归测试。
- 主题质量、市场认可和 review 标签是联动的；改 `core/market/theme_rules.py`、`theme_quality.py`、`recognition.py` 后，至少跑主题归一化、主题质量、review、排序和 web strategy 相关最小测试。

## 14. 保护已有改动

- 工作区可能有用户或其他 agent 的未提交改动；编辑前先看 `git status --short`。
- 不要回滚自己没改的文件。
- 如果同一文件已有不相关修改，保留它们，只做当前任务需要的最小 patch。
- 发现文档与代码不一致时，先以代码和用户最新要求为准，并指出差异。

## 15. 最终回复

最终回复保持简洁，至少包含：

- 改了哪些文件。
- 关键行为或规范变化。
- 做了什么验证。
- 未验证的部分和原因。
