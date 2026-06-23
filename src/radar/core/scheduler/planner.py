from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from radar.core.scheduler.models import ScheduleRecord

DEFAULT_ZONE = "Asia/Shanghai"


def scheduler_now(timezone_name: str = DEFAULT_ZONE) -> datetime:
    return datetime.now(ZoneInfo(timezone_name)).replace(tzinfo=None)


def compute_next_tick_at(schedule: ScheduleRecord, now: datetime | None = None) -> datetime:
    current = now or scheduler_now(schedule.timezone)
    if schedule.cadence_kind == "interval":
        return _next_interval_tick(schedule, current)
    if schedule.cadence_kind == "daily":
        return _next_daily_tick(schedule, current)
    raise ValueError(f"未知调度类型: {schedule.cadence_kind}")


def resolve_window_preset(preset: str | None, now: datetime | None = None) -> tuple[datetime | None, datetime | None]:
    if preset is None:
        return None, None
    current = now or scheduler_now()
    if preset == "yesterday_1500_to_now":
        return (current - timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0), current
    raise ValueError(f"未知时间窗口模板: {preset}")


def _next_interval_tick(schedule: ScheduleRecord, now: datetime) -> datetime:
    minutes = int(schedule.cadence.get("minutes") or 30)
    offset_minutes = int(schedule.cadence.get("offset_minutes") or 0)
    if minutes < 1:
        raise ValueError("interval minutes 必须大于 0")
    base = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=offset_minutes)
    if now < base:
        return base
    interval = timedelta(minutes=minutes)
    elapsed = int((now - base).total_seconds() // interval.total_seconds()) + 1
    return base + elapsed * interval


def _next_daily_tick(schedule: ScheduleRecord, now: datetime) -> datetime:
    tick_time = _parse_time(str(schedule.cadence.get("time") or "15:20"))
    weekdays_only = bool(schedule.cadence.get("weekdays_only", True))
    candidate = datetime.combine(now.date(), tick_time)
    if candidate <= now or (weekdays_only and candidate.weekday() >= 5):
        candidate += timedelta(days=1)
    while weekdays_only and candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _parse_time(value: str) -> time:
    try:
        hour, minute = value.split(":", 1)
        return time(hour=int(hour), minute=int(minute))
    except ValueError as exc:
        raise ValueError(f"时间格式应为 HH:MM: {value}") from exc
