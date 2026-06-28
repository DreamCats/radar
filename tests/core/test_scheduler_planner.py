from __future__ import annotations

from datetime import datetime

from radar.core.scheduler.models import ScheduleRecord
from radar.core.scheduler.planner import compute_next_tick_at, resolve_window_preset


def test_interval_schedule_respects_active_window():
    schedule = _schedule(
        cadence={"minutes": 60, "offset_minutes": 0, "active_start": "08:00", "active_end": "22:00"}
    )

    assert compute_next_tick_at(schedule, datetime.fromisoformat("2026-06-28T07:30:00")) == datetime.fromisoformat(
        "2026-06-28T08:00:00"
    )
    assert compute_next_tick_at(schedule, datetime.fromisoformat("2026-06-28T20:39:00")) == datetime.fromisoformat(
        "2026-06-28T21:00:00"
    )
    assert compute_next_tick_at(schedule, datetime.fromisoformat("2026-06-28T21:30:00")) == datetime.fromisoformat(
        "2026-06-28T22:00:00"
    )
    assert compute_next_tick_at(schedule, datetime.fromisoformat("2026-06-28T22:01:00")) == datetime.fromisoformat(
        "2026-06-29T08:00:00"
    )


def test_last_1h_window_preset():
    start, end = resolve_window_preset("last_1h", datetime.fromisoformat("2026-06-28T20:39:00"))

    assert start == datetime.fromisoformat("2026-06-28T19:39:00")
    assert end == datetime.fromisoformat("2026-06-28T20:39:00")


def _schedule(cadence: dict[str, object]) -> ScheduleRecord:
    now = datetime.fromisoformat("2026-06-28T00:00:00")
    return ScheduleRecord(
        schedule_id="test",
        job_key="test",
        title="测试",
        enabled=True,
        timezone="Asia/Shanghai",
        cadence_kind="interval",
        cadence=cadence,
        catch_up_policy="latest_only",
        max_lag_minutes=60,
        created_at=now,
        updated_at=now,
    )
