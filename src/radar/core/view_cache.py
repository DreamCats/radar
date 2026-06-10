from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db, migrate_message_db
from radar.core.store import connect

ModelT = TypeVar("ModelT", bound=BaseModel)


def cache_key(name: str, params: dict[str, object]) -> str:
    raw = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{name}:{hashlib.sha256(raw.encode()).hexdigest()}"


def cached_model(
    database: Path,
    *,
    key: str,
    dependency_key: str,
    model_type: type[ModelT],
    compute: Callable[[], ModelT],
    ttl_seconds: int = 86_400,
) -> ModelT:
    cached = load_model(database, key=key, dependency_key=dependency_key, model_type=model_type)
    if cached is not None:
        return cached

    started = time.perf_counter()
    value = compute()
    compute_ms = int((time.perf_counter() - started) * 1000)
    store_model(database, key=key, dependency_key=dependency_key, value=value, ttl_seconds=ttl_seconds, compute_ms=compute_ms)
    return value


def load_model(
    database: Path,
    *,
    key: str,
    dependency_key: str,
    model_type: type[ModelT],
) -> ModelT | None:
    with connect(database) as conn:
        migrate_message_db(conn)
        row = conn.execute(
            """
            SELECT payload_json, expires_at
            FROM view_cache
            WHERE cache_key = ? AND dependency_key = ?
            """,
            (key, dependency_key),
        ).fetchone()
    if row is None:
        return None
    if row["expires_at"] and datetime.fromisoformat(str(row["expires_at"])) <= datetime.now():
        return None
    return model_type.model_validate_json(str(row["payload_json"]))


def store_model(
    database: Path,
    *,
    key: str,
    dependency_key: str,
    value: BaseModel,
    ttl_seconds: int,
    compute_ms: int,
) -> None:
    now = datetime.now()
    expires_at = now + timedelta(seconds=ttl_seconds) if ttl_seconds > 0 else None
    with connect(database) as conn:
        migrate_message_db(conn)
        conn.execute(
            """
            INSERT INTO view_cache (
                cache_key, dependency_key, payload_json, created_at, expires_at, compute_ms
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                dependency_key = excluded.dependency_key,
                payload_json = excluded.payload_json,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at,
                compute_ms = excluded.compute_ms
            """,
            (
                key,
                dependency_key,
                value.model_dump_json(),
                now.isoformat(),
                expires_at.isoformat() if expires_at else None,
                compute_ms,
            ),
        )
        conn.commit()


def dashboard_dependency_key(config: RadarConfig) -> str:
    return _hash_parts(
        {
            "message": _message_dependency(config.database_path),
            "market": _market_dependency(config.market_database_path),
        }
    )


def cleanup_cache(database: Path, *, keep: int = 500) -> int:
    with connect(database) as conn:
        migrate_message_db(conn)
        cur = conn.execute(
            """
            DELETE FROM view_cache
            WHERE cache_key NOT IN (
                SELECT cache_key FROM view_cache ORDER BY created_at DESC LIMIT ?
            )
            """,
            (keep,),
        )
        conn.commit()
        return cur.rowcount


def _message_dependency(database: Path) -> dict[str, tuple[int, str]]:
    with connect(database) as conn:
        migrate_message_db(conn)
        return {
            "messages": _table_signature(conn, "messages", "message_time"),
            "message_classifications": _table_signature(conn, "message_classifications", "updated_at"),
            "recommendation_events": _table_signature(conn, "recommendation_events", "message_time"),
            "recommendation_backtest_windows": _table_signature(conn, "recommendation_backtest_windows", "updated_at"),
        }


def _market_dependency(database: Path) -> dict[str, tuple[int, str]]:
    with connect(database) as conn:
        migrate_market_db(conn)
        return {
            "daily": _history_signature(conn, "daily"),
            "index_daily": _history_signature(conn, "index_daily"),
        }


def _table_signature(conn: sqlite3.Connection, table: str, max_column: str) -> tuple[int, str]:
    row = conn.execute(f"SELECT COUNT(*) AS count, MAX({max_column}) AS max_value FROM {table}").fetchone()
    return int(row["count"] or 0), str(row["max_value"] or "")


def _history_signature(conn: sqlite3.Connection, api_name: str) -> tuple[int, str]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count, MAX(date_key) AS max_value
        FROM tushare_history
        WHERE api_name = ?
        """,
        (api_name,),
    ).fetchone()
    return int(row["count"] or 0), str(row["max_value"] or "")


def _hash_parts(parts: object) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()
