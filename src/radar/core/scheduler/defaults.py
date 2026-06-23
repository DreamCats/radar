from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
        schedule_id="message-classify-incremental",
        job_key="message_classify",
        title="消息分类增量",
        cadence_kind="interval",
        cadence={"minutes": 30, "offset_minutes": 10},
        window_preset="yesterday_1500_to_now",
        request={
            "source": "all",
            "force": False,
            "chunk_hours": 1,
            "limit": 500,
            "batch_size": 16,
            "max_concurrency": 10,
            "low_confidence_threshold": 0.65,
        },
        sort_order=20,
    ),
    DefaultSchedule(
        schedule_id="market-anchor-close",
        job_key="market_anchor_update",
        title="Anchor 更新",
        cadence_kind="daily",
        cadence={"time": "15:20", "weekdays_only": True},
        request={"force": False, "min_anchor_count": 100},
        max_lag_minutes=180,
        sort_order=30,
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
            "min_classification_confidence": 0.7,
            "benchmark_ts_code": "000300.SH",
            "remote_price_fetch": True,
        },
        max_lag_minutes=180,
        sort_order=40,
    ),
)
