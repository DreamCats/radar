"""Fixed job scheduling primitives."""

from radar.core.scheduler.defaults import DEFAULT_SCHEDULES, DefaultSchedule
from radar.core.scheduler.models import ScheduleRecord, ScheduleTickRecord, TickStatus
from radar.core.scheduler.planner import compute_next_tick_at, resolve_window_preset, scheduler_now
from radar.core.scheduler.storage import (
    create_schedule_tick,
    ensure_default_schedules,
    finish_schedule_tick,
    get_schedule,
    list_due_schedules,
    list_schedule_ticks,
    list_schedules,
    set_schedule_enabled,
    update_schedule_after_tick,
    update_schedule_request,
)

__all__ = [
    "DEFAULT_SCHEDULES",
    "DefaultSchedule",
    "ScheduleRecord",
    "ScheduleTickRecord",
    "TickStatus",
    "compute_next_tick_at",
    "create_schedule_tick",
    "ensure_default_schedules",
    "finish_schedule_tick",
    "get_schedule",
    "list_due_schedules",
    "list_schedule_ticks",
    "list_schedules",
    "resolve_window_preset",
    "scheduler_now",
    "set_schedule_enabled",
    "update_schedule_after_tick",
    "update_schedule_request",
]
