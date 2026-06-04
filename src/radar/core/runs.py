from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from radar.core.db import migrate_message_db

RunStatus = Literal["running", "succeeded", "skipped", "failed"]


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
) -> str:
    """记录一次 core 执行；run_id 用于 CLI/Web 排查同一次任务。"""

    run_id = uuid4().hex
    now = datetime.now().isoformat()
    with _connect(database) as conn:
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
    status: Literal["succeeded", "skipped"] = "succeeded",
    raw_count: int = 0,
    stored_count: int = 0,
    filtered_count: int = 0,
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
                error_message = NULL,
                metadata_json = ?
            WHERE run_id = ?
            """,
            (
                datetime.now().isoformat(),
                status,
                raw_count,
                stored_count,
                filtered_count,
                _metadata_json(metadata),
                run_id,
            ),
        )


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


def _connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    migrate_message_db(conn)
    return conn


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
