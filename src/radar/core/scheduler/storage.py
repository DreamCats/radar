from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from radar.core.scheduler.defaults import (
    DEFAULT_SCHEDULES,
    RETIRED_SCHEDULE_IDS,
    RETIRED_SCHEDULE_JOB_KEYS,
)
from radar.core.scheduler.models import ScheduleRecord, ScheduleTickRecord, TickStatus
from radar.core.scheduler.planner import compute_next_tick_at, scheduler_now
from radar.core.storage.db import configure_sqlite_connection, migrate_message_db

_SQLITE_TIMEOUT_SECONDS = 15.0
_SQLITE_BUSY_TIMEOUT_MS = 15_000


def ensure_default_schedules(database: Path, *, now: datetime | None = None) -> None:
    current = now or scheduler_now()
    current_text = current.isoformat()
    with _connect(database) as conn:
        _delete_retired_schedules(conn)
        for schedule in DEFAULT_SCHEDULES:
            existing = conn.execute(
                "SELECT * FROM job_schedules WHERE schedule_id = ?",
                (schedule.schedule_id,),
            ).fetchone()
            if existing is not None:
                _sync_catalyst_strategy_default(conn, schedule, existing, current_text, current)
                continue
            next_tick = _default_next_tick(schedule, current)
            conn.execute(
                """
                INSERT INTO job_schedules (
                    schedule_id, job_key, title, enabled, timezone, cadence_kind,
                    cadence_json, window_preset, request_json, catch_up_policy,
                    max_lag_minutes, next_tick_at, sort_order, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    schedule.schedule_id,
                    schedule.job_key,
                    schedule.title,
                    1 if schedule.enabled else 0,
                    schedule.timezone,
                    schedule.cadence_kind,
                    _json(schedule.cadence),
                    schedule.window_preset,
                    _json(schedule.request),
                    schedule.catch_up_policy,
                    schedule.max_lag_minutes,
                    next_tick.isoformat(),
                    schedule.sort_order,
                    current_text,
                    current_text,
                ),
            )


def list_schedules(database: Path) -> list[ScheduleRecord]:
    ensure_default_schedules(database)
    with _connect(database) as conn:
        rows = conn.execute(
            """
            SELECT * FROM job_schedules
            ORDER BY sort_order ASC, title ASC
            """
        ).fetchall()
    return [_row_to_schedule(row) for row in rows]


def get_schedule(database: Path, schedule_id: str) -> ScheduleRecord | None:
    ensure_default_schedules(database)
    with _connect(database) as conn:
        row = conn.execute(
            "SELECT * FROM job_schedules WHERE schedule_id = ?",
            (schedule_id,),
        ).fetchone()
    return _row_to_schedule(row) if row is not None else None


def list_due_schedules(database: Path, *, now: datetime, limit: int = 20) -> list[ScheduleRecord]:
    ensure_default_schedules(database, now=now)
    with _connect(database) as conn:
        rows = conn.execute(
            """
            SELECT * FROM job_schedules
            WHERE enabled = 1 AND next_tick_at IS NOT NULL AND next_tick_at <= ?
            ORDER BY next_tick_at ASC, sort_order ASC
            LIMIT ?
            """,
            (now.isoformat(), limit),
        ).fetchall()
    return [_row_to_schedule(row) for row in rows]


def set_schedule_enabled(
    database: Path,
    schedule_id: str,
    *,
    enabled: bool,
    now: datetime | None = None,
) -> ScheduleRecord | None:
    current = now or scheduler_now()
    schedule = get_schedule(database, schedule_id)
    if schedule is None:
        return None
    next_tick = compute_next_tick_at(schedule, current)
    with _connect(database) as conn:
        conn.execute(
            """
            UPDATE job_schedules
            SET enabled = ?, next_tick_at = ?, updated_at = ?
            WHERE schedule_id = ?
            """,
            (1 if enabled else 0, next_tick.isoformat(), current.isoformat(), schedule_id),
        )
    return get_schedule(database, schedule_id)


def update_schedule_after_tick(
    database: Path,
    schedule: ScheduleRecord,
    *,
    last_tick_at: datetime,
    next_tick_at: datetime,
) -> ScheduleRecord | None:
    with _connect(database) as conn:
        conn.execute(
            """
            UPDATE job_schedules
            SET last_tick_at = ?, next_tick_at = ?, updated_at = ?
            WHERE schedule_id = ?
            """,
            (
                last_tick_at.isoformat(),
                next_tick_at.isoformat(),
                last_tick_at.isoformat(),
                schedule.schedule_id,
            ),
        )
    return get_schedule(database, schedule.schedule_id)


def create_schedule_tick(
    database: Path,
    *,
    schedule_id: str,
    planned_at: datetime,
    request: dict[str, Any],
    now: datetime | None = None,
) -> ScheduleTickRecord:
    current = now or scheduler_now()
    tick_id = uuid4().hex
    with _connect(database) as conn:
        conn.execute(
            """
            INSERT INTO job_schedule_ticks (
                tick_id, schedule_id, planned_at, status, request_json, created_at, updated_at
            ) VALUES (?, ?, ?, 'running', ?, ?, ?)
            """,
            (
                tick_id,
                schedule_id,
                planned_at.isoformat(),
                _json(request),
                current.isoformat(),
                current.isoformat(),
            ),
        )
    tick = get_schedule_tick(database, tick_id)
    if tick is None:
        raise RuntimeError(f"调度 tick 写入失败: {tick_id}")
    return tick


def finish_schedule_tick(
    database: Path,
    tick_id: str,
    *,
    status: TickStatus,
    run_ids: list[str] | None = None,
    skipped_reason: str | None = None,
    error_message: str | None = None,
    request: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> ScheduleTickRecord | None:
    current = now or scheduler_now()
    updates = [
        "fired_at = ?",
        "status = ?",
        "run_ids_json = ?",
        "skipped_reason = ?",
        "error_message = ?",
        "updated_at = ?",
    ]
    params: list[object] = [
        current.isoformat(),
        status,
        _json(run_ids or []),
        skipped_reason,
        error_message,
        current.isoformat(),
    ]
    if request is not None:
        updates.append("request_json = ?")
        params.append(_json(request))
    params.append(tick_id)
    with _connect(database) as conn:
        conn.execute(
            f"""
            UPDATE job_schedule_ticks
            SET {", ".join(updates)}
            WHERE tick_id = ?
            """,
            params,
        )
    return get_schedule_tick(database, tick_id)


def get_schedule_tick(database: Path, tick_id: str) -> ScheduleTickRecord | None:
    with _connect(database) as conn:
        row = conn.execute(
            "SELECT * FROM job_schedule_ticks WHERE tick_id = ?",
            (tick_id,),
        ).fetchone()
    return _row_to_tick(row) if row is not None else None


def list_schedule_ticks(
    database: Path,
    *,
    schedule_id: str | None = None,
    limit: int = 50,
) -> list[ScheduleTickRecord]:
    if limit < 1 or limit > 200:
        raise ValueError("limit 必须在 1 到 200 之间")
    ensure_default_schedules(database)
    sql = ["SELECT * FROM job_schedule_ticks"]
    params: list[object] = []
    if schedule_id:
        sql.append("WHERE schedule_id = ?")
        params.append(schedule_id)
    sql.append("ORDER BY created_at DESC LIMIT ?")
    params.append(limit)
    with _connect(database) as conn:
        rows = conn.execute(" ".join(sql), params).fetchall()
    return [_row_to_tick(row) for row in rows]


def _delete_retired_schedules(conn: sqlite3.Connection) -> None:
    _delete_retired_schedules_by_ids(conn)
    _delete_retired_schedules_by_job_keys(conn)


def _sync_catalyst_strategy_default(
    conn: sqlite3.Connection,
    default_schedule,
    row: sqlite3.Row,
    current_text: str,
    current: datetime,
) -> None:
    if default_schedule.schedule_id != "catalyst-strategy-hourly":
        return

    updates: list[str] = []
    params: list[object] = []
    request = _load_json(row["request_json"], {})
    if request.get("notify") is False:
        request["notify"] = True
        updates.append("request_json = ?")
        params.append(_json(request))

    if row["created_at"] == row["updated_at"] and bool(row["enabled"]) != default_schedule.enabled:
        updates.append("enabled = ?")
        params.append(1 if default_schedule.enabled else 0)
        updates.append("next_tick_at = ?")
        params.append(_default_next_tick(default_schedule, current).isoformat())

    if not updates:
        return
    updates.append("updated_at = ?")
    params.append(current_text)
    params.append(default_schedule.schedule_id)
    conn.execute(
        f"""
        UPDATE job_schedules
        SET {", ".join(updates)}
        WHERE schedule_id = ?
        """,
        params,
    )


def _delete_retired_schedules_by_ids(conn: sqlite3.Connection) -> None:
    if not RETIRED_SCHEDULE_IDS:
        return
    placeholders = ", ".join("?" for _ in RETIRED_SCHEDULE_IDS)
    params = list(RETIRED_SCHEDULE_IDS)
    conn.execute(f"DELETE FROM job_schedule_ticks WHERE schedule_id IN ({placeholders})", params)
    conn.execute(f"DELETE FROM job_schedules WHERE schedule_id IN ({placeholders})", params)


def _delete_retired_schedules_by_job_keys(conn: sqlite3.Connection) -> None:
    if not RETIRED_SCHEDULE_JOB_KEYS:
        return
    placeholders = ", ".join("?" for _ in RETIRED_SCHEDULE_JOB_KEYS)
    params = list(RETIRED_SCHEDULE_JOB_KEYS)
    conn.execute(
        f"""
        DELETE FROM job_schedule_ticks
        WHERE schedule_id IN (
            SELECT schedule_id FROM job_schedules WHERE job_key IN ({placeholders})
        )
        """,
        params,
    )
    conn.execute(f"DELETE FROM job_schedules WHERE job_key IN ({placeholders})", params)


def _default_next_tick(default_schedule, now: datetime) -> datetime:
    record = ScheduleRecord(
        schedule_id=default_schedule.schedule_id,
        job_key=default_schedule.job_key,
        title=default_schedule.title,
        enabled=default_schedule.enabled,
        timezone=default_schedule.timezone,
        cadence_kind=default_schedule.cadence_kind,
        cadence=default_schedule.cadence,
        window_preset=default_schedule.window_preset,
        request=default_schedule.request,
        catch_up_policy=default_schedule.catch_up_policy,
        max_lag_minutes=default_schedule.max_lag_minutes,
        sort_order=default_schedule.sort_order,
        created_at=now,
        updated_at=now,
    )
    return compute_next_tick_at(record, now)


def _connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database, timeout=_SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    configure_sqlite_connection(conn, busy_timeout_ms=_SQLITE_BUSY_TIMEOUT_MS)
    migrate_message_db(conn)
    return conn


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _load_json(value: str | None, fallback):
    if not value:
        return fallback
    return json.loads(value)


def _row_to_schedule(row: sqlite3.Row) -> ScheduleRecord:
    return ScheduleRecord(
        schedule_id=row["schedule_id"],
        job_key=row["job_key"],
        title=row["title"],
        enabled=bool(row["enabled"]),
        timezone=row["timezone"],
        cadence_kind=row["cadence_kind"],
        cadence=_load_json(row["cadence_json"], {}),
        window_preset=row["window_preset"],
        request=_load_json(row["request_json"], {}),
        catch_up_policy=row["catch_up_policy"],
        max_lag_minutes=row["max_lag_minutes"],
        last_tick_at=datetime.fromisoformat(row["last_tick_at"]) if row["last_tick_at"] else None,
        next_tick_at=datetime.fromisoformat(row["next_tick_at"]) if row["next_tick_at"] else None,
        sort_order=row["sort_order"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_tick(row: sqlite3.Row) -> ScheduleTickRecord:
    return ScheduleTickRecord(
        tick_id=row["tick_id"],
        schedule_id=row["schedule_id"],
        planned_at=datetime.fromisoformat(row["planned_at"]),
        fired_at=datetime.fromisoformat(row["fired_at"]) if row["fired_at"] else None,
        status=row["status"],
        run_ids=_load_json(row["run_ids_json"], []),
        request=_load_json(row["request_json"], {}),
        skipped_reason=row["skipped_reason"],
        error_message=row["error_message"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
