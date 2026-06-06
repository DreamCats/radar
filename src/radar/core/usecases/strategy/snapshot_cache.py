from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from radar.core.config import RadarConfig
from radar.core.db import migrate_market_db
from radar.core.store import connect, init_db
from radar.core.usecases.strategy.models import StrategyDashboard
from radar.core.usecases.strategy.signals import build_strategy_dashboard_from_conn
from radar.core.usecases.strategy.snapshots import (
    STRATEGY_TYPE,
    StrategySnapshotSaveResult,
    save_strategy_dashboard_snapshot,
)


def save_cached_strategy_snapshot(
    config: RadarConfig,
    *,
    days: int = 30,
    recent_days: int = 7,
    limit: int = 12,
    force: bool = False,
) -> StrategySnapshotSaveResult:
    conn = connect(config.database_path)
    market_conn = connect(config.market_database_path)
    try:
        init_db(conn)
        migrate_market_db(market_conn)
        dashboard = build_strategy_dashboard_from_conn(
            conn,
            market_conn=market_conn,
            days=days,
            recent_days=recent_days,
            limit=limit,
        )
        if not force:
            cached = _find_cached_snapshot(conn, dashboard)
            if cached is not None:
                return cached
        return save_strategy_dashboard_snapshot(conn, dashboard)
    finally:
        conn.close()
        market_conn.close()


def _find_cached_snapshot(conn: sqlite3.Connection, dashboard: StrategyDashboard) -> StrategySnapshotSaveResult | None:
    payload = _stable_payload(dashboard.model_dump(mode="json"))
    rows = conn.execute(
        """
        SELECT snapshot_id, generated_at, stock_count, opportunity_count, payload_json
        FROM strategy_snapshots
        WHERE strategy_type = ?
          AND start_time = ?
          AND end_time = ?
          AND recent_start_time = ?
          AND stock_count = ?
          AND opportunity_count = ?
        ORDER BY created_at DESC
        LIMIT 20
        """,
        (
            STRATEGY_TYPE,
            dashboard.start_time.isoformat(),
            dashboard.end_time.isoformat(),
            dashboard.recent_start_time.isoformat(),
            len(dashboard.stock_candidates),
            dashboard.opportunity_count,
        ),
    ).fetchall()
    for row in rows:
        try:
            stored_payload = _stable_payload(json.loads(row["payload_json"] or "{}"))
        except json.JSONDecodeError:
            continue
        if stored_payload == payload:
            return StrategySnapshotSaveResult(
                snapshot_id=str(row["snapshot_id"]),
                generated_at=datetime.fromisoformat(str(row["generated_at"])),
                stock_count=int(row["stock_count"]),
                opportunity_count=int(row["opportunity_count"]),
                reused_existing=True,
            )
    return None


def _stable_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable_payload(item) for key, item in value.items() if key != "generated_at"}
    if isinstance(value, list):
        return [_stable_payload(item) for item in value]
    return value
