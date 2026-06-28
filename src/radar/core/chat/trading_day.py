from __future__ import annotations

from datetime import date
from typing import Any

from radar.core.config import RadarConfig
from radar.core.tushare import call


def build_trading_day_prompt(config: RadarConfig, *, today: date | None = None) -> str:
    status = today_trading_day_status(config, today=today)
    if status is None:
        return "今日 A 股交易日状态：未知"
    return f"今日是否 A 股交易日：{'是' if status else '否'}"


def today_trading_day_status(config: RadarConfig, *, today: date | None = None) -> bool | None:
    target = today or date.today()
    try:
        rows = call(
            config,
            "trade_cal",
            params={
                "exchange": "SSE",
                "start_date": target.strftime("%Y%m%d"),
                "end_date": target.strftime("%Y%m%d"),
            },
            fields="cal_date,is_open",
            cache_ttl=3600,
        )
    except Exception:
        # 交易日只是 prompt 辅助上下文；Tushare 配置、网络或缓存异常都不应阻断聊天。
        return None
    if not rows:
        return None
    return _is_open(rows[0].get("is_open"))


def _is_open(value: Any) -> bool:
    return str(value).strip() in {"1", "1.0", "True", "true"}
