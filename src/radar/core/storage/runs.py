from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from radar.core.storage.db import configure_sqlite_connection, migrate_message_db

RunStatus = Literal["running", "succeeded", "skipped", "partial_failed", "failed"]
_SQLITE_TIMEOUT_SECONDS = 15.0
_SQLITE_BUSY_TIMEOUT_MS = 15_000


class RunRecord(BaseModel):
    run_id: str
    kind: str
    target: str
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus
    raw_count: int = 0
    stored_count: int = 0
    filtered_count: int = 0
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def start_run(
    database: Path,
    *,
    kind: str,
    target: str,
    metadata: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
    busy_timeout_ms: int | None = None,
) -> str:
    """记录一次 core 执行；run_id 用于 CLI/Web 排查同一次任务。"""

    run_id = uuid4().hex
    now = datetime.now().isoformat()
    with _connect(database, timeout_seconds=timeout_seconds, busy_timeout_ms=busy_timeout_ms) as conn:
        conn.execute(
            """
            INSERT INTO runs (
                run_id, kind, target, started_at, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, kind, target, now, "running", _metadata_json(metadata)),
        )
    return run_id


def finish_run(
    database: Path,
    run_id: str,
    *,
    status: Literal["succeeded", "skipped", "partial_failed"] = "succeeded",
    raw_count: int = 0,
    stored_count: int = 0,
    filtered_count: int = 0,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    with _connect(database) as conn:
        conn.execute(
            """
            UPDATE runs
            SET finished_at = ?,
                status = ?,
                raw_count = ?,
                stored_count = ?,
                filtered_count = ?,
                error_message = ?,
                metadata_json = ?
            WHERE run_id = ? AND status = 'running'
            """,
            (
                datetime.now().isoformat(),
                status,
                raw_count,
                stored_count,
                filtered_count,
                error_message,
                _metadata_json(metadata),
                run_id,
            ),
        )


def cancel_run(database: Path, run_id: str, *, reason: str = "用户终止任务") -> RunRecord | None:
    """把运行中的任务标记为失败；实际 worker 会在下一次进度检查时停止。"""

    now = datetime.now().isoformat()
    with _connect(database) as conn:
        row = conn.execute("SELECT metadata_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        metadata = json.loads(row["metadata_json"] or "{}")
        metadata["cancel_requested_at"] = now
        metadata["cancel_reason"] = reason
        conn.execute(
            """
            UPDATE runs
            SET finished_at = ?,
                status = 'failed',
                error_message = ?,
                metadata_json = ?
            WHERE run_id = ? AND status = 'running'
            """,
            (now, reason, _metadata_json(metadata), run_id),
        )
        updated = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return _row_to_run(updated) if updated is not None else None


def update_run_progress(
    database: Path,
    run_id: str,
    *,
    raw_count: int | None = None,
    stored_count: int | None = None,
    filtered_count: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """更新运行中任务的进度摘要；真实业务结果仍以 finish_run 为准。"""

    with _connect(database) as conn:
        row = conn.execute("SELECT metadata_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return False

        merged_metadata = json.loads(row["metadata_json"] or "{}")
        merged_metadata.update(metadata or {})
        merged_metadata["progress_updated_at"] = datetime.now().isoformat()

        updates = ["metadata_json = ?"]
        params: list[object] = [_metadata_json(merged_metadata)]
        if raw_count is not None:
            updates.append("raw_count = ?")
            params.append(raw_count)
        if stored_count is not None:
            updates.append("stored_count = ?")
            params.append(stored_count)
        if filtered_count is not None:
            updates.append("filtered_count = ?")
            params.append(filtered_count)
        params.append(run_id)

        cursor = conn.execute(
            f"""
            UPDATE runs
            SET {", ".join(updates)}
            WHERE run_id = ? AND status = 'running'
            """,
            params,
        )
        return cursor.rowcount > 0


def fail_run(database: Path, run_id: str, error: BaseException) -> None:
    with _connect(database) as conn:
        conn.execute(
            """
            UPDATE runs
            SET finished_at = ?,
                status = 'failed',
                error_message = ?
            WHERE run_id = ?
            """,
            (datetime.now().isoformat(), str(error)[:1000], run_id),
        )


def get_run(database: Path, run_id: str) -> RunRecord | None:
    with _connect(database) as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    return _row_to_run(row)


def get_running_run(
    database: Path,
    *,
    kind: str,
    target: str,
    timeout_seconds: float | None = None,
    busy_timeout_ms: int | None = None,
) -> RunRecord | None:
    with _connect(database, timeout_seconds=timeout_seconds, busy_timeout_ms=busy_timeout_ms) as conn:
        row = conn.execute(
            """
            SELECT * FROM runs
            WHERE kind = ? AND target = ? AND status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (kind, target),
        ).fetchone()
    if row is None:
        return None
    return _row_to_run(row)


