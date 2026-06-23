from __future__ import annotations

from datetime import datetime, timedelta
from threading import Event, Lock, Thread
from typing import Callable

from radar.core.config import RadarConfig
from radar.core.scheduler import (
    ScheduleRecord,
    ScheduleTickRecord,
    compute_next_tick_at,
    create_schedule_tick,
    ensure_default_schedules,
    finish_schedule_tick,
    list_due_schedules,
    scheduler_now,
    update_schedule_after_tick,
)
from radar.web.server.schedule_jobs import (
    has_running_scheduled_job,
    mark_stale_scheduled_runs,
    prepare_schedule_job,
    submit_prepared_schedule_job,
)


class SchedulerLoop:
    def __init__(self, config: RadarConfig, *, now_fn: Callable[[], datetime] | None = None) -> None:
        self.config = config
        self.now_fn = now_fn or scheduler_now
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = Lock()

    def start(self) -> None:
        if not self.config.scheduler.enabled or self._thread is not None:
            return
        ensure_default_schedules(self.config.database_path, now=self.now_fn())
        self._thread = Thread(target=self._run, name="radar-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        interval = self.config.scheduler.poll_interval_seconds
        while not self._stop.wait(interval):
            tick_due_schedules(self.config, now=self.now_fn(), lock=self._lock)


def tick_due_schedules(
    config: RadarConfig,
    *,
    now: datetime | None = None,
    lock: Lock | None = None,
) -> list[ScheduleTickRecord]:
    current = now or scheduler_now()
    ensure_default_schedules(config.database_path, now=current)
    guard = lock or Lock()
    if not guard.acquire(blocking=False):
        return []
    try:
        return [trigger_schedule(config, schedule, now=current) for schedule in list_due_schedules(config.database_path, now=current)]
    finally:
        guard.release()


def trigger_schedule(config: RadarConfig, schedule: ScheduleRecord, *, now: datetime | None = None) -> ScheduleTickRecord:
    current = now or scheduler_now(schedule.timezone)
    planned_at = schedule.next_tick_at or current
    tick = create_schedule_tick(
        config.database_path,
        schedule_id=schedule.schedule_id,
        planned_at=planned_at,
        request={},
        now=current,
    )
    try:
        if _missed_window(schedule, planned_at, current):
            return _finish_and_advance(
                config,
                schedule,
                tick.tick_id,
                now=current,
                status="skipped",
                skipped_reason="missed_max_lag",
            )
        prepared = prepare_schedule_job(schedule, now=current)
        mark_stale_scheduled_runs(config, schedule)
        if has_running_scheduled_job(config, schedule):
            return _finish_and_advance(
                config,
                schedule,
                tick.tick_id,
                now=current,
                status="skipped",
                request=prepared.request_payload,
                skipped_reason="previous_tick_running",
            )
        submitted = submit_prepared_schedule_job(config, schedule, prepared)
        return _finish_and_advance(
            config,
            schedule,
            tick.tick_id,
            now=current,
            status="submitted",
            run_ids=submitted.run_ids,
            request=prepared.request_payload,
            skipped_reason="reused_existing" if submitted.reused_existing else None,
        )
    except BaseException as exc:
        return _finish_and_advance(
            config,
            schedule,
            tick.tick_id,
            now=current,
            status="failed",
            error_message=str(exc)[:1000],
        )


def run_schedule_now(config: RadarConfig, schedule: ScheduleRecord, *, now: datetime | None = None) -> ScheduleTickRecord:
    current = now or scheduler_now(schedule.timezone)
    prepared = prepare_schedule_job(schedule, now=current)
    tick = create_schedule_tick(
        config.database_path,
        schedule_id=schedule.schedule_id,
        planned_at=current,
        request=prepared.request_payload,
        now=current,
    )
    try:
        mark_stale_scheduled_runs(config, schedule)
        if has_running_scheduled_job(config, schedule):
            finished = finish_schedule_tick(
                config.database_path,
                tick.tick_id,
                status="skipped",
                request=prepared.request_payload,
                skipped_reason="previous_tick_running",
                now=current,
            )
        else:
            submitted = submit_prepared_schedule_job(config, schedule, prepared)
            finished = finish_schedule_tick(
                config.database_path,
                tick.tick_id,
                status="submitted",
                run_ids=submitted.run_ids,
                request=prepared.request_payload,
                skipped_reason="reused_existing" if submitted.reused_existing else None,
                now=current,
            )
    except BaseException as exc:
        finished = finish_schedule_tick(
            config.database_path,
            tick.tick_id,
            status="failed",
            request=prepared.request_payload,
            error_message=str(exc)[:1000],
            now=current,
        )
    if finished is None:
        raise RuntimeError(f"调度 tick 不存在: {tick.tick_id}")
    return finished


def _finish_and_advance(
    config: RadarConfig,
    schedule: ScheduleRecord,
    tick_id: str,
    *,
    now: datetime,
    status,
    run_ids: list[str] | None = None,
    request: dict | None = None,
    skipped_reason: str | None = None,
    error_message: str | None = None,
) -> ScheduleTickRecord:
    tick = finish_schedule_tick(
        config.database_path,
        tick_id,
        status=status,
        run_ids=run_ids,
        skipped_reason=skipped_reason,
        error_message=error_message,
        request=request,
        now=now,
    )
    next_tick = compute_next_tick_at(schedule, now)
    update_schedule_after_tick(config.database_path, schedule, last_tick_at=now, next_tick_at=next_tick)
    if tick is None:
        raise RuntimeError(f"调度 tick 不存在: {tick_id}")
    return tick


def _missed_window(schedule: ScheduleRecord, planned_at: datetime, now: datetime) -> bool:
    return now - planned_at > timedelta(minutes=schedule.max_lag_minutes)
