# Tushare 5000 积分账号接口实测清单

> 实测时间：2026-06-30  
> 账号：5000 积分 Tushare Pro 账号  
> 验证工具：`~/Work/tools/cli/tushare-cli`（强制跳过缓存 `--no-cache`）  
> 测试日期：2025-06-10（历史）/ 2026-06-29（概念列表）

## 结论速览

- **历史/日频数据**：5000 积分可覆盖本项目 90% 以上需求。
- **盘中实时**：唯一真实时接口 `rt_k` **不可用**（需单独开通权限）。
- **涨停池/龙虎榜**：`limit_list_d`、`top_list`、`top_inst` 可用；`limit_step`、`limit_strongest` 不可用。
- **热股排行**：`ths_hot`、`dc_hot` 不可用。
- **概念板块**：`ths_index`/`ths_member`、`dc_concept`/`dc_member` 均可用。

---

## ✅ 已验证可用（5000 积分）

| 接口 | 项目使用位置 | 实测结果 | 备注 |
|---|---|---|---|
| `stock_basic` | `core/tushare/stock_master.py` | ✅ | 股票主数据 |
| `trade_cal` | `core/usecases/analyst_mentions/pricing.py` | ✅ | 交易日历 |
| `daily` | `core/tushare/history.py`、`core/chat/tushare_tools.py` | ✅ | 个股日线 |
| `daily_basic` | `core/tushare/history.py` | ✅ | 每日估值指标 |
| `adj_factor` | `core/tushare/history.py` | ✅ | 复权因子 |
| `moneyflow` | `core/tushare/market_data.py` | ✅ | Tushare 官方个股资金流 |
| `moneyflow_dc` | `core/tushare/market_data.py` | ✅ | 东财个股资金流 |
| `moneyflow_ths` | `core/tushare/market_data.py` | ✅ | 同花顺个股资金流 |
| `moneyflow_ind_dc` | `core/tushare/market_data.py` | ✅ | 东财行业/板块资金流（552 条） |
| `moneyflow_ind_ths` | `core/tushare/market_data.py` | ✅ | 同花顺行业资金流（90 条） |
| `stk_factor` | `core/tushare/market_data.py` | ✅ | 技术因子（MACD/KDJ/RSI/BOLL 等） |
| `stk_limit` | `core/tushare/market_data.py` | ✅ | 每日涨跌停价 |
| `top_list` | `core/tushare/market_data.py` | ✅ | 龙虎榜每日明细（81 条） |
| `top_inst` | `core/tushare/market_data.py` | ✅ | 龙虎榜机构交易明细（920 条） |
| `limit_list_d` | `core/tushare/market_data.py` | ✅ | 涨跌停和炸板池（77 条） |
| `ths_index` | `core/usecases/premarket_signal/concepts.py` | ✅ | 同花顺概念列表（1725 条） |
| `ths_member` | `core/usecases/premarket_signal/concepts.py` | ✅ | 同花顺概念成分股 |
| `dc_concept` | `core/usecases/premarket_signal/concepts.py` | ✅ | 东财概念列表（5000 条） |
| `dc_member` | `core/usecases/premarket_signal/concepts.py` | ✅ | 东财概念成分股 |
| `index_daily` | `core/tushare/history.py` | ✅ | 指数日线 |
| `index_global` | `core/tushare/history.py` | ✅ | 国际指数日线 |
| `sw_daily` | `core/tushare/history.py` | ✅ | 申万行业日线 |
| `index_dailybasic` | `core/tushare/history.py` | ✅ | 指数每日指标 |
| `fund_nav` | `core/tushare/history.py` | ✅ | 基金净值 |
| `cn_cpi` / 宏观类 | `core/tushare/history.py` | ✅ | 中国宏观月/季频 |
| `ci_daily` | `core/tushare/history.py` | ⚠️ API 通，返回 0 条 | 代码格式待确认，权限无问题 |

---

## ❌ 已验证不可用（5000 积分）

| 接口 | 项目使用位置 | 实测结果 | 说明 |
|---|---|---|---|
| `rt_k` | `core/tushare/realtime.py` | ❌ 权限不足 | **唯一真盘中实时接口**，需单独开通（约 200 元/月） |
| `limit_step` | `core/tushare/market_data.py` | ❌ 权限不足 | 连板天梯，5000 积分不够 |
| `limit_strongest` | `core/tushare/market_data.py` | ❌ “请指定正确的接口名” | Tushare 不认该接口名，可能是项目写错或接口已下线 |
| `ths_hot` | `core/tushare/cache.py`（有 TTL，未实际调用） | ❌ 权限不足 | 同花顺热股排行 |
| `dc_hot` | `core/tushare/cache.py`（有 TTL，未实际调用） | ❌ 权限不足 | 东财热股排行 |

---

## 对 radar 项目的影响

### 1. 回测与历史分析

完全可用。5000 积分足够支撑：

- 分析师提及回测（`daily` + `index_daily`）
- 估值报告（`daily`/`daily_basic`/`adj_factor`）
- 资金流分析（`moneyflow*`）
- 概念板块映射（`ths_index`/`ths_member`/`dc_concept`/`dc_member`）

### 2. 盘中/实时能力

**基本为 0**。项目里唯一设计为盘中的 `rt_k` 在该账号下无法调用。其他短 TTL 接口（如 `limit_list_d`、`top_list`、`moneyflow_ind_*`）虽然项目缓存策略允许盘中查询，但 Tushare 数据本身是**日终更新**，盘中查到的是昨日数据或空。

### 3. 需要修复/注意的点

- **`limit_strongest` 接口异常**：`src/radar/core/tushare/market_data.py` 中注册了该接口，但 Tushare 返回“请指定正确的接口名”。建议确认该接口是否仍然有效。
- **`limit_step` 需要更高积分**：如果盘前信号或涨停梯队功能需要该接口，需升级账号。

---

## 升级建议

| 需求 | 最低成本路径 |
|---|---|
| 只要历史回测/日频分析 | **当前 5000 积分已足够** |
| 需要盘中实时快照 | 单独开通 `rt_k` 权限（约 200 元/月） |
| 需要连板天梯 `limit_step` | 提升积分档位或确认是否含在更高积分档 |
| 需要热股排行 `ths_hot`/`dc_hot` | 提升积分档位 |

---

## 复现命令

```bash
cd ~/Work/tools/cli/tushare-cli

# 历史/日频
uv run tushare --json --no-cache bar daily 600519.SH --start 20250610 --end 20250610
uv run tushare --json --no-cache flow stock --ts-code 600519.SH --trade-date 20250610
uv run tushare --json --no-cache tops daily --trade-date 20250610
uv run tushare --json --no-cache concept ths-list

# 盘中/实时（预期失败）
uv run python - << 'PY'
from tushare_cli.common.client import call
call("rt_k", {"ts_code": "600519.SH"}, cache_ttl=0)
PY
```