def is_run_running(database: Path, run_id: str) -> bool:
    with _connect(database) as conn:
        row = conn.execute("SELECT 1 FROM runs WHERE run_id = ? AND status = 'running'", (run_id,)).fetchone()
    return row is not None


def fail_stale_runs(
    database: Path,
    *,
    older_than: datetime,
    kind: str | None = None,
    timeout_seconds: float | None = None,
    busy_timeout_ms: int | None = None,
) -> int:
    """把服务重启后遗留的 running 标记为失败，避免前端一直等。"""

    sql = [
        """
        UPDATE runs
        SET finished_at = ?,
            status = 'failed',
            error_message = ?
        WHERE status = 'running' AND started_at < ?
        """
    ]
    params: list[object] = [
        datetime.now().isoformat(),
        "任务超过预期时间未完成，已标记为过期",
        older_than.isoformat(),
    ]
    if kind:
        sql.append("AND kind = ?")
        params.append(kind)

    try:
        with _connect(database, timeout_seconds=timeout_seconds, busy_timeout_ms=busy_timeout_ms) as conn:
            cursor = conn.execute(" ".join(sql), params)
            return cursor.rowcount
    except sqlite3.OperationalError as exc:
        if _is_database_locked(exc):
            return 0
        raise


def list_runs(
    database: Path,
    *,
    kind: str | None = None,
    kinds: list[str] | None = None,
    status: RunStatus | None = None,
    limit: int = 50,
) -> list[RunRecord]:
    """按开始时间倒序查看执行记录；Web/CLI 只展示脱敏摘要。"""

    if limit < 1 or limit > 200:
        raise ValueError("limit 必须在 1 到 200 之间")

    sql = ["SELECT * FROM runs"]
    where: list[str] = []
    params: list[object] = []
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if kinds:
        placeholders = ", ".join("?" for _ in kinds)
        where.append(f"kind IN ({placeholders})")
        params.extend(kinds)
    if status:
        where.append("status = ?")
        params.append(status)
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY started_at DESC LIMIT ?")
    params.append(limit)

    with _connect(database) as conn:
        rows = conn.execute(" ".join(sql), params).fetchall()
    return [_row_to_run(row) for row in rows]


def _connect(
    database: Path,
    *,
    timeout_seconds: float | None = None,
    busy_timeout_ms: int | None = None,
) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database, timeout=timeout_seconds or _SQLITE_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    configure_sqlite_connection(conn, busy_timeout_ms=busy_timeout_ms or _SQLITE_BUSY_TIMEOUT_MS)
    migrate_message_db(conn)
    return conn


def _is_database_locked(error: sqlite3.OperationalError) -> bool:
    message = str(error).lower()
    return "database is locked" in message or "database table is locked" in message


def _metadata_json(metadata: dict[str, Any] | None) -> str:
    return json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True, default=str)


def _row_to_run(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        run_id=row["run_id"],
        kind=row["kind"],
        target=row["target"],
        started_at=datetime.fromisoformat(row["started_at"]),
        finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
        status=row["status"],
        raw_count=row["raw_count"],
        stored_count=row["stored_count"],
        filtered_count=row["filtered_count"],
        error_message=row["error_message"],
        metadata=json.loads(row["metadata_json"] or "{}"),
    )
