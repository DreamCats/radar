from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_CATALYST_VALUATION_REPORT_MAX_STOCKS = 20


@dataclass(frozen=True)
class DefaultSchedule:
    schedule_id: str
    job_key: str
    title: str
    cadence_kind: str
    cadence: dict[str, Any]
    request: dict[str, Any] = field(default_factory=dict)
    window_preset: str | None = None
    timezone: str = "Asia/Shanghai"
    catch_up_policy: str = "latest_only"
    max_lag_minutes: int = 60
    sort_order: int = 0
    enabled: bool = False


DEFAULT_SCHEDULES: tuple[DefaultSchedule, ...] = (
    DefaultSchedule(
        schedule_id="wechat-ingest-incremental",
        job_key="wechat_ingest",
        title="微信数据源增量",
        cadence_kind="interval",
        cadence={"minutes": 30, "offset_minutes": 0},
        window_preset="yesterday_1500_to_now",
        request={"source": "all", "force": False, "chunk_hours": 1, "concurrency": 4},
        sort_order=10,
    ),
    DefaultSchedule(
        schedule_id="analyst-backtest-close",
        job_key="analyst_backtest",
        title="分析师回测",
        cadence_kind="daily",
        cadence={"time": "15:40", "weekdays_only": True},
        request={
            "lookback_days": 40,
            "windows": [1, 3, 5],
            "source": "all",
            "cooldown_trade_days": 5,
            "benchmark_ts_code": "000300.SH",
            "remote_price_fetch": True,
        },
        max_lag_minutes=180,
        sort_order=20,
    ),
    DefaultSchedule(
        schedule_id="market-stock-refresh-morning",
        job_key="market_stock_refresh",
        title="市场主数据全量刷新",
        enabled=True,
        cadence_kind="daily",
        cadence={"time": "08:30", "weekdays_only": False},
        request={"force": True},
        max_lag_minutes=180,
        sort_order=15,
    ),
    DefaultSchedule(
        schedule_id="catalyst-valuation-report-hourly",
        job_key="catalyst_valuation_report",
        title="催化估值线索报告",
        cadence_kind="interval",
        cadence={"minutes": 60, "offset_minutes": 0, "active_start": "08:00", "active_end": "23:00"},
        window_preset="last_1h",
        request={
            "limit": 200,
            "max_stocks": DEFAULT_CATALYST_VALUATION_REPORT_MAX_STOCKS,
            "publish": True,
            "notify": False,
        },
        max_lag_minutes=60,
        sort_order=30,
    ),
)

RETIRED_SCHEDULE_IDS: tuple[str, ...] = (
    "message-classify-incremental",
    "market-anchor-close",
    "catalyst-strategy-hourly",
)

RETIRED_SCHEDULE_JOB_KEYS: tuple[str, ...] = (
    "message_classify",
    "market_anchor_update",
    "catalyst_strategy",
)
