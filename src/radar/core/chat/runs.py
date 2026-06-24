from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from radar.core.chat.events import new_id, now_iso
from radar.core.config import RadarConfig

ChatRunStatus = Literal["running", "completed", "failed", "cancelled"]

DEFAULT_LEASE_SECONDS = 120
DEFAULT_FINISHED_RUN_KEEP_LATEST = 500
TERMINAL_RUN_STATUSES = ("completed", "failed", "cancelled")
_RUN_LOCK = threading.RLock()


class ChatRunLeaseLost(RuntimeError):
    """Raised when another process has claimed the run lease."""


class ChatRun(BaseModel):
    run_id: str
    session_id: str
    created_at: str
    updated_at: str
    status: ChatRunStatus
    last_seq: int = 0
    cancel_requested: bool = False
    error: str | None = None
    heartbeat_at: str | None = None
    lease_owner: str | None = None
    lease_until: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    request: dict[str, Any] = Field(default_factory=dict)


class ChatRunEvent(BaseModel):
    run_id: str
    session_id: str
    seq: int
    event: str
    created_at: str
    data: dict[str, Any] = Field(default_factory=dict)


class ChatRunStore:
    """SQLite-backed run log for resumable chat streams.

    session 是对话真相，run 是前端可恢复订阅的传输日志。
    run/request/event 独立落到 chat 专用 SQLite，避免服务重启后丢掉运行态。
    """

    def __init__(self, root: Path):
        self.root = root.expanduser()
        self.database_path = self.root / "runs.sqlite3"

    @classmethod
    def from_config(cls, config: RadarConfig) -> "ChatRunStore":
        return cls(config.data_dir / "chat")

    def create_run(
        self,
        session_id: str,
        *,
        metadata: dict[str, Any] | None = None,
        request: dict[str, Any] | None = None,
    ) -> ChatRun:
        now = now_iso()
        run = ChatRun(
            run_id=new_id(),
            session_id=session_id,
            created_at=now,
            updated_at=now,
            status="running",
            heartbeat_at=now,
            metadata=metadata or {},
            request=request or {},
        )
        with _RUN_LOCK, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_runs (
                    run_id, session_id, created_at, updated_at, status, last_seq,
                    cancel_requested, error, heartbeat_at, lease_owner, lease_until,
                    metadata_json, request_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _run_params(run),
            )
            self._cleanup_terminal_runs(conn, keep_latest=DEFAULT_FINISHED_RUN_KEEP_LATEST)
        return run

    def get_run(self, run_id: str) -> ChatRun:
        _validate_run_id(run_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM chat_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"chat run 不存在: {run_id}")
        return _row_to_run(row)

    def append_event(self, run_id: str, event: str, data: dict[str, Any]) -> ChatRunEvent:
        _validate_run_id(run_id)
        with _RUN_LOCK, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM chat_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"chat run 不存在: {run_id}")
            run = _row_to_run(row)
            now = now_iso()
            run_event = ChatRunEvent(
                run_id=run.run_id,
                session_id=run.session_id,
                seq=run.last_seq + 1,
                event=event,
                created_at=now,
                data=data,
            )
            conn.execute(
                """
                INSERT INTO chat_run_events (
                    run_id, session_id, seq, event, created_at, data_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_event.run_id,
                    run_event.session_id,
                    run_event.seq,
                    run_event.event,
                    run_event.created_at,
                    _json_dumps(run_event.data),
                ),
            )
            conn.execute(
                """
                UPDATE chat_runs
                SET last_seq = ?, updated_at = ?, heartbeat_at = ?
                WHERE run_id = ?
                """,
                (run_event.seq, now, now, run_id),
            )
            return run_event

    def load_events(self, run_id: str, *, after_seq: int = 0) -> list[ChatRunEvent]:
        self.get_run(run_id)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM chat_run_events
                WHERE run_id = ? AND seq > ?
                ORDER BY seq ASC
                """,
                (run_id, after_seq),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def mark_completed(self, run_id: str) -> ChatRun:
        return self._update_run(run_id, status="completed", cancel_requested=False, error=None)

    def mark_failed(self, run_id: str, error: str) -> ChatRun:
        return self._update_run(run_id, status="failed", error=error[:1000])

    def mark_cancelled(self, run_id: str) -> ChatRun:
        return self._update_run(
            run_id,
            status="cancelled",
            cancel_requested=True,
            error="已停止",
        )

    def request_cancel(self, run_id: str) -> ChatRun:
        return self._update_run(run_id, cancel_requested=True)

    def claim_run(
        self,
        run_id: str,
        owner: str,
        *,
        ttl_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> ChatRun | None:
        _validate_run_id(run_id)
        _validate_owner(owner)
        now = datetime.now()
        now_text = now.isoformat()
        lease_until = (now + timedelta(seconds=max(1, ttl_seconds))).isoformat()
        with _RUN_LOCK, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE chat_runs
                SET lease_owner = ?, lease_until = ?, heartbeat_at = ?, updated_at = ?
                WHERE run_id = ?
                  AND status = 'running'
                  AND cancel_requested = 0
                  AND (lease_until IS NULL OR lease_until < ? OR lease_owner = ?)
                """,
                (owner, lease_until, now_text, now_text, run_id, now_text, owner),
            )
            if cursor.rowcount == 0:
                return None
            row = conn.execute("SELECT * FROM chat_runs WHERE run_id = ?", (run_id,)).fetchone()
        return _row_to_run(row) if row is not None else None

    def release_lease(self, run_id: str, owner: str) -> ChatRun:
        _validate_run_id(run_id)
        _validate_owner(owner)
        with _RUN_LOCK, self._connect() as conn:
            conn.execute(
                """
                UPDATE chat_runs
                SET lease_owner = NULL, lease_until = NULL, updated_at = ?
                WHERE run_id = ? AND lease_owner = ?
                """,
                (now_iso(), run_id, owner),
            )
            row = conn.execute("SELECT * FROM chat_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(f"chat run 不存在: {run_id}")
        return _row_to_run(row)

    def heartbeat(
        self,
        run_id: str,
        *,
        owner: str | None = None,
        ttl_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> ChatRun:
        if owner is None:
            return self._update_run(run_id, heartbeat_at=now_iso())
        _validate_run_id(run_id)
        _validate_owner(owner)
        now = datetime.now()
        now_text = now.isoformat()
        lease_until = (now + timedelta(seconds=max(1, ttl_seconds))).isoformat()
        with _RUN_LOCK, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE chat_runs
                SET heartbeat_at = ?, lease_until = ?, updated_at = ?
                WHERE run_id = ? AND lease_owner = ?
                """,
                (now_text, lease_until, now_text, run_id, owner),
            )
            row = conn.execute("SELECT * FROM chat_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(f"chat run 不存在: {run_id}")
        if cursor.rowcount == 0:
            raise ChatRunLeaseLost(f"chat run lease 已被其它 worker 接管: {run_id}")
        return _row_to_run(row)

    def cleanup_terminal_runs(
        self,
        *,
        keep_latest: int = DEFAULT_FINISHED_RUN_KEEP_LATEST,
        older_than: str | datetime | None = None,
    ) -> int:
        with _RUN_LOCK, self._connect() as conn:
            return self._cleanup_terminal_runs(
                conn,
                keep_latest=keep_latest,
                older_than=_older_than_text(older_than),
            )

    def _cleanup_terminal_runs(
        self,
        conn: sqlite3.Connection,
        *,
        keep_latest: int,
        older_than: str | None = None,
    ) -> int:
        keep_latest = max(0, keep_latest)
        terminal_placeholders = ",".join("?" for _ in TERMINAL_RUN_STATUSES)
        rows = conn.execute(
            f"""
            SELECT run_id, updated_at
            FROM chat_runs
            WHERE status IN ({terminal_placeholders})
            ORDER BY updated_at DESC, created_at DESC, run_id DESC
            """,
            TERMINAL_RUN_STATUSES,
        ).fetchall()
        candidates = []
        for row in rows[keep_latest:]:
            updated_at = str(row["updated_at"])
            if older_than is None or updated_at < older_than:
                candidates.append(str(row["run_id"]))
        if not candidates:
            return 0
        placeholders = ",".join("?" for _ in candidates)
        conn.execute(f"DELETE FROM chat_run_events WHERE run_id IN ({placeholders})", candidates)
        conn.execute(f"DELETE FROM chat_runs WHERE run_id IN ({placeholders})", candidates)
        return len(candidates)

    def is_cancel_requested(self, run_id: str) -> bool:
        return self.get_run(run_id).cancel_requested

    def active_run(
        self,
        *,
        session_id: str | None = None,
        surface: str | None = None,
        entity_id: str | None = None,
    ) -> ChatRun | None:
        active = [
            run
            for run in self.list_runs(session_id=session_id)
            if run.status == "running"
            and not run.cancel_requested
            and _metadata_matches(run, surface=surface, entity_id=entity_id)
        ]
        return active[0] if active else None

    def list_runs(self, *, session_id: str | None = None) -> list[ChatRun]:
        where = ""
        params: tuple[Any, ...] = ()
        if session_id is not None:
            where = "WHERE session_id = ?"
            params = (session_id,)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM chat_runs {where} ORDER BY updated_at DESC",
                params,
            ).fetchall()
        return [_row_to_run(row) for row in rows]

    def _update_run(self, run_id: str, **updates: Any) -> ChatRun:
        _validate_run_id(run_id)
        with _RUN_LOCK, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM chat_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"chat run 不存在: {run_id}")
            run = _row_to_run(row).model_copy(update={**updates, "updated_at": now_iso()})
            conn.execute(
                """
                UPDATE chat_runs
                SET session_id = ?, created_at = ?, updated_at = ?, status = ?,
                    last_seq = ?, cancel_requested = ?, error = ?, heartbeat_at = ?,
                    lease_owner = ?, lease_until = ?, metadata_json = ?, request_json = ?
                WHERE run_id = ?
                """,
                (*_run_params(run)[1:], run.run_id),
            )
            return run

    def _connect(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_runs (
            run_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status TEXT NOT NULL,
            last_seq INTEGER NOT NULL DEFAULT 0,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            heartbeat_at TEXT,
            lease_owner TEXT,
            lease_until TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            request_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    _ensure_columns(
        conn,
        "chat_runs",
        {
            "lease_owner": "TEXT",
            "lease_until": "TEXT",
        },
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_run_events (
            run_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            event TEXT NOT NULL,
            created_at TEXT NOT NULL,
            data_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (run_id, seq)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_runs_session_status ON chat_runs(session_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_run_events_run_seq ON chat_run_events(run_id, seq)"
    )


def _run_params(run: ChatRun) -> tuple[Any, ...]:
    return (
        run.run_id,
        run.session_id,
        run.created_at,
        run.updated_at,
        run.status,
        run.last_seq,
        1 if run.cancel_requested else 0,
        run.error,
        run.heartbeat_at,
        run.lease_owner,
        run.lease_until,
        _json_dumps(run.metadata),
        _json_dumps(run.request),
    )


def _row_to_run(row: sqlite3.Row) -> ChatRun:
    return ChatRun(
        run_id=str(row["run_id"]),
        session_id=str(row["session_id"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        status=row["status"],
        last_seq=int(row["last_seq"]),
        cancel_requested=bool(row["cancel_requested"]),
        error=row["error"],
        heartbeat_at=row["heartbeat_at"],
        lease_owner=row["lease_owner"],
        lease_until=row["lease_until"],
        metadata=_json_loads(row["metadata_json"]),
        request=_json_loads(row["request_json"]),
    )


def _row_to_event(row: sqlite3.Row) -> ChatRunEvent:
    return ChatRunEvent(
        run_id=str(row["run_id"]),
        session_id=str(row["session_id"]),
        seq=int(row["seq"]),
        event=str(row["event"]),
        created_at=str(row["created_at"]),
        data=_json_loads(row["data_json"]),
    )


def _metadata_matches(
    run: ChatRun,
    *,
    surface: str | None,
    entity_id: str | None,
) -> bool:
    if surface is not None and run.metadata.get("surface") != surface:
        return False
    if entity_id is not None and run.metadata.get("entity_id") != entity_id:
        return False
    return True


def _validate_run_id(run_id: str) -> None:
    if "/" in run_id or "\\" in run_id:
        raise ValueError("run_id 不能包含路径分隔符")


def _validate_owner(owner: str) -> None:
    if not owner.strip():
        raise ValueError("lease owner 不能为空")


def _older_than_text(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return value if isinstance(value, str) and value else None


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_loads(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
