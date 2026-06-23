# 定时作业设计

## 背景

当前离线作业都在 Web 的“作业中心”手动触发。作业类型已经固定，但手动点会带来两个问题：

- 固定窗口来不及点，错过有效数据同步或盘后整理。
- 想看结果时才触发，需要等待重作业跑完。

第一版目标不是做通用调度平台，而是把现有固定作业模板自动化，并且继续复用现有 `runs` 审计、去重和取消能力。

## 现状

前端固定了 6 类作业模板：

- 微信数据源：`wechat_ingest_range`
- 消息分类：`message_classify_range`
- Anchor 更新：`market_anchor_update`
- 分析师回测：`analyst_stock_mention_backtest_refresh`
- 个股证据链：`stock_evidence_chain`
- 机会生命周期摘要：`opportunity_lifecycle_digest`

这些作业已经走 Web API 提交，后端用线程池异步执行，并在 `runs` 表记录状态和 metadata。调度层应该只负责“什么时候提交哪个模板”，不重新实现作业逻辑。

## 设计原则

- 调度只编排，不承载业务逻辑。
- `runs` 仍是单次作业的事实来源。
- 新增 schedule/tick 表只记录调度计划和触发记录。
- 默认可暂停；任何任务必须能一键禁用。
- 同一计划到点时，如果同类目标已有 running run，复用或跳过，不重复堆积。
- 第一版不做 DAG/链路引擎；每个 schedule 独立触发，只通过窗口 preset 和 running 去重保持一致。
- 重作业要有限流，尤其是 LLM 和行情拉取相关作业。
- 后端重启后允许补最近一次漏跑，但不无限补历史。

## 后端结构

建议新增：

```text
src/radar/core/scheduler/
├── models.py       # ScheduleSpec / ScheduleTick 等核心模型
├── storage.py      # schedules / schedule_ticks 读写
├── defaults.py     # 第一版内置固定模板
└── planner.py      # next_run_at / due schedules / catch-up 计算

src/radar/web/server/routers/schedules.py
src/radar/web/server/scheduler.py      # 后端内置轮询循环
src/radar/web/server/schedule_jobs.py  # job_key -> 现有 submit_*_job 适配
```

`core/scheduler/` 不依赖 FastAPI，也不反向依赖 Web job submitter。由于现有异步 submitter 在 `web/server/*_jobs.py`，`schedule_jobs.py` 放在 Web 层做适配。

## SQLite 表

通过 message DB migration 追加：

```sql
CREATE TABLE IF NOT EXISTS job_schedules (
    schedule_id TEXT PRIMARY KEY,
    job_key TEXT NOT NULL,
    title TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    cadence_kind TEXT NOT NULL,
    cadence_json TEXT NOT NULL DEFAULT '{}',
    window_preset TEXT,
    request_json TEXT NOT NULL DEFAULT '{}',
    catch_up_policy TEXT NOT NULL DEFAULT 'latest_only',
    max_lag_minutes INTEGER NOT NULL DEFAULT 60,
    last_tick_at TEXT,
    next_tick_at TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_schedule_ticks (
    tick_id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL,
    planned_at TEXT NOT NULL,
    fired_at TEXT,
    status TEXT NOT NULL,
    run_ids_json TEXT NOT NULL DEFAULT '[]',
    request_json TEXT NOT NULL DEFAULT '{}',
    skipped_reason TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (schedule_id) REFERENCES job_schedules(schedule_id)
);
```

`job_schedule_ticks.status` 建议使用：

- `planned`
- `running`
- `submitted`
- `skipped`
- `failed`

真实执行成败仍看 `runs.status`。

## 调度执行流

```text
backend startup
  -> init_db
  -> start scheduler loop if config.scheduler.enabled
  -> every 30s:
       load enabled schedules due before now
       acquire scheduler lock
       build request from schedule preset
       call existing submit_*_job
       write tick with run_ids
       compute next_tick_at
```

锁建议先做进程内锁 + SQLite tick 唯一约束。当前个人工作台通常单后端进程；后续如果有多进程部署，再补 DB lease。

## 默认任务节奏

第一版可以内置模板，但默认不自动启用，由 Tab 里打开：

- 微信数据源增量：每 30 分钟，时间窗用“昨日 15:00 到当前时刻”，`force=false`。
- 消息分类增量：每 30 分钟，建议相对微信数据源延后 5-10 分钟；时间窗同样用“昨日 15:00 到当前时刻”，`force=false`，只补未分类。
- Anchor 更新：交易日 15:20 后独立触发。
- 分析师回测：交易日 15:30 或 15:40 独立触发。

微信数据源和消息分类保持独立 cron，不做硬依赖。两者都是增量作业：入库按 `message_id` 去重，分类默认补未分类；分类早跑最多少吃到刚入库的新消息，下一轮会补上。这样后续暂停、拆分、改频率都更简单。

个股证据链和生命周期摘要第一版不放入默认定时模板，只保留手动触发。后续如果发现等待仍明显，再考虑把个股证据链拆成轻量预扫和 LLM 重判，或单独加可选定时。

## Web API

新增：

- `GET /api/schedules`
- `POST /api/schedules/{schedule_id}/enable`
- `POST /api/schedules/{schedule_id}/disable`
- `POST /api/schedules/{schedule_id}/run-now`
- `GET /api/schedules/{schedule_id}/ticks`

`run-now` 也走同一套 Web 层 job adapter，并写一条 manual tick，避免“手动”和“自动”两套历史。

## UI Tab

新增一级 Tab：`定时`。

页面布局建议：

- 左侧：固定计划列表，显示启用状态、下一次运行、最近一次结果。
- 中间：计划详情，允许改时间、时间窗、force、并发等少量参数。
- 右侧：最近 tick + 对应 run 卡片，复用现有 `JobRunCard`。

重要操作：

- 启用 / 暂停
- 立即运行
- 查看最近一次 run
- 查看漏跑 / 跳过原因

## 分阶段落地

1. 后端 schema + scheduler core + API，只支持固定内置计划。
2. Web 增加 `定时` Tab，先做启停、立即运行、最近历史。
3. 接入后端生命周期，dashboard 启动时自动轮询。
4. 再补可编辑计划和更细粒度的失败/漏跑提醒。

## 风险

- 如果 dashboard 后端没有常驻，Web 内置调度不会触发。当前先接受这个约束；需要更稳时再加 `radar scheduler` CLI 或系统 launchd。
- LLM 重作业可能排队，第一版必须依赖现有 running run 去重，不能到点就新增。
- 远端如果是 preview/public 部署，要确认实际启动脚本是否常驻后端；否则 Tab 能显示计划，但不会真实自动触发。
